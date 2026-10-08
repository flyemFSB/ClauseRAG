# Baseline smoke run, 2026-10-03 (pre-refactor)

Commit `9a900fd` — the baseline before the module and composition refactor that
`docs/architecture/system-overview.md` now specifies. Command:

```text
pwsh -NoProfile -File scripts/smoke.ps1
```

Raw output: `.probe/baseline/smoke.out.log`, `.probe/baseline/smoke.err.log` (`.probe/` is gitignored).

| probe | wall clock | result |
|---|---|---|
| health | 10.9 s | passed |
| auth | 12.6 s | passed |
| migrations | 8.4 s | passed |
| ingestion | 38.9 s | passed |
| parsing | 106.0 s | passed |
| chunking | 230.3 s | passed |
| indexing | 168.7 s | passed |
| retrieval | 77.1 s | passed |
| agent | 44.4 s | passed |
| graph | 111.9 s | passed |
| observability | 145.3 s | passed |
| **queue** | 68.9 s | **FAILED** (exit 1) |

Total 1,075.0 s (probes 1,023.4 s, environment 37.3 s). The suite exited non-zero.

## The queue probe's failure (pre-existing)

```text
QUEUE PROBE FAILED: the task queue holds 1 messages
cleanup did not finish: the caller's Compose topology has 8 containers after this probe, expected 5
```

Two facts, both reproduced with the *unmodified* tree:

1. after the probe's own scenarios, the `taskiq` queue still holds one message — the probe's
   "nothing is left behind" assertion is red;
2. the probe's RabbitMQ restart path leaves 8 containers where it expects 5.

Every other lane's real-container contract passed, including the ones the refactor's exit criteria
name: duplicate delivery does not execute one job revision twice (queue probe steps 3),
transient retry within the finite budget and deterministic failure without retry (steps 4–5),
retrieval fusion and the evidence gate (retrieval probe), the SSE terminal-event contract and
cancellation (agent probe), and graph independence (graph probe).

## Policy for the rest of this work

Per the operator's direction of 2026-10-03, **no test or probe suite runs during development** —
only the static checks (`uv run ruff check`, `uv run ruff format --check`, `uv run pyright`). The
single real-container run is the final acceptance run at the end of the refactor
(`scripts/e2e-final.ps1`). This baseline is therefore the last recorded real-container result until
then, and the queue probe's red state is a **known pre-existing defect** that the final run has to
account for: either it is fixed by this refactor or it must be reported as the pre-existing failure
it is (it is not caused by, nor part of, the refactor plan's phases).
