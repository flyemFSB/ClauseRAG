# Artifact immutability and cleanup leases, 2026-10-04

This is the targeted real-container record for the round that closed the two residual findings (the
fixed-key parse/chunk artifacts, and the cleanup claim that was neither re-claimable nor
token-fenced). It is not the acceptance run:
`scripts/e2e-final.ps1` is, and it has not been re-run since this round.

## What ran

| check | command | outcome |
|---|---|---|
| static | `scripts/check.ps1` (locked sync, Ruff, format, strict Pyright) | clean: `All checks passed!`, `113 files already formatted`, `0 errors, 0 warnings, 0 informations` |
| hardening | `uv run python scripts/probes/hardening.py` | passed — the 11 fence invariants, the 10 durable-cleanup invariants and the 12 new lease invariants |
| parsing | `scripts/probes/parsing.ps1` | passed, 237.5 s — 8 formats parsed with real `anydoc`/PaddleOCR-VL calls, every version's pointer equal to its parse artifact row's key, each artifact's read-back digest equal to `parse_artifacts.checksum`, the operator re-parse keeping the same key, the unreadable fixtures leaving no object, the deletion leaving nothing under the run's prefixes |
| chunking | `scripts/probes/chunking.ps1` | passed, 312.3 s — every artifact hashes to its recorded digest, a re-chunk produces the same bytes, the queue chain writes `chunks/{version}/{job}/chunks.jsonl`, a repeated delivery is skipped, step 3b (new) proves a corrupted Markdown is refused, and the deletion leaves nothing under the run's prefixes |
| queue | `scripts/probes/queue.ps1` | passed, 118.0 s — the full lane over the real worker, the retry endpoint's five outcomes, a stale-retry replacement publishing a new artifact key and deleting the object it replaced, an unreachable broker, and the worker's sweep completing the knowledge base's cleanup with no object left behind |

Not run in this round: `scripts/e2e-final.ps1`, `scripts/smoke.ps1`, and the probes this change does
not touch (`health`, `auth`, `ingestion`, `indexing`, `retrieval`, `agent`, `graph`,
`observability`). `ingestion` shares the deletion-cleanup assertions with `parsing`, `chunking` and
`queue`, all three of which ran; it is part of the acceptance run.

## What changed, and what the runs found

