# Hardening verification, 2026-10-03 (H1–H6, post-refactor)

> Superseded in part by `docs/research/probes/hardening-2026-10-04.md`. The fixed-key artifact
> behaviour this record lists as an open limit, and the cleanup claim the plan listed as
> status-fenced, both changed in the following round: artifact keys are attempt-scoped and the
> cleanup claim is a lease with an attempt token. This record is kept as the state of its own round.

This is the targeted real-container record for the hardening round that fenced stale attempts,
narrowed API composition, kept Taskiq at the worker boundary, made external-deletion cleanup
durable, made CLI composition command-specific and removed the remaining duplicate surfaces. It is
not the acceptance run: `scripts/e2e-final.ps1` is, its last recorded run
predates this round (`docs/research/probes/final-e2e-2026-10-03.md`), and it has not been re-run
since — the run below is what was executed instead, on the same Compose topology and the same real
providers.

## What ran

| check | command | outcome |
|---|---|---|
| static | `scripts/check.ps1` (locked sync, Ruff, format, strict Pyright) | clean: `All checks passed!`, `0 errors, 0 warnings, 0 informations` |
| migrations | `scripts/probes/migrations.ps1 -EnvironmentReady` | passed, 8.0 s — `cleanup_intents` created by `0006`, `alembic check` reports "ORM metadata matches the migrated schema", downgrade → upgrade round trip clean, business database untouched |
| hardening | `uv run python scripts/probes/hardening.py` (new, below) | passed — 11 fence invariants and 8 cleanup invariants |
| ingestion | `scripts/probes/ingestion.ps1` | passed, 63.4 s — document and knowledge-base deletion each record `pending|0`, `cleanup-pending` runs them to `succeeded|1`, the objects are gone |
| parsing | `scripts/probes/parsing.ps1` | passed, 249.9 s — 8 formats parsed with real `anydoc`/PaddleOCR-VL calls, the knowledge-base deletion's intent reaches `succeeded`, no leftover object |
| queue | `scripts/probes/queue.ps1` | passed, 125.2 s — topology, duplicate delivery skipped, deterministic vs transient classification, the retry endpoint's `created`/`queued`/`running`/`stale`/409 outcomes, an unreachable broker, and the knowledge-base cleanup completed by the **worker's sweep** (`[10] cleanup intent after the worker's sweep -> succeeded`) |

Not run in this round: `scripts/smoke.ps1` as a whole, `scripts/e2e-final.ps1`, and the probes this
change does not touch (`health`, `auth`, `chunking`, `indexing`, `retrieval`, `agent`, `graph`,
`observability`). `chunking`, `indexing` and `parsing` gained the same cleanup wait the ingestion and
queue probes use, but only `parsing` was executed here; the other two are part of the acceptance run.

## The new check: `scripts/probes/hardening.py`

Two invariants cannot be shown by a fake or a static check, because both are about what a second
writer may do to rows that really exist. The check drives the real store and the real lane against
the configured PostgreSQL, with fakes only for the external stores it wants to fail on purpose.

**H1 — the fence.** One owner, knowledge base, document, uploaded version and `pending` parse job are
seeded; the job is claimed; `start_parse_retry` is asked for a retry with a zero staleness bound, so
the running attempt counts as abandoned and a replacement revision is appended. Every invariant then
holds:

```text
ok   the queued parse job is claimed once
ok   the stale retry appends a replacement revision
ok   the late attempt's completion is refused and appends no successor
ok   the abandoned attempt is terminal and the replacement is pending
ok   the late attempt moved no version
ok   the late attempt recorded no artifact
ok   the late attempt appended no successor job
ok   the replacement revision is claimable
ok   the current revision records its result and appends the chunk job
ok   a repeated delivery of the finished revision does nothing
ok   exactly one successor job exists for the version
```

**H4 — the durable cleanup.** A document is deleted through the real store, which writes the intent
in the transaction that removes the rows; the lane then runs it with an object store that fails once:

```text
ok   the document's rows are deleted
ok   the deletion wrote a pending intent in its own transaction
ok   the intent names the scope the commit produced
ok   a transient failure returns the intent to pending with the class recorded
ok   the next pass completes the intent
ok   the objects and the version's points were removed once the store recovered
ok   the knowledge base's rows are deleted
ok   the knowledge-base deletion wrote its own pending intent
ok   a rejected index call is recorded terminal after one attempt
ok   the objects were removed and the graph was not touched after the index refused
PASS: the fence and the durable cleanup hold
```

The same run's structured log carries the two decisions the record is meant to make visible:
`cleanup.attempt_failed ... retry=True` with `error_class=ObjectStorageError`, then
`cleanup.completed attempt=2`; and `cleanup.attempt_failed ... retry=False` with
`error_class=VectorIndexRejectedError`, which is the terminal classification.

## What the runs found, and what was changed

1. **The cleanup backoff made a fresh intent unclaimable.** `claim_next` required
   `updated_at <= now - backoff`, so an intent written a moment earlier by a deletion waited a full
   backoff before anything could run it. The predicate now treats `attempt == 0` as claimable
   immediately and applies the backoff only to a retry (`infrastructure/cleanup_store.py`). The
   failure was found by the ingestion probe, which assert-objects-gone and instead saw
   `cleanup attempts 0`.
2. **Five probes asserted that the delete request did the external work.** `ingestion`, `parsing`,
   `chunking`, `indexing` and `queue` deleted a document or a knowledge base and immediately demanded
   the objects, points and graph be gone. That was the old contract. They now assert the durable one:
   the rows are gone, a `pending` intent exists, and the cleanup is drained — by the operator command
   in the probes that run no worker, by the worker's sweep in `queue` — before the external stores are
   read. `parsing` and `ingestion` also start Qdrant when run standalone, because the points are part
   of what the cleanup owes.
3. **A Qdrant outage showed both sides of the retry contract.** One parsing run happened while Qdrant
   was down (Qdrant is not part of that probe's standalone Compose set): the first attempt failed with
   `VectorIndexError ... HTTP 502` and the intent returned to `pending`; with the provider still down,
   the remaining attempts were spent and the intent became terminal `failed`. That is the intended
   finite retry, and it is why the probe now starts the provider it addresses. The record was left in
   place rather than deleted: an intent that is terminal is a fact about a deployment, not noise.
4. **`cleanup-pending` was added because the probes need it and operators do too.** A deployment whose
   worker is stopped, or an operator repairing a terminal cleanup, has no other way to drain the owed
   work; the probes use it to be deterministic instead of waiting on a sweep interval.

## Honest limits of this round

- `scripts/e2e-final.ps1` has not been re-run. The changes touch the deletion contract, the API
  composition, the CLI, the queue adapter's task binding and the migration head, so the acceptance run
  must be executed before the platform is called accepted again.
- The H4 acceptance's "stop the dependency, restore it, prove the worker finishes without a second
  delete" is covered at the store/lane level (a failing external store, a real retry, a real record)
  and for the worker's sweep (queue probe), but not by stopping a container mid-deletion and
  restarting it. The parsing probe's accidental Qdrant outage is the closest real-dependency evidence
  available in this round, and it demonstrates the retry path rather than the recovery path.
- A superseded attempt's artifact objects are left in place by design (see the plan's deviation note
  for H1); the bytes-level race that motivates revision-scoped keys is not measured yet.
