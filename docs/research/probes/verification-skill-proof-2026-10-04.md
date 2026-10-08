# Verification skill: proof of the generated skill, 2026-10-04

The skill added at `.agents/skills/verify-rag-platform/` was proven by running its own instructions end
to end once — doctor, drive one mapped feature, evidence, cleanup — as the skill itself requires of a
freshly generated skill. Nothing here is a new probe run: this is the record that the driving recipe
works, with the two lanes that cost no provider calls.

## What ran

```text
pwsh -NoProfile -File scripts/doctor.ps1                 -> exit 0, worth driving (1 warning)
pwsh -NoProfile -File scripts/probes/auth.ps1             -> exit 0, 28.1 s   (features/auth-and-sessions.md)
pwsh -NoProfile -File scripts/probes/ingestion.ps1        -> exit 0, 76.0 s   (features/ingest-a-document.md)
pwsh -NoProfile -File scripts/doctor.ps1                 -> exit 0 (re-run after both lanes)
```

Both lanes ran standalone, so both prepared their own environment: no `-EnvironmentReady`, nothing on
8000/8001 beforehand. The Compose topology was already up (started by another process, 8/8 services
healthy) and was **not** torn down by either lane — the ownership rule the skill documents held.

## Evidence

- `auth`: CLI provisioning, duplicate-email refusal, login/`me`/logout, wrong password and unknown email
  both 401, `sessions.token_hash` equal to the SHA-256 of the issued token, and the absolute expiry poke
  (a past `expires_at` → 401, then a fresh login → 200).
- `ingestion`: all thirteen endpoints 401 without a session; a second user 404 (never 403) on every
  attempt; upload 201 with checksum/size/`source_object_key`; the RustFS read-back SHA-256 equal to the
  local file's; `version_ordinal` 2 on re-upload; 415/400/413 rejections with no row written (413 also
  answered before authentication on the over-sized anonymous request); extension case-insensitivity and
  the lying multipart `Content-Type`; 204 delete → `cleanup_intents` `pending` → `cleanup-pending` →
  `succeeded|1` → both raw objects `exists: false`; the same for a knowledge-base delete.
- Detached `.probe/auth/` (3 files) and `.probe/ingestion/` (12 files) still present after cleanup, and
  no API process left on 8000/8001. `.probe/` is gitignored, which is why this file is the durable record.

## Two defects this run found in the new doctor (fixed, then re-run)

1. `.env` carries no connection URL — only the Langfuse keys; `smoke.ps1` and the probes supply the
   Compose defaults. The first version therefore reported a `[FAIL]` for a database that was in fact at
   head, because a bare `uv run alembic current` dies with `RAG_DATABASE_URL must be set`. The doctor now
   applies the same default table to its own process (an existing environment value wins).
2. Alembic logs to stderr, so `2>&1` turned a log line into "the revision". The check now filters
   `INFO/WARNING/DEBUG` lines, and a schema behind the head is a `[WARN]` — the suite and a standalone
   probe migrate it themselves, so it only matters to a run handed an environment with
   `-EnvironmentReady`.

## Not covered by this proof

- The paid lanes (`parsing`, `chunking`, `indexing`, `retrieval`, `agent`, `graph`): they call
  PaddleOCR-VL, SiliconFlow embeddings/rerank/chat, or the graph LLM. Drive them with
  `pwsh -NoProfile -File scripts/smoke.ps1 -Only <lane>` (one shared environment) or standalone.
- The browser/UI surface: the frontend is prototype-only and has no harness, so the skill covers the
  HTTP API and SSE surfaces only.
- `scripts/e2e-final.ps1`, which stays the single acceptance run after the whole system is implemented.