1. **The artifact keys are attempt-scoped, so the byte-level race is closed by construction.**
   `parsed_object_key(version_id, job_id)` and `chunks_object_key(version_id, job_id)` now carry the
   identifier of the attempt that writes the object; the row is the pointer a reader follows, and a
   superseded or vanished attempt deletes its own object (`parse_document_version.py`,
   `chunk_document_version.py`). The alternative — a fixed key published with a conditional write —
   was rejected: it still lets a reader observe old bytes under a live key, and boto3's
   `upload_fileobj` refuses `IfNoneMatch`/`IfMatch` as extra arguments (they are not in
   `s3transfer`'s `ALLOWED_UPLOAD_ARGS`), so it would have meant dropping the bounded-memory
   multipart helper. The parsing probe confirms the pointer/key agreement on eight real formats and
   the absence of an object for both unreadable fixtures.
2. **The chunk stage proves the Markdown it cuts is the one its parse artifact row records.**
   `ChunkTarget` carries the artifact's digest and size, resolved from the same `parse_artifacts` row
   as its page spans, and a disagreement is an `UnchunkableDocumentError` — `manual_retry_required`,
   because a retry re-reads the same bytes. Step 3b of the chunking probe overwrites a parsed
   version's stored Markdown with a same-length body, so the size still agrees and only the digest
   disagrees, and asserts the outcome:

   ```text
   the chunk stage over a Markdown whose digest disagrees -> exit 1
   stderr: error: UnchunkableDocumentError: the Markdown artifact
     parsed/{version}/{job}/document.md hashes to a2923bbb... and the parse artifact recorded 9be85274...
   version {version} status=manual_retry_required | job status=manual_retry_required error_class=UnchunkableDocumentError
   [3b] a same-length corruption of the stored Markdown was refused as unreadable, with nothing written
   ```

3. **A successful attempt deletes the object its pointer replaced — the queue probe found that the
   first version of this round did not.** With attempt-scoped keys, every *successful* re-parse or
   re-chunk of a version publishes a new object and leaves the previous one referenced by no row: the
   fixed key used to make that overwrite, so nothing was ever orphaned. `queue.ps1` caught it —
   `QUEUE PROBE FAILED: the replacement changed the artifact key to parsed/{version}/{job}/document.md`
   and `cleanup did not finish: orphan objects: chunks/... , parsed/...` — because it asserts both
   that a stale-retry replacement publishes a new key and that the bucket holds nothing of the run's
   after the deletion. `StageCompletion` now reports the key the pointer moved away from (the store
   reads it in the same transaction), and the parse and chunk stages delete it once that transaction
   has committed; a stage that rewrites its own key (the operator path re-runs the version's current
   job) reports None, because the previous key *is* the published one and deleting it would destroy
   live work. The same probe step now asserts the replacement's key differs, the digest is unchanged
   and the replaced object is gone, and its final cleanup check is what proves no residue remains.

4. **The cleanup claim became a lease with an attempt token, and the finding's reason was
   corrected.** `claim_next` only ever selected `pending` rows, so the "stale worker settles a
   re-claimed row" race the finding described was unreachable; what was real is its inverse — a sweep
   cancelled or killed mid-intent left the row `running` with no reclaim, no lease and no operator
   surface, while `worker/main.py` claimed the next sweep would re-claim it. Now an intent is
   claimable while it has an attempt left and either its last attempt is past the backoff or its
   claim is past `RAG_CLEANUP_LEASE_SECONDS`; the settlement carries the attempt number
   (`WHERE id = :intent AND status = 'running' AND attempt = :claimed_attempt`); a refused settlement
   is reported as `cleanup.settlement_refused`; and a claim whose budget is spent records `failed`
   with `error_class = LeaseExpired` instead of staying `running` for good. The new checks:

   ```text
   ok   the first worker claims the intent
   ok   a claim inside its lease is not handed to a second worker
   ok   a claim past its lease is re-claimed as the next attempt
   ok   the dead worker's settlement is refused
   ok   the new claim's settlement lands
   ok   the row records the attempt that actually settled it
   ok   the only allowed attempt is claimed
   ok   a spent budget offers no attempt to re-claim
   ok   the abandoned claim is recorded terminal with the expiry class
   ```

## Residual risks this round does not close

- **An object written by an attempt that then died before any row named it** is unreferenced and is
  not collected: the deletion cleanup enumerates the keys the rows hold, and a *replaced* pointer is
  cleaned up by the attempt that replaced it, but a process killed between the object write and the
  transaction that would publish it leaves an object no row ever named. The window is bounded by the
  upload limit and the probes' bucket listing would surface it. A prefix sweep or a bucket lifecycle
  rule is the upgrade path if it ever matters.
- **Ingestion jobs still have no lease.** A worker killed mid-attempt leaves its job `running`, and
  only a hand-made retry past `RAG_JOB_STALE_AFTER_SECONDS` recovers the parse stage; the other four
  stages have no retry endpoint at all. Cleanup intents now recover themselves; the ingestion lane
  does not, and that asymmetry is deliberate rather than accidental — a stage attempt is a provider
  call whose re-delivery is the queue's retry lane, while a cleanup has no message to be re-delivered.
- **A `failed` cleanup intent is terminal and cleared by an operator.** A `LeaseExpired` intent is
  recoverable in principle (the work is still owed), but there is no command that re-opens one;
  re-opening means clearing `status`/`attempt` by hand, the same contract the CLI documents for
  deterministic provider refusals.
- **The full acceptance run is outstanding.** `scripts/e2e-final.ps1` must be re-run before the
  overall change is declared accepted.
