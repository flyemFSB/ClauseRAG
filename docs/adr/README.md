# Architecture Decision Records

> **关于本文中的 `Evidence:` 与 `RAG_*` 行**：ADR-0001 到 ADR-0032 写作时，平台的验证机制是
> `scripts/probes/` 下的探针脚本套件，环境变量带 `RAG_` 前缀（`RAG_DATABASE_URL` 等）；两者后来都变了——
> 探针套件已随展示交付删除，验证入口改为容器路径
> （`docker compose -f infra/compose.yaml --profile app up -d --build --wait` 加 nginx 入口上的真实响应，
> 见 `docs/development/testing-strategy.md`），环境变量去掉了前缀（`RAG_DATABASE_URL` 现在就叫
> `DATABASE_URL`）。旧条目里的路径与前缀保留原文，因为那是做出该决策时的依据；它们在今天读起来是
> 死链与旧拼写，而不是失效的论证。

## ADR-0001: Python 3.12 runtime

Status: accepted

Use Python `>=3.12,<3.13` for the first release. The exact maintenance release is supplied by the environment/container and dependency lock.

## ADR-0002: Qdrant is the only vector store, one collection per embedding model

Status: accepted (the LightRAG-isolation half is withdrawn by ADR-0029)

Vector search is served by Qdrant and nothing else. Business child-chunk vectors live in their own
collection, created for one embedding model's width, separate from any other collection of the same
deployment (ADR-0019); a change of embedding model means a second collection beside it, never points of
a second width inside it.

The original decision also isolated LightRAG's entity/relation/chunk vectors from the business ones in
separate collections and workspaces. That half is withdrawn: the graph channel no longer exists
(ADR-0029), so there is nothing left to isolate.

## ADR-0003: PostgreSQL keyword retrieval first

Status: accepted

SiliconFlow's documented BGE-M3 endpoint is treated as dense-only. The first keyword channel uses PostgreSQL `pg_trgm`; its quality is evaluated against the final corpus before considering tokenized `tsvector` or an external search engine.

Refined by ADR-0008: the keyword channel runs `pg_trgm` with `LIKE` over the GIN trgm index plus `similarity()` scoring, not the `%` / `word_similarity` threshold operators.

## ADR-0004: RabbitMQ is the only business queue

Status: accepted

Taskiq uses RabbitMQ for worker tasks. Redis is not a queue. Aegra's runtime queue is not allowed to become the document-ingestion queue.

Refined by ADR-0024: there is no scheduler process; a scheduled task is what earns one.

## ADR-0005: Final E2E timing

Status: accepted

The full business E2E suite runs after implementation is complete, not during development. Development uses static checks and targeted contract/smoke probes.

## ADR-0006: UI/UX ownership boundary

Status: accepted

Visual and interaction design is maintained separately by another model. The core project owns only frontend engineering, accessibility/performance floors and API/SSE/citation contracts.

## ADR-0007: Two PostgreSQL drivers, split by workload

Status: accepted

Business persistence uses SQLAlchemy async over `asyncpg`. The LangGraph checkpointer uses `psycopg[binary]`: `langgraph-checkpoint-postgres` declares only bare `psycopg`, which ships no libpq wrapper and raises `ImportError: no pq wrapper available` until the `binary` extra is present. `AsyncPostgresSaver.setup()` needs no autocommit DSN parameter — the library sets the connection to autocommit itself (`from_conn_string` hands back a connection with `autocommit=True`) — and `setup()` is idempotent, so it can run on every start. On Windows the psycopg v3 async path must run on a Selector event loop; the default `ProactorEventLoop` fails with `InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode`. The async saver is imported from `langgraph.checkpoint.postgres.aio`, not from the package root.

Evidence: `docs/research/probes/live-dependency-contracts.md` (§1d); `docs/research/probes/python-resolution.md` (§(b), §(e)).

## ADR-0008: Keyword channel uses pg_trgm with LIKE, not the `%` threshold operator

Status: accepted

Against the real Chinese corpus, `similarity()` with the `%` operator at the default `pg_trgm.similarity_threshold = 0.3` fails as a pre-filter: the true substring query `知识库检索` scores only `0.2381` and yields no hit, while 2-character CJK queries score `0.0000` (`库检` = `0.0000`, `检索` = `0.0000`) and 4-character mid-string queries stall at `0.4000`, below the `0.6` default `word_similarity_threshold`.

The correct channel is `content LIKE '%q%'`, which keeps exact substring semantics and is accelerated by the GIN trgm index (measured as a Bitmap Index Scan with recheck), with `similarity()` / `word_similarity()` used only to score, never as a threshold filter. This refines and supersedes the pg_trgm choice of ADR-0003.

Recorded here as well: `postgres:18-alpine` does not provide pgvector — `CREATE EXTENSION vector` fails with `extension "vector" is not available` — so Qdrant stays the only vector store (ADR-0002).

Still open from the evidence: recall quality on the final corpus, the final `word_similarity_threshold` value, whether application-side tokenized `tsvector` is needed, and re-measuring index usage at corpus scale (the planner still chose a Seq Scan at 5000 rows).

Evidence: `docs/research/probes/live-dependency-contracts.md` (§1a, §1b).

## ADR-0009: RabbitMQ broker for Taskiq is `taskiq-aio-pika`

Status: accepted

Taskiq 0.13.0 core ships only in-memory, shared and ZeroMQ brokers. RabbitMQ comes from the separate `taskiq-aio-pika` 0.6.1 package (alpha, `aio-pika` as transport), whose `startup()` declares the durable quorum queue `taskiq` and the dead-letter queue `taskiq.dead_letter` for us.

RabbitMQ never creates a dead-letter target queue on its own: when `x-dead-letter-routing-key` points at a queue that does not exist, the message is silently dropped. The deployment topology must therefore declare those queues explicitly, and `taskiq` cannot be redeclared as a classic queue (`PRECONDITION_FAILED - inequivalent arg 'x-queue-type'`). This is consistent with ADR-0004 and details its implementation.

Evidence: `docs/research/probes/live-dependency-contracts.md` (§4a, §4b); `docs/research/probes/python-resolution.md` (§(c)).

## ADR-0010: Frontend toolchain is Vite+ (`vite-plus`)

Status: accepted

The `vp` CLI is the real command surface (project-local CLI: `create/migrate/dev/build/test/lint/fmt/check/pack/run/exec/preview/cache/config/hooks/staged/toolchain/install`); built-in commands cannot be overridden, and a `package.json` script runs through `vpr <script>` / `vp run <script>`. Official manual installation requires aliasing `vite` to `@voidzero-dev/vite-plus-core` and pinning `vitest` to the version Vite+ bundles; both are implemented in `frontend/pnpm-workspace.yaml` (`catalog` + `overrides` + `peerDependencyRules`), and `pnpm peers check` exits 0.

TypeScript stays on the 6.x line. TS 7.0.2 passed `tsc -b` / `vp check` / `vp build` locally, but it ships without `lib/typescript.js` (the programmatic API) and without `tsserver`, which are surfaces `vp check` and `vp build` do not cover. `vp test` exits 1 when no test file exists (Vitest default), so a bare `vp test` gate needs `--passWithNoTests` until real tests exist. Visual and page composition remain owned by the UI/UX owner (ADR-0006): the UI/UX layer is being redesigned, so this repository now carries only the frontend's engineering skeleton — the typed API/SSE clients, the toolchain configuration and the dev-server proxy contract — and no pages, styles or prototypes.

## ADR-0011: SiliconFlow provider contract is measured (was unproven while the account was in arrears)

Status: accepted

`GET /v1/models` returns 200 with 97 models, `BAAI/bge-m3` and `BAAI/bge-reranker-v2-m3` are both listed, and the key is valid (a bad key returns 401). The first measurement run hit `HTTP 402` (`{"code":30001,...}`) on every inference endpoint — embeddings, rerank, streamed and non-streamed chat, structured output and tools alike, and before any input validation — so the contract stayed unproven and the official documentation was the only basis for it. **After the account was funded the Re-run checklist was executed (2026-10-02) and the ingest lane's contract is now VERIFIED:**

* `POST /v1/embeddings` with `BAAI/bge-m3` answers **HTTP 200** with `data.length == input.length`, `data[i].index` = 0..n-1, and the whole key set of an entry is **`embedding` / `index` / `object`** — there is **no `sparse` or `lexical` field, so BGE-M3 is dense-only** and the dense-only decision of ADR-0003/0008 is settled rather than assumed. The vector is **1024-dimensional** (the documentation does not state a width for this model; 1024 is measured), and `usage` is `{prompt_tokens, completion_tokens, total_tokens}`, as documented.
* **Batch count: the documentation gives no limit.** 32, 64, 128 and 256 inputs all answered 200 with one vector each, and no 400 boundary was reachable. The deployment therefore bounds a request itself with `RAG_EMBEDDING_BATCH_SIZE` (default 16) and records that choice as its own, not as a provider constant (ADR-0019).
* `POST /v1/rerank` with `BAAI/bge-reranker-v2-m3` answers **HTTP 200** with `results[].relevance_score` **in descending order and inside [0,1]** (measured `0.974393367767334 / 0.000418916024500504 / 0.000301230873446912` for a mixed candidate set, and `0.8229097127914429 / 1.6180234524654225e-05` on a second run), `document: null` when `return_documents=false`, and `{"text": ...}` when it is true. An empty `documents` array is refused: HTTP 400, `{"code":20015,"message":"List should have at least 1 item after validation, not 0","data":null}`.

What stays unverified is exactly what this release does not depend on: `top_n` larger than the candidate count, the SSE frame shape, `json_object`/`json_schema` and tool calling. An account's balance is an operational fact, so `RAG_SILICONFLOW_API_KEY` (the bare `SILICONFLOW_API_KEY` of `.env`) is validated at startup like the OCR credential, and the ingest lane refuses to start without it rather than reporting every version as one it cannot embed.

Evidence: `docs/research/probes/siliconflow-contract.md` (U1–U5, U7, U8, U14 VERIFIED; U6, U9–U13 UNVERIFIED, with the Re-run checklist kept); `docs/research/official-docs-siliconflow.md`; `scripts/probes/indexing.ps1` step 9 re-measures the embedding field inventory and the rerank score semantics on every run.

## ADR-0012: LightRAG integration constraints

Status: withdrawn by ADR-0029

> The channel this ADR constrained no longer exists (ADR-0029). Its evidence file,
> `docs/research/official-docs-lightrag.md`, was deleted with it. The body is kept as the record of what
> was measured and decided while the channel existed.

Storage: the graph uses `lightrag.kg.pgtable_impl.PGTableGraphStorage` (officially recommended, no Apache AGE needed), KV and doc status use `lightrag.kg.postgres_impl.PGKVStorage` / `PGDocStatusStorage`, and vectors use `lightrag.kg.qdrant_impl.QdrantVectorDBStorage`.

Isolation rests on three layers: the hard-coded `lightrag_vdb_` collection prefix, separate collections, and payload filtering on `workspace_id`. `embedding_func.model_name` must be set, otherwise the collection name falls back to `lightrag_vdb_{namespace}` (no model/dimension suffix) with a warning.

Chunk-level source references come from `aquery_data(query, param)`, which returns structured retrieval results without LLM generation — so it is unaffected by the 402 gate — and is what maps graph hits back to business chunks. (The exact top-level keys of `aquery_data` in the pinned 1.5.7 still need a local source check: evidence §Missing evidence M9.)

Key constraint: a single query cannot be filtered by knowledge base or tenant in 1.5.x — one instance serves one workspace, multi-workspace is announced for 1.6.x, and the workspace is immutable once initialized. The integration must therefore assign one workspace per knowledge base or post-filter graph results through the mapping, and this stays recorded as an open risk.

A dimension mismatch raises `DataMigrationError` only when a collection with the legacy name exists. Rebuild uses the official `lightrag-rebuild-vdb`.

Evidence: `docs/research/official-docs-lightrag.md`; `docs/research/probes/python-resolution.md` (§(e)).

## ADR-0013: Aegra is not adopted; the agent runtime is LangGraph on our own FastAPI

Status: accepted

Aegra exists and is real (Apache-2.0, `aegra-api` 0.10.8, Python `>=3.12`, self-classified `Development Status :: 4 - Beta`), but `aegra up` brings its own PostgreSQL and Redis, and its tracing path is an OTLP fan-out rather than the Langfuse SDK.

Against this project's process boundaries in `docs/architecture/system-overview.md` (API / agent runtime / worker / scheduler), the SSE and citation contracts, the single business queue (ADR-0004) and the existing reuse of external dependencies, adopting it would add a second runtime and a second set of infrastructure for unclear benefit.

Decision: do not adopt Aegra. The agent runtime is LangGraph plus our own FastAPI process entrypoint. Re-evaluate only if a second real use case appears.

Evidence: `docs/research/official-docs-langfuse-aegra.md`.

## ADR-0014: Langfuse self-hosting components and isolation method

Status: accepted

Required components: `langfuse/langfuse` (web) + `langfuse/langfuse-worker` + PostgreSQL + ClickHouse (v4 requires `>= 25.12`, `26.4` recommended) + Redis/Valkey + S3. Reusing external PostgreSQL/Redis/S3 is officially supported, but isolation must be a **separate PostgreSQL database** (Langfuse hard-codes the `public` schema in the selected database and does not support a shared database with a separate schema), a separate Redis DB or key prefix, a separate bucket or prefix, and a separate `CLICKHOUSE_DB`. A single-container ClickHouse is officially classified as development-only (Community support). That single node also fixes one migration setting: `CLICKHOUSE_CLUSTER_ENABLED` defaults to `true`, which makes Langfuse issue its ClickHouse DDL `ON CLUSTER` and create Replicated engines — against a node with no Keeper the migration fails with `code: 139, There is no Zookeeper configuration in server config` and `langfuse-web` crash-loops on startup (`langfuse-worker` does not migrate, so it stays up). The compose file sets it to `false`, which is the value the official Docker guide documents for a single-container ClickHouse (https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse#docker). RustFS is not on the official S3 provider list (it falls under "Other S3-compatible providers" = Community), so a real-machine S3 preflight is required. `postgres:18-alpine` is above the officially recommended 16 and must be confirmed in Phase 5.

The application uses only the `langfuse` SDK 4.16.0 (`>= 4.7`) to emit observations and does not read Langfuse tables directly. Difference against the source: the official text forbids direct *writes* to Langfuse tables and declares the ClickHouse schema not a stable API contract; it does not ban read-only queries. This decision is deliberately stricter, and is justified by that schema-instability statement rather than by a claimed read ban.

Evidence: `docs/research/official-docs-langfuse-aegra.md`.

## ADR-0015: Server-side session cookies instead of bearer tokens or JWTs

Status: withdrawn (ADR-0033 removed login from the deployment: there is no cookie, no session row and
no account table left)

Authentication is an httpOnly cookie (`rag_session`) backed by a server-side session row in PostgreSQL. The cookie carries a 256-bit random token (`secrets.token_urlsafe(32)`); the database stores only its SHA-256 hex digest in `sessions.token_hash` (unique), and the raw token reaches neither storage nor a log line. A storage or log leak therefore cannot be replayed as a live session, and the `sessions` row is the single revocation point. `secure` is set whenever `RAG_ENVIRONMENT != "local"`, so the cookie cannot travel over plain HTTP outside development.

Why not a bearer token or a JWT: the client is a browser application served from the same site as the API, so it must hold the credential somewhere. A header token would need JavaScript-readable storage (localStorage/sessionStorage), which widens XSS exposure and pushes token plumbing into every request. A JWT would additionally make revocation a second mechanism (denylist or short TTL), while the platform already reads PostgreSQL for task status, documents and conversations — there is no availability argument for avoiding a session read.

Expiry is absolute (`RAG_SESSION_TTL_SECONDS`, default 7 days) and there is no sliding renewal: extending a session on every request would turn every read into a write and make session lifetime a function of traffic. Logout, and any later forced logout, sets `revoked_at`; `sessions` rows cascade with their user. Expired rows are not reclaimed by a background job — expiry is enforced only when a session is read (`Session.is_usable_at`), so expired rows accumulate until a later sweep removes them. A reaper is a known deferral, not implemented in Phase 1.

CSRF posture: the API relies on `SameSite=Lax` alone, with no CSRF token. The precondition is that the frontend and the API are served from the same site, so a cross-site form or `fetch` cannot attach the cookie to a state-changing request; state-changing requests are never simple GETs — they use POST, PATCH or DELETE, none of which a cross-site `Lax` request carries the cookie for — while `Lax` still attaches the cookie to top-level GET navigations, which are safe. If the frontend is ever deployed on a different site from the API, this decision must be revisited and a CSRF token added before that deployment.

Login answers the same 401 with the same body for an unknown email, a wrong password and an inactive account, and verifies against a per-process dummy Argon2id hash when no account exists, so neither response content nor timing enumerates accounts. There is no self-service registration and no password reset: accounts are provisioned by the operator CLI (`python -m cli create-user`), which enforces a 12-character password minimum. Passwords are hashed with Argon2id (argon2-cffi defaults: m=64 MiB, t=3, p=4) and a successful login re-hashes a stored hash whose parameters are weaker (`check_needs_rehash`). Rate limiting, account lockout and "remember me" are deliberately out of scope.

Evidence: `backend/src/api/auth.py`; `backend/src/application/identity/auth.py`; `backend/src/infrastructure/providers/password_hasher.py`; `backend/migrations/versions/0001_phase1_schema.py`; `scripts/probes/auth.ps1`.

## ADR-0016: Parse-stage parser routing and the parse-artifact contract

Status: accepted

**Parser selection and routing.** Office and PDF documents are read with `firecrawl-anydoc`: the PyPI distribution name is `firecrawl-anydoc` while the module it installs is `anydoc` (the `anydoc` name on PyPI is an unrelated Slack Q&A bot). It is MIT, declares no `Requires-Dist` at all, ships one Rust extension with no external binary and no model download, and converts all four binary formats deterministically (three consecutive conversions of one file hashed identically). HTML is read with `html-to-markdown`, which must be called with `extract_metadata=False` — the default prefixes the output with YAML frontmatter whose leading `---` a downstream splitter reads as a thematic break — and whose ATX headings and unescaped underscores keep `pg_trgm`-style identifiers intact for exact matching (`markdownify` emits Setext headings for `h1`/`h2` and escapes the underscore). Plain text and Markdown are decoded directly; images and scans go to PaddleOCR-VL. Rejected: `docling` (107 packages / 1026 MB, needs a Hugging Face layout model that is unreachable from this machine, and flattens PDF headings and tables), `unstructured` (132 packages / 1356 MB, 89.9 s for one DOCX, PNG needs another HF model, and it has no Markdown serializer at all), `markitdown` (the base package cannot read any of the four formats, and with extras a PNG comes back as an empty string — a silent degraded success), and a hand-assembled native-library stack (`pypdf`/`pymupdf`/`python-docx`/`python-pptx`/`openpyxl` have no Markdown serializer, so adopting them means writing and maintaining the multi-format-to-normalized-Markdown converter ourselves, which `ingestion-pipeline.md` forbids because parser internals are not reimplemented).

**Scope: URL ingestion, and with it the Firecrawl adapter, is not in the first release.** `docs/implementation-plan.md` listed a Firecrawl adapter at the end of Phase 2. The accepted inputs are the ones `system-overview.md` names — PDF, DOCX, PPTX, XLSX, TXT, HTML, image and Markdown — and a web URL is none of them, so no web route is wired and the upload endpoint takes a multipart file only. The decision is to defer the adapter with the feature rather than ship a second ingestion entry point no probe and no contract covers: `firecrawl-anydoc`, the local conversion library this release does use for Office and PDF, shares the vendor's name but is a different component with no network dependency, so it is unaffected. `docs/implementation-plan.md` and `docs/architecture/ingestion-pipeline.md` record the same scope.

**Immutability scope of the artifact keys.** `data-flow.md` states that object keys are immutable, and the derived artifacts honour it literally: a parse artifact is written to `parsed/{document_version_id}/{job_id}/document.md` and a chunk artifact to `chunks/{document_version_id}/{job_id}/chunks.jsonl`, so the attempt that wrote an object is part of its name and no two attempts of a version ever share one. The database row is the pointer a reader follows (`parse_artifacts.markdown_object_key`, `chunk_artifacts.object_key`, and `document_versions.markdown_object_key` for the version's current one). This is what makes a late stale worker harmless at the byte level and not merely at the row level: it cannot overwrite the live revision's object, and because its own object is unreferenced it deletes it when its completion is refused. Publishing a pointer has a second half, and it is the same rule read forwards: the object the previous pointer named is deleted once the transaction that moved the pointer has committed, because from then on no row names it — the store reports the replaced key and the stage deletes it, for the parse and chunk artifacts alike. Each `document_version` still has exactly one `parse_artifacts` row (unique on `document_version_id`) and one chunk artifact row, and the version's pointer is the one the last successful attempt published. What a reader gets is a fixed point: an object whose key is published is never rewritten, so the digest and size the row records are true for as long as the object exists. An object written by an attempt that then died before publishing anything is unreferenced and is removed by the deletion cleanup only if the row survived to name it — a hard kill between the write and the row is the one residue, bounded by the upload limit and reported by the probe's bucket listing.

**What a page number can and cannot be.** `anydoc` reports no page number and no page marker for PDF, DOCX, PPTX or XLSX (`Block.anchor` is `None`, or a title string in PPTX, never a page), so on the text-PDF route `page_start`/`page_end` are null; a page can only be attributed through `page_spans` (one element per page — the OCR route does have real page numbers, because `layoutParsingResults` holds one element per page) or derived from the line numbers of the normalized Markdown. This is written down explicitly because the citation contract requires a location.

> **Revised by ADR-0027 (2026-10-06).** The page coordinates and the `page_spans` map described here
> are dropped. What stands is the observation that only the OCR route can report a page at all, which
> is why `page_count` is the only page fact that survives, and why the citation contract is satisfied
> by a line range plus the quote instead.

**PaddleOCR-VL parameter whitelist.** An `optionalPayload` key the service does not define is silently ignored and still answered `200` (measured). A misspelled parameter would therefore look like success, so the adapter must never rely on the server to reject a wrong name: it sends no optional payload at all — layout detection, deskew and running header/footer removal are the service's documented defaults — and any parameter added later is only added once its spelling has been verified against the reference.

**One parse attempt, two records, and each has one job.** A version's parse result is written twice in the same transaction, and the split is deliberate rather than duplicated state. `document_versions` carries the **current pointer and the static metadata `data-flow.md` requires of a version** (`document_id`, `document_version_id`, `source_object_key`, `markdown_object_key`, `parser_name`, `parser_version`, `mime_type`, `checksum`, `page_count`): it is what every version read already has in hand — the document list, the version list, the upload response — with no second query, and `markdown_object_key` is the pointer the chunk stage follows. `parse_artifacts` carries **the facts of that version's parse attempt** (the same parser identity, plus `page_spans`, the parser `warnings`, and the digest and size measured from the stored object), which have no home on the version and are exactly what the ingestion verification gate asks to be visible. Neither record is deleted: dropping the version columns would contradict `data-flow.md`'s required static metadata and force every read to join the artifact table, while dropping the artifact row would leave page attribution and warnings stored nowhere — `page_spans` is the only page source the OCR route has, and the citation contract needs a location. They cannot diverge while they are written by one transaction, and the artifact is **read** as well as written: `GET /api/v1/document-versions/{version_id}` answers the version with a `parse_artifact` summary (parser name and version, page count, page spans, warnings, checksum, size) and never with the object key, so "the artifact is visible" is an API contract instead of a psql session.

> **Revised by ADR-0026 (2026-10-05).** The second paragraph above is superseded: the version row no
> longer carries `markdown_object_key`, `parser_name`, `parser_version` or `page_count`, and
> `parse_artifacts` is the one row that owns the parse result. The requirement it cites is unchanged —
> `data-flow.md`'s static metadata is still required and still returned — but it is stored once rather
> than twice, because two rows written by one transaction are two rows a future writer can disagree
> with. The reads that used the version's copy (the deletion paths reporting the object keys they
> removed) read the artifact table instead, and no version read needs a join for a field it actually
> returns.
>
> **Revised again by ADR-0027 (2026-10-06).** `page_spans` is dropped along with the page coordinates
> it existed to fill, so the artifact row now carries the parser identity, `page_count`, the warnings
> and the measured digest and size — not a page map.

**A provider failure is not a statement about the document.** The three failure classes of `domain/parsing.py` are the whole mapping, and the OCR adapter's code table is what feeds them. An **unreadable document** (`UnparseableDocumentError`: an unknown or unsupported format, an encrypted file, bytes that are not UTF-8, the provider's own `10004` file-format code) is a property of the bytes: the same file fails the same way on any account, a retry changes nothing, and the version goes to `manual_retry_required` for a human. An **operational failure** (`OcrProviderError`: missing or wrong credential, exhausted quota, a wrong model or request parameter, an unknown answer code, a base URL that answers 400/404) says nothing about the bytes — the measured wrong-token call and the successful one carry identical images — so the version goes to `parse_failed` with `OcrProviderError` as its `error_class`, which is the state a human may restart after fixing the environment; parking it at `manual_retry_required` would tell an operator to inspect a document that was never the problem, and the queue would never look at it again. A **transient failure** (`TransientParseError`: a full submission queue, a rate limit, 5xx, a timeout) is retried by the queue while the job's attempt budget lasts. The credential itself is validated where the process starts: `PADDLEOCR_API_KEY` is a required setting, and a missing, blank or still-`replace-me` value fails configuration before any work begins, so a misconfigured environment cannot present itself as an unreadable document (the error names the setting, never its value).

**MIME detection.** `mimetypes.guess_type` is not used: on Windows CPython 3.12 it returns `None` for `.webp`. The accepted extensions are mapped to MIME types by an explicit table instead.

Evidence: `docs/research/probes/parser-contracts.md` (§A–§E); `backend/src/domain/parsing.py`; `backend/src/domain/normalization.py`; `backend/src/infrastructure/parsing/anydoc_parser.py`; `backend/src/infrastructure/parsing/html_parser.py`; `backend/src/infrastructure/parsing/plain_text_parser.py`; `backend/src/infrastructure/parsing/paddleocr_parser.py`; `backend/src/infrastructure/config/settings.py`; `backend/src/application/ingestion/parse.py`; `backend/src/api/knowledge_schemas.py`; `backend/migrations/versions/0002_parse_artifacts.py`; `scripts/probes/parsing.ps1` (including the bad-credential classification gate).

## ADR-0017: Queued parse job semantics

Status: accepted, except the retry and delivery halves, which ADR-0030 supersedes

Superseded part: retry is no longer the official middleware and delivery no longer happens only after
the commit plus a manual retry request. What ADR-0030 keeps from this record is the conditional claim,
the revision-as-identity rule, the claim-token completions, the retry endpoint and the stale-`running`
policy. The rest below describes the lane as it was before ADR-0030.

**Where the queue lives.** The queue is infrastructure. Application code depends on one port,
`JobDispatcher.dispatch_stage(stage=..., document_version_id=..., job_id=...)`, implemented by
`infrastructure/queue/job_queue.py` on `taskiq-aio-pika` and wired by the composition root; neither
`domain/` nor `application/` imports taskiq, aio-pika or aiormq. A message carries two identifiers
and nothing else. The topology is the library's own (ADR-0009): the durable quorum queue `taskiq`,
the durable quorum queue `taskiq.dead_letter` it dead-letters into, and the durable **classic**
queue `taskiq.delay_queue` that the retry backoff needs — per-message TTL is not supported on
quorum queues, which is why that one is classic.

**Idempotency is a conditional write, not a check.** `(document_version_id, stage, revision)` is
the identity and a retry appends a revision instead of editing history, so a delivery claims its
job with a single `UPDATE ... WHERE id = :job_id AND status = 'pending'` that also marks the
version `parsing` and counts the attempt. Zero affected rows means the job is running elsewhere,
already finished, or superseded, and that delivery returns without touching the document, the
artifact or the object store. Two deliveries of one revision therefore cannot both work, and a
repeated delivery of a finished job is a no-op rather than a second parse.

**Retry is the official middleware, and the only retry layer there is.** Only
`TransientParseError` is retried (`types_of_exceptions`), so an unreadable document and an
operational OCR failure are never retried; `SmartRetryMiddleware` republishes through the delay
queue with jitter and a capped backoff. The budget and the delay are **not** task labels: they come
from the worker's settings (`RAG_JOB_MAX_ATTEMPTS`, `RAG_JOB_RETRY_DELAY_SECONDS`,
`RAG_JOB_RETRY_MAX_DELAY_SECONDS`, shared by every stage because there is one middleware and one
queue). The middleware and the application share those numbers, but
**the one that seals the lane is the job row**: the middleware counts retries per *message* (its
`_retries` label starts at 0 for every message, and the retry endpoint publishes a fresh one), while
`attempt` lives on the job row and `claim_parse_job` only takes a job that is still `pending`. A
delivery beyond the budget is therefore refused by the claim and does nothing, which is why a
repeated retry request cannot buy extra attempts even though it can publish another message. The
adapters retry nothing of their own: one delivery is one provider call, so the row's `attempt` is
the number of calls and the delay between them is the one the settings describe — linear in the
attempt number (`min(delay × retries, max)` from the library's own source, not the doubling the
name suggests). A transient failure whose job still has an attempt left returns the job to `pending`
for the retry already on its way; the last one writes `failed`/`parse_failed`. An unexpected internal
failure is recorded as `parse_failed` without a retry, because the middleware will not retry it
either and a terminal state an operator can see beats a job stuck `pending` with no message.

**The retry lane is verified by its contract, not by the clock.** The properties that make the lane
finite are the attempt count the job row records, the number of retries the worker schedules, and
the delay each retry was scheduled with — read from the middleware's own line (its `_retries` label
and the calculated delay are the retry's metadata, and the delay queue carries them as the message's
per-message TTL). The probe therefore asserts those, with a deliberately small
`RAG_JOB_RETRY_DELAY_SECONDS`/`RAG_JOB_RETRY_MAX_DELAY_SECONDS` pair: a bounded attempt count, one
scheduled retry per attempt left, and delays that are linear in the retry number, capped by the
configured maximum and never more than the middleware's one second of jitter above it — strictly
increasing, which is what "a backoff and not an immediate redelivery" means. Sleeping through the
configured backoff and timing it proves nothing these numbers do not, and on the shipped defaults it
costs ninety seconds per run.

**Dispatch happens after the commit, and a failed dispatch is not a failed upload.** The upload
transaction commits first, then the job is published. If publishing fails the request still answers
201 with the version and its `pending` job — those rows are true, and 503 would invite the caller to
upload the same file again — and the failure is logged as a structured event with the transport
error's class only, never its text, which can quote the connection URL and its password. The job
stays `pending` and is recoverable through the retry endpoint, which dispatches a pending job again.

**The retry endpoint.** `POST /api/v1/document-versions/{version_id}/retry` is owner-scoped (404 for
someone else's version) and answers 202 with the new revision when it appended one, 200 when it
changed nothing, and 409 when the version's status is outside
`manual_retry_required`/`parse_failed` — a `parsed` version is refused explicitly instead of being
silently rebuilt. The body names the outcome, so the two 200 cases are not the same answer: a
`pending` job already covers the request (`queued` — the endpoint publishes it again, because a job
whose message never reached the broker is the one case it can still recover), or an attempt is
executing at that moment (`running` — nothing was appended and nothing was dispatched, so the caller
cannot mistake a live worker for a queued retry). `created` is true for the two outcomes that
appended a revision: `created`, and `stale` (below). A retry appends a revision and puts the version
back in its entry state (`uploaded`); columns recording a previous successful attempt are left alone,
so a version that was parsed and later failed keeps naming its last artifact until the next
successful attempt replaces it.

**A `running` job has a bounded life, and that is what makes a dead worker recoverable.** A worker
killed mid-attempt leaves its job `running` with no message in flight, so nothing will ever finish
it and the version stays `parsing`. A retry request therefore compares the job's `started_at` with
`RAG_JOB_STALE_AFTER_SECONDS`: inside that bound the job is reported as `running` and left alone;
older than that it is treated as abandoned, and a new revision is appended over it, which puts the
version back in `uploaded` and dispatches it again. The bound is safe because an attempt is itself
bounded by `RAG_PARSE_TIMEOUT_SECONDS`, so nothing can still be executing past it — the default
staleness bound is twice the default parse deadline, and a deployment that raises the parse deadline
must raise this one with it. The abandoned `running` row is kept as the record of an attempt that
never reported an outcome, and it is written terminal (`failed`, `AbandonedAttempt`) in the same
transaction that appends its replacement: the row, not the elapsed-time assumption, is what refuses
the delivery it belonged to. No reaper process runs; recovery is the operator's explicit request,
and `docs/operations/local-development.md` describes it.

**Every attempt write carries the claim token it was handed.** The ingestion store's completions and
failure writes address the identified job — `UPDATE ... WHERE id = :claimed_job_id AND status =
'running'` — so a delivery that returns after a stale retry replaced its revision records nothing at
all: no artifact, no version status and no successor job. The store answers such a write with
`superseded` (a newer revision owns the version), `vanished` (the version was deleted while the
attempt ran) or `recorded`, and a stage acts on that answer instead of assuming its own success. The
objects a superseded attempt wrote are its own — each artifact key carries the identifier of the
attempt that wrote it — so the same answer is what lets it delete them: nothing else can refer to
them, and the revision that replaced it published its own key. A superseded attempt is therefore
both a fence and a cleanup, and a *successful* attempt cleans up after itself in the same way: the
key its pointer replaced is reported by the store and deleted once the pointer's transaction has
committed.

**A cleanup claim is a lease with an attempt token.** The cleanup lane claims one intent by a
conditional write and settles it with `UPDATE ... WHERE id = :intent AND status = 'running' AND
attempt = :claimed_attempt`; an intent whose lease (`RAG_CLEANUP_LEASE_SECONDS`) expired is
re-claimed as the next attempt, and the settlement of the worker that died is refused instead of
writing over the newer claim's row. Re-claiming is safe because every step of a cleanup is
idempotent, and a claim that dies with the attempt budget already spent is recorded `failed` with
`error_class = LeaseExpired` — the state that names what happened — rather than staying `running`
for good. The lease is deliberately far above any legitimate attempt (a large deletion issues one
call per object): a premature re-claim costs duplicated deletes and a reported refusal, while a
lease that never expires costs the cleanup itself.

**Known limits.** A graceful drain is not exercised on Windows: the probe stops the worker with
`taskkill`, so `Receiver.listen` finishing its running tasks is not covered there. An *ingestion*
worker killed mid-attempt still leaves its job `running`, and only a hand-made retry past
`RAG_JOB_STALE_AFTER_SECONDS` recovers it: there is no automatic reaper for the ingestion jobs, and a
version whose worker died looks like a running attempt until that bound passes. Cleanup intents have
their own lease and are recovered without an operator (above).

Evidence: `docs/research/official-docs-taskiq.md`; `backend/src/infrastructure/queue/job_queue.py`;
`scripts/probes/hardening.py` (the fence, the durable cleanup, and the cleanup lease: a claim inside
its lease is not handed out twice, a claim past it is re-claimed as the next attempt, the dead
worker's settlement is refused, and a spent budget records the expiry instead of staying `running`);
`backend/src/application/ingestion/document_ingestion.py`;
`backend/src/infrastructure/{document_store,ingestion_store,chunk_store}.py`; `scripts/probes/queue.ps1`
(topology, duplicate delivery, one-attempt deterministic failure, three-delivery transient failure
with the scheduled delays read back from the middleware, retry endpoint idempotency and the 409
refusal, a stale `running` job replaced by a new revision, and an upload that survives an
unreachable broker); `scripts/probes/migrations.ps1` (the migration history on an isolated
database).

## ADR-0018: Block-aware chunking, derived chunk identifiers and the stage chain

Status: accepted

**Splitting is block-aware, and every rule is stated as a boundary.** The chunk stage reads the
normalized Markdown of one version and cuts it into **parents** (the structural section an agent is
given as context) and **children** (the retrieval unit that is embedded, retrieved and cited). Both
levels are cut on Markdown block boundaries — heading, paragraph, list, table, code, image — and
never by character offset, because a character splitter destroys exactly the structure the citation
and retrieval contracts depend on. The initial budgets of `docs/architecture/data-flow.md` are the
constants of `domain.chunking`: a child is filled to `CHILD_MIN_TOKENS = 200` and
closed before `CHILD_MAX_TOKENS = 500`, a parent to `PARENT_MIN_TOKENS = 800` and closed before
`PARENT_MAX_TOKENS = 1600`. A heading starts a new unit at both levels: neither a child nor a parent
spans two `heading_path` values, so a section is never mixed into its neighbour. Three block types
need their own rule, because their internal structure is what carries meaning:

* **a table** is split only at row boundaries and **repeats its header rows (and the alignment row,
  where there is one) in every shard**, so no shard is a continuation without its column names; the
  shard's recorded line range starts at the header line it carries again;
* **a fenced code block** is split only at line boundaries and **re-adds the same fence and info
  string** to every shard, so each shard is a valid code block on its own;
* **a list** is split only between items, never inside one.

Blank lines are skipped, no chunk is ever empty, and a version whose Markdown holds no block at all
raises `UnchunkableDocumentError` rather than producing a version with no chunks — a version can
never reach `ready` without them.

**A block that cannot be cut below the provider ceiling is cut deterministically, and says so.** A
single line longer than BGE-M3's documented `8192`-token input ceiling has no boundary to cut on.
It is halved recursively until every part measures at or below `CHUNK_TOKEN_CEILING`, the attempt
records a warning naming the line and the split, and the warning is stored in `chunk_artifacts` and
logged. Halving rather than a character budget is deliberate: a token count is not linear in
characters, so a character window could still exceed the ceiling, while a measured bisection cannot.
The provider's own limit is still validated where the provider is called — at the embedding adapter
of the later lane — because a different tokenizer can count the same text differently.

**Identifiers are derived, not generated.** `parent_id` and `child_id` are
`UUID5(document_version_id, kind, ordinal)`, so rebuilding one version produces the identifiers it
had before instead of a second set that looks like new content. The price is that a **cut-configuration
change is a rebuild, not a migration**: changing a budget changes which chunks exist while the
ordinals (and therefore the identifiers) stay the same, so the chunk stage *replaces* the version's
chunks — it deletes the old rows and inserts the new ones in one transaction — and the artifact is
overwritten under its fixed key. Any consumer that stored a `child_id` therefore has to treat a
configuration change as a re-index, which is the same statement ADR-0016 makes about the parse
artifact and the same one the embedding lane will make about vectors.

**Token counts are a budget, and the counter is an adapter.** `tiktoken`'s `cl100k_base` counts the
tokens of the budgets, and it is a *direct* dependency (`pyproject.toml`) because the number is a
product decision rather than a transitive accident. It is **not** BGE-M3's tokenizer: BGE-M3 uses
the XLM-R SentencePiece vocabulary, which is not available in this process, so the two counters
disagree and only the budget depends on this one. Measured on this machine: `cl100k_base` charges
11 tokens for the 11 CJK characters `知识库检索增强生成系统` and 10 tokens for the 43-character English
sentence `The quick brown fox jumps over the lazy dog.` — about one token per CJK character, which
is the same order the XLM-R family uses for common Han characters, so the approximation is
reasonable for this corpus' Chinese text and conservative for its Latin text. It is treated as an
approximation in both directions rather than as a bound: the chunker keeps its own ceiling, and the
embedding adapter is where the provider's limit is enforced. The counter is reached through
`domain.chunks.model.TokenCounter`, implemented by `infrastructure/parsing/token_counter.py`, so
neither `domain/` nor `application/` imports the tokenizer. The first use of the encoding downloads
and caches its vocabulary file (measured: 10 s on this machine, then cached), so an offline
deployment has to pre-seed `TIKTOKEN_CACHE_DIR`.

**A page is only ever what the parser reported.** `page_start`/`page_end` come from the parse
stage's `page_spans` and from nothing else: a chunk records the first and last page its lines fall
on, and where the parser reported no page — the whole `anydoc` route for PDF, DOCX, PPTX and XLSX —
the fields stay `null`. A page is never derived from the document's length, from a chunk ordinal or
from a character offset, and `line_start`/`line_end` always address the normalized Markdown, which
is the only text the parse stage stored. A shard of a split table records the header line it repeats,
so its range says where its text came from.

> **Revised by ADR-0027 (2026-10-06).** Superseded: `page_start`/`page_end` and the `page_spans` map
> they came from are dropped. What survives of this paragraph is the rule that a location is never
> guessed — `line_start`/`line_end` address the normalized Markdown and the quote addresses the text,
> and neither is derived from the document's length, a chunk ordinal or a character offset.

**The chunk artifact is a row and an attempt-scoped key, exactly like the parse artifact.** The stage
writes `chunks/{document_version_id}/{job_id}/chunks.jsonl` — one JSON object per line, a parent
followed by its children, field names equal to the column names — verifies the size with
`head_object`, then reads the object back and hashes it. The digest recorded in `chunk_artifacts` is
the digest of the bytes that came back, never the metadata this process wrote, and the row also
carries the counts and the warnings of that attempt, so the record itself says what it claims to
contain. A rebuild replaces the row and publishes its own object (ADR-0016's rule, applied to the
second artifact). Reading is verified too: the stage cuts the Markdown only after the bytes match
the digest and the size its parse artifact row records, so a stored artifact that disagrees with the
row is a classified `manual_retry_required` failure rather than a chunk set cut from unnamed text. The migration
that creates the tables also enables `pg_trgm` and indexes `child_chunks.content` with GIN trigrams:
that index is the foundation of ADR-0008's keyword channel, and `postgres:18-alpine` ships
`pg_trgm` as a trusted extension.

**Jobs are dispatched by stage, and a stage's success appends the next stage's job.**
`JobDispatcher.dispatch_stage(stage, document_version_id, job_id)` replaces the parse-only dispatch,
the single Taskiq task `rag.run_ingestion_stage` carries the stage name beside the two identifiers,
and `DocumentIngestion` maps the stage to its handler. The claim, the idempotency rule, the failure
classification and the finite retry budget are unchanged (ADR-0017): a claim is still one conditional
`UPDATE ... WHERE status = 'pending'`, the budget is still counted in the job row, and the middleware
still retries only the stages' transient classes (`TransientParseError`, `TransientChunkError`). What
is new is the chain: `complete_parse` appends a `chunk` job at `pending`/next revision **in the same
transaction** as the parse artifact, and the delivery publishes that job **after** the attempt
returned — that is, after the commit. A publish that fails is logged and swallowed, because the
attempt itself succeeded and the row stays `pending`: the same recoverable state an upload whose
dispatch failed leaves. The operator path publishes nothing at all, which keeps `run-stage` outside
the queue (ADR-0017). The settings that carried a parse-only name (`RAG_PARSE_MAX_ATTEMPTS`,
`RAG_PARSE_RETRY_DELAY_SECONDS`, `RAG_PARSE_RETRY_MAX_DELAY_SECONDS`) are renamed to
`RAG_JOB_*` for the same reason: one queue, one middleware, one budget. `RAG_PARSE_TIMEOUT_SECONDS`
stays parse-specific and `RAG_CHUNK_TIMEOUT_SECONDS` bounds the chunk attempt.

**A version status names the stage that last ran, and `ready` is the only status that means the
pipeline finished.** `parsing` while a parse attempt runs, `parsed` after it succeeds, `chunking`
while the chunk attempt runs and — in this release — after it succeeds, because the stages that
follow (`embed`, `index`) do not exist yet and the ingestion contract makes `ready` mean *parse,
normalized Markdown, chunks and the business vector index are all durable*. A successfully chunked
version is therefore left at `chunking` on purpose rather than promoted to a status it has not
earned. The failure statuses follow the same split as the parse stage: a Markdown artifact that
cannot be read is `manual_retry_required` (only a human can restore it), everything else is
`chunk_failed`, and a transient failure inside the job's budget returns the job to `pending` with
the version still at `chunking`. Known limit, recorded rather than hidden: the hand-made retry
endpoint still addresses the parse stage only, so a `chunk_failed` version is recovered with
`run-stage chunk` — the operator path of ADR-0017, applied to the second stage — until a later lane
extends the endpoint.

**The operator command is `run-stage <stage> <document_version_id>`.** `parse-version` is deleted
rather than aliased: a second stage would have made the old name a lie, and a compatibility alias is
not a thing this project keeps. The command refuses a stage it does not implement before it starts
work, and on failure it prints the classification the job row records (the version status, the job
status and the error class) so the exit code and the database agree.

**Not in this ADR, deliberately.** The embedding adapter, the Qdrant collection and payload index,
and upsert/delete/rebuild of vectors belong to the lane that follows; the chunk artifact is not
exposed through the version detail API (the parse artifact is, per ADR-0016) because nothing consumes
it yet; and the `chunk` stage appends no `embed` job until that stage exists.

Evidence: `backend/src/domain/chunks`;
`backend/src/infrastructure/parsing/token_counter.py`;
`backend/src/application/ingestion/chunk.py`;
`backend/src/application/ingestion/document_ingestion.py`;
`backend/src/application/ingestion/failures.py`;
`backend/src/infrastructure/{ingestion_store,chunk_store}.py`;
`backend/src/infrastructure/queue/job_queue.py`;
`backend/migrations/versions/0003_parent_child_chunks.py`; `scripts/probes/chunking.ps1`
(every accepted format chunked with parents, children and no orphan child; artifact digest, line
count and every chunk compared field by field with the database; table shards with a repeated
header, code shards with a re-added fence, list shards at item boundaries; determinism across two
runs and against the planner run outside the pipeline; real pages on the OCR route and null pages
on the `anydoc` route; the token distributions and the ceiling; the parse -> chunk chain with no CLI
call; a repeated chunk delivery that changes nothing; and the delete of one document and of the whole
knowledge base); `docs/research/probes/live-dependency-contracts.md` (§1a, `pg_trgm` on
`postgres:18-alpine`).

## ADR-0019: The business dense index, the embed and index stages, and the embedding adapter

Status: accepted

**One collection, one dense vector, one point per child chunk.** The business child chunks live in a
single Qdrant collection (`RAG_QDRANT_COLLECTION`, default `rag_child_chunks`), created with one
**unnamed** dense vector of the configured width (`RAG_EMBEDDING_DIMENSION`, default 1024 — the width
`BAAI/bge-m3` was measured to answer, ADR-0011) at **Cosine** distance. Named vectors are not used:
a point has exactly one embedding here, and naming it would only add a `using=` name to every query.
The collection is separate from every other collection of the same deployment, which is ADR-0002's
physical isolation, and the module that writes it never touches anything else.

**The point identifier is the child identifier.** `child_id` is `UUID5(document_version_id, kind,
ordinal)` (ADR-0018) and Qdrant accepts a UUID string as a point id, so no second identifier has to
be kept in step with the business one and a rebuild addresses exactly the points it addressed
before. The payload is the thirteen-field set `docs/architecture/ingestion-pipeline.md` fixes, in
that order, built in one place (`domain.embedding.child_payload`) and asserted by the
indexing probe against a stored point. Four of the identifier fields and `block_type` carry a payload
index — `uuid` for `knowledge_base_id`, `document_version_id`, `document_id` and `parent_id`,
`keyword` for `block_type` — because those are the fields the retrieval contract filters on and
Qdrant indexes a payload field only when told to (ADR-0003/0008; `docs/research/official-docs-qdrant.md`).
Indexes are created before the first point is written, which is the documented order.

**The lane is two stages because the gate must be a measurement.** `embed` reads one version's child
rows, embeds them in batches and upserts the points; `index` ensures the collection and its payload
indexes exist, counts the version's points **exactly**, compares that number with the version's
`child_chunks` row count, and only then marks the version `ready`. The comparison is the point of the
split: a stage cannot certify its own write, and `ready` is the documented statement that parse,
normalized Markdown, chunks *and* the vector index are durable. A mismatch records
`VectorCountMismatchError` on the version as `index_failed`; it is **not** retried by the queue,
because a retry of the index stage would observe the same counts — the repair is to run the embed
stage again, which the operator path does under one command (`reindex`). Neither stage adds a table:
what the index holds is derived from `child_chunks` and is verified against it, so a row recording
"the index was written" would be a second claim about state the count already proves.

**The provider boundary is a thin native `httpx` adapter, not `langchain_openai`.** Both were
available (both are already dependencies). `langchain_openai` 1.6.7's `OpenAIEmbeddings` carries
`max_retries=2` of its own by default and batches internally at `chunk_size=1000`, and with
`check_embedding_ctx_length=True` (the default) it tokenizes input with `tiktoken` before sending it
— three behaviours this lane has to own itself: a second retry layer contradicts ADR-0017's single
retry lane, an internal batch size contradicts a configured one, and a tokenizer chosen by the
client library is not the provider's tokenizer. `SiliconFlowEmbeddingProvider` calls
`POST {base_url}/embeddings` once per batch with an explicit `httpx.Timeout`, classifies the
response, and enforces the two facts this lane cannot proceed without: **exactly one vector per
input text** (in `index` order, so a reordered response cannot be paired with the wrong child) and
**exactly the configured width** — a provider answering another width fails the attempt instead of
writing a wrong-width vector into a collection cosine distance cannot repair afterwards. 400/401/
402/403 and shape violations are `EmbeddingProviderError` (operational, not retried); 408/409/425/
429/5xx and transport failures are `TransientEmbeddingError` (retried inside the job's attempt
budget); no adapter retries, and neither the key nor the `Authorization` header ever reaches a log
line or an error message.

**Batch size is this deployment's decision, and it is recorded as such.** The provider documents no
input-count limit (only per-text token limits; measured up to 256 inputs with no boundary) and
Qdrant documents only a byte cap inside strict mode, which this release does not enable. So
`RAG_EMBEDDING_BATCH_SIZE` (default 16) is deliberately conservative and stated as ours: one number
bounds both the texts in one provider request and the points in one upsert. `ensure_ready` also
refuses to write into an existing collection whose vector width differs from the configured one — a
changed model needs a collection of its own, which is why the name is configuration.

**Rebuild is re-embedding, and deletion is three-store-consistent.** The vectors exist nowhere but
in the index, so a rebuild cannot be read back from PostgreSQL: `python -m cli reindex
<version_id>` embeds the version's children again and then verifies the count, which is the entry
point for a version whose points were removed by hand or built by an older model. Deleting a
document removes its rows first, and the same transaction reports the object keys *and* the version
identifiers it removed, so the RustFS objects and the Qdrant points (`document_version_id` filter)
are cleaned with the scope the commit produced; deleting a knowledge base filters points by
`knowledge_base_id`. A failed point deletion is reported at error level rather than swallowed: a
point whose row is gone is a chunk a dense retrieval can still return, while a row without its point
is a hole the count check catches. Nothing on this path fails the request, because the rows the
caller asked to remove are already gone.

Evidence: `docs/research/official-docs-qdrant.md` (collection, payload index, filtering, batching,
deletion, point ids, collection info, `query_points`); `docs/research/official-docs-siliconflow.md`
(embeddings and rerank response shapes incl. the documented batch gap);
`docs/research/probes/siliconflow-contract.md` (U1–U5, U7, U8, U14 VERIFIED with the raw values);
`backend/src/domain/embedding.py`; `backend/src/application/ingestion/embed.py`;
`backend/src/application/ingestion/index.py`; `backend/src/application/cleanup/service.py`;
`backend/src/infrastructure/retrieval/qdrant_index.py`; `backend/src/infrastructure/providers/siliconflow_embeddings.py`;
`scripts/probes/indexing.ps1` (the queue chain to `ready` with no CLI call; the collection's real
width, distance and payload indexes read back from the client; every version's type count equal to
its row count and every payload field compared with its row; the dimension guard refusing a 1023-wide
configuration with no point written; two knowledge bases proven not to see each other under a
filtered search; repeated embed and index deliveries changing nothing; a document delete leaving no
row, no object and no point; a hand-deleted point set restored byte-identically by `reindex`; and the
live dense-only and `relevance_score` evidence).

## ADR-0020: The HTTP surface is two processes: the business API and the agent runtime

Status: accepted

**Decision.** The platform serves HTTP from two processes, each built by its own factory from its own
process composition, with the same session cookie and the same middleware:

* the **API process** (`python -m api.main`, `RAG_API_PORT`, default 8000) serves
  identity, knowledge bases, documents, versions, ingestion jobs and the health endpoints;
* the **agent runtime** (`python -m agent_runtime.main`, `RAG_AGENT_RUNTIME_PORT`, default
  8001) serves the same health and auth endpoints plus the chat surface: conversations, the streamed
  run and the retrieval diagnostics read.

Both use the `/api/v1` prefix. Authentication is unchanged: one login sets one `rag_session` cookie,
and because a cookie is scoped to a host rather than a port and `SameSite=Lax` keeps the two origins
same-site, either process resolves the same `sessions` row. A client reaches both through its own
origin — a development proxy or a reverse proxy — which is the frontend engineering contract's
business, not this one's.

**Why two processes rather than one, and rather than three.** `docs/architecture/system-overview.md`
assigns the graph execution, the checkpoint and the streaming to the agent runtime and the SSE response
lifecycle to the API process; this split implements that boundary where it costs the least. The process
that streams a run is the process that *executes* it, so a client that disconnects cancels the LangGraph
run directly — with no internal hop whose cancellation would have to be propagated by hand, and no
second SSE protocol between two of our own services. The business API stays a thin request/response
API over PostgreSQL, and the chat lane — the one that holds long-lived connections, a checkpointer pool
and a compiled graph — can be restarted or scaled without touching it.

The alternative considered and rejected: one process serving everything. It would make the API process
carry the checkpointer pool and the graph for the sake of saving a port, and it would contradict the
process boundary the architecture document states. Also rejected: the API proxying to the agent runtime.
That adds an internal HTTP contract, an internal authentication story and a second cancellation path,
for no behaviour a client can observe.

**Consequences, recorded as limits.** A deployment must route `/api/v1/conversations*`,
`/api/v1/retrieval-debug*` and `/api/v1/auth*` to the agent runtime and everything else to the API (or
serve both under one origin with two upstreams). Both processes must be running for the chat to work,
which is why `scripts/smoke.ps1` starts both and the health contract is served by both. The agent
runtime additionally needs the selector event loop on Windows (ADR-0007), which its entrypoint creates
itself rather than through uvicorn's own loop factories — those hard-code `ProactorEventLoop` on
Windows, which psycopg's async path refuses.

Evidence: `backend/src/composition/api/app.py` (the business app and the middleware both share);
`backend/src/composition/agent/app.py`; `backend/src/agent_runtime/main.py`;
`backend/src/api/conversations.py`; `scripts/smoke.ps1` (two processes, two ports);
`scripts/probes/retrieval.ps1` and `scripts/probes/agent.ps1` (each addresses both).

## ADR-0021: The Phase 4 retrieval and agent lane

Status: accepted

**The channel contract, and what a failure means.** A channel answers one query with the matches its own
store ranked and with its own score; the engine assigns the ranks after merging the query variants of
that channel, so a rank is a property of the channel's answer rather than of the query that produced
it. A channel's outcome is one of four states and they are different facts: `ok` (it answered with
hits), `empty` (it answered with nothing), `failed` (it did not answer; `error_type` names the class)
and `unavailable` (this deployment has no such channel). The three channels run concurrently under a
per-channel timeout, and a channel that fails is recorded as failed while the others' results stand: a
run never reports "the knowledge base does not contain this" because a provider timed out.

**Hydration before fusion, and `ready` as the gate.** The channels return identifiers and scores;
their text, location and document name are read from PostgreSQL before anything is fused. That step is
where a hit stops being a candidate: a row that is gone, a document of another knowledge base or a
version that never reached `ready` is simply absent. The dense channel's filter is the knowledge base
only, because the point payload is a fixed thirteen-field copy of the row and carries no version status
(ADR-0019); the `ready` filter therefore lives where the authority is — in the join that hydration and
the keyword channel both perform.

**Fusion is application-level and recomputable.** `Σ weight_c / (60 + rank_c)` over the channels that
returned a chunk, deduplicated by `document_version_id + child_id`, ordered by score and then by
identifier. The numbers are configuration and the run reports them: `POST /api/v1/retrieval-debug/query`
answers each channel's ranked hits, every candidate's `channel_ranks` and its `rrf_score`, the rerank
scores, the gate's decision and the labelled context — so a fused score can be recomputed from the
response that reports it. The retrieval probe does exactly that, to 1e-9. Per-request channel/rank
scores are *not* stored: they are request-scoped observability, and the diagnostics read is where they
are reported (``docs/architecture/data-flow.md``).

**Rerank, and what happens when it cannot run.** At most the rerank budget's candidates are scored,
`top_n` is bounded by the number of documents handed over, and an empty set is never sent (the provider
refuses it: HTTP 400, code 20015 — measured). A provider that is unavailable does not fail the run: the
configured fallback keeps the fused order and the run reports `degraded`, which the evidence gate reads
as "grounded without rerank scores". A missing score is never written as zero, and a degraded run is
never reported as a reranked one.

**The gate.** `retrieved` is not `evidence`. A candidate is evidence when it exists, carries the stored
text a citation quotes, and either reached the rerank threshold or was kept under the explicitly
configured degraded mode. The threshold's default is a provisional floor, recorded as such: the
retrieval contract defers its calibration to the final corpus, and until then the gate exists to keep an
unrelated question from being answered out of whatever the index happened to hold. An abstention is a
constant of the platform, not a model call, so the one answer that must contain no general knowledge
cannot acquire any.

**Context and citations are child-scoped.** The accepted candidates are grouped by parent, each
parent's children are ordered by the document's own ordinal, parents are taken in the order their best
candidate was fused, and whole chunks are selected under the token budget — a chunk that would exceed
it is dropped whole rather than half-rendered. Labels (`S1`, `S2`, …) are assigned in that order, which
is what makes the evidence set and the context text one object. A citation is *child*-scoped, and that
is forced by the schema rather than chosen: `parent_chunks` has page columns but no line columns, and
the protocol's location must be exact. The quote is an excerpt of the stored child text cut at a line
boundary, the line range is the child's own, and the page range is whatever the parser reported — null
on the `anydoc` route, where no page exists to report (ADR-0016). The model may emit only the labels it
was given: an id outside the request's evidence set is stripped or refused according to
`RAG_CITATION_INVALID_ID_POLICY`, never accepted, and a chunk that vanished while the answer streamed
takes its marker with it.

**The graph is fixed and its only cycle is bounded.** The topology is the documented one —
`load_context → understand_query → route_query → {direct_response | ask_clarification | plan_retrieval}`
and `plan_retrieval → retrieve → {generate → validate_citations | rewrite_once → plan_retrieval |
abstain}`. The retrieval lane is a single node because it is a single application operation
(`RetrievalService.retrieve`): the channels, hydration, fusion, rerank and the gate are steps inside
it, not checkpoint boundaries, so a round is the recovery granularity (safe, because the lane is
read-only) instead of seven writes of the same chunk text. `plan_retrieval` counts the round and the
retrieval edge may send the run back only while
`rounds < max_retrieval_rounds` (the documented 2), so the retry edge is unreachable once the budget is
spent and a run that cannot be grounded abstains after exactly that many rounds. LangGraph's recursion
limit is derived from the same number, so the engine's bound and the topology's cannot drift apart, and
`python -m cli graph-topology` prints the compiled graph's nodes, edges and bounds. A
retry round *replaces* the candidate set rather than accumulating it: a rewrite is a new question, and
a second gate decision that mixed both questions' candidates would be judging neither. The classifier
is a hint and never a gate: a classification that fails, times out or answers nonsense falls back to
retrieving the question as asked, marked degraded.

**State, thread and the reset rule.** A conversation is one LangGraph thread, and the checkpoint is the
run's own storage — never the conversation's history, which PostgreSQL owns. Because a thread is reused,
a new turn *resets every state key* (`initial_state`), so a stale `rounds`, `answer` or retrieval
record from the previous question cannot be mistaken for this one's. The retrieval lane's telemetry —
the channels' hits, the fused and reranked candidates — never enters the state at all: a candidate
carries its chunk's text, and the state keeps only the round's `RetrievalRecord` (the gate's decision,
the labelled sources, the rendered context), which is what answer generation and citation validation
read. The state is therefore business-free: it holds the route, the round's record and the answer, and the
persisted message and its citations are written to PostgreSQL by the runner.

**Streaming and the terminal rule.** The answer's deltas leave the graph through LangGraph's *custom*
stream, because the provider boundary is a thin HTTP adapter rather than a LangChain chat model, so
LangGraph's `messages` stream mode has no model call to observe. The runner turns those frames into
`answer_delta` events and owns the contract's other half: exactly one terminal event per stream, emitted
**after** the message and its citations are committed, so a client that received `run_completed` reads
the same answer and the same citation payloads from `GET /conversations/{id}`. A failure before the
assistant message exists still ends the stream with `run_failed`, whose `message_id` is null in that
case.

**Cancellation is preserved.** A client that disconnects cancels the ASGI task, the graph run and the
provider's connection; the runner persists the partial answer as a `cancelled` message inside the
cancellation — shielded with `asyncio.shield`, so a second cancellation cannot cut the write short — and
then **re-raises** `CancelledError`. Swallowing it would leave the graph's own cancellation, the
provider's connection and the task's cleanup to chance, which is the one thing
`docs/development/backend-guidelines.md` forbids. The cancelled row is the visible statement of the
interruption, and the run is logged with `terminal=cancelled`.

**Not in this ADR, deliberately.** The retrieval lane's channel tuple is where a further source would be
appended, so no engine change is required for one; no such source exists today (ADR-0029). Langfuse
traces are Phase 5's. The frontend's client, its own cancellation
handling and the pages are Phase 7's; this ADR fixes only the contract they consume.

Evidence: `backend/src/domain/retrieval.py`;
`backend/src/domain/citation.py`; `backend/src/domain/query.py`;
`backend/src/domain/chat.py`; `backend/src/domain/conversation.py`;
`backend/src/application/retrieval/service.py`; `backend/src/application/agent/answer.py`;
`backend/src/application/retrieval/citations.py`;
`backend/src/application/agent/query_understanding.py`;
`backend/src/application/conversations/service.py`;
`backend/src/agent_runtime/graph.py`; `backend/src/agent_runtime/runner.py`;
`backend/src/agent_runtime/events.py`; `backend/src/agent_runtime/state.py`;
`backend/src/agent_runtime/checkpointer.py`;
`backend/src/infrastructure/{dense_channel,keyword_channel,chunk_store,conversation_store,siliconflow_chat,siliconflow_rerank}.py`;
`backend/migrations/versions/0004_conversations.py`; `docs/architecture/frontend-contract.md` (the Phase 4
contract); `scripts/probes/retrieval.ps1` (the channels, the recomputed fusion, the rerank contract
including `top_n` above the candidate count, the gate, the context and its authoritative sources, the
version isolation and the `ready` filter); `scripts/probes/agent.ps1` (the six-event stream, the
validated citations compared with their stored rows, the round-bounded abstention, the direct-response
route, cancellation with its persisted row and its log line, the checkpointer's four tables, and the
chat provider's `json_object` contract).

## ADR-0022: LightRAG is the knowledge graph, one workspace per knowledge base

Status: withdrawn by ADR-0029

> The graph channel, its table, its stage and its probe were removed (ADR-0029). The body is kept as the
> record of the storage, scope and lifecycle decisions the channel was built on.

> **Refined by ADR-0028.** This ADR decided the graph's storage, scope and lifecycle but left two things
> implicit: who may write one knowledge base's LightRAG workspace at the same time (LightRAG's own
> coordination is in-process only, and `ainsert` drains the whole workspace rather than the job it was
> handed), and how the process-level objects a write or a query needs are bounded (a cached instance
> holds nine Qdrant clients and a reference into the process-wide PostgreSQL pool). ADR-0028 decides
> both, makes the startup storage configuration a contract that refuses a workspace override instead of
> silently removing it, and puts the graph's own readiness on the wire beside the version's. Neither
> paragraph below is superseded by it.

**Storage and scope.** The graph is LightRAG 1.5.7's own storage — ``PGTableGraphStorage`` for entities
and relations, ``PGKVStorage`` for documents, chunks and the entity/relation side indexes,
``PGDocStatusStorage`` for the pipeline's document state, and ``QdrantVectorDBStorage`` for the graph's
vectors (ADR-0012) — reached through its own storage registry. No LightRAG storage is reimplemented,
and the graph needs no infrastructure this platform does not already run: PostgreSQL and Qdrant.

**One workspace per knowledge base** is the isolation decision ADR-0012 left open ("one workspace per
knowledge base or post-filter graph results"). The workspace is *derived* from the knowledge base
identifier (``kb_<hex>``), so a deployment mistake cannot point one knowledge base's graph at another's,
and the consequences are the ones the retrieval contract wants: a query can never rank another
knowledge base's documents in the first place, and a knowledge base's graph is removable in one
drop. The Qdrant side keeps ADR-0002's physical isolation as well: LightRAG's collections are
``lightrag_vdb_*`` and never the business collection, and its PostgreSQL tables are its own
(``lightrag_*``), outside this platform's Alembic history.

**One LightRAG document per child chunk, with the business identifiers in the reference.** Each child
chunk is inserted as a document whose ``file_path`` is ``child--<version>--<parent>--<child>`` — the
canonical business source reference ``docs/architecture/ingestion-pipeline.md`` asks for — which is
what makes a graph hit map back to the child chunk a citation quotes rather than to a LightRAG chunk
nobody can cite. The three identifiers are separated inside *one* path component because LightRAG
stores ``normalize_document_file_path``'s canonical basename of the value it is handed: a
``/``-separated reference reaches retrieval as its last segment alone (measured on this deployment),
so the separators have to survive basename canonicalization. The chunker's own size is configured
above this platform's child budget, so LightRAG keeps each document as the chunk it was given and one
reference stays the reference of exactly one business chunk.

**LightRAG's configuration surface is the environment, and that is not hidden.** Its PostgreSQL and
Qdrant storages read ``POSTGRES_*`` and ``QDRANT_*`` (or a ``config.ini`` beside the process) with no
injection point, so the adapter derives those variables from this platform's validated configuration
and **removes** ``POSTGRES_WORKSPACE``/``QDRANT_WORKSPACE`` when a deployment set them: either would
override the per-knowledge-base workspace and silently break the isolation. The adapter also uses
LightRAG's own ``EmbeddingFunc`` wrapper, with ``model_name`` set, because LightRAG names its vector
collections from it (ADR-0012's warning about a missing model suffix).

**The build is a stage of its own, and it cannot move the version.** A successful index stage appends
a ``graph_build`` job in the same transaction that declares the version ``ready``, and the graph
stage writes only its job and its ``graph_build_runs`` row — never the version's status. That is the
independence ``docs/architecture/data-flow.md`` states: a graph that is pending, building or failed
leaves a ``ready`` version fully retrievable through the dense and keyword channels. The retry
machinery is the ingestion lane's own (claim, finite attempts, classification), and a version with no
child chunk is the one failure a retry cannot fix, so it is recorded once for an operator.

**Deletion is the store's own.** A document deletion reports the child identifiers its transaction
removed, and the graph deletes those documents through LightRAG's ``adelete_by_doc_id`` — which also
rebuilds the entities that other documents still reference, using its own extraction cache. A
knowledge base deletion drops the whole workspace: every storage's ``drop()``, which is exact because
the workspace is the scope, followed by the instance's finalization. What ``drop()`` leaves is the
collection: LightRAG provisions one physical Qdrant collection per namespace and partitions it across
workspaces by a payload field, and its own ``QdrantVectorDBStorage.drop()`` documents that "the
collection itself and its vector index are NOT recreated — they were provisioned at ``initialize()``
and remain in place". A deletion is therefore verified as "no points and no rows for the workspace"
(``scripts/probes/graph.ps1`` step 8), not as "the collections are gone"; a read of a never-built
workspace is enough to create them, so they outlive the knowledge bases that first needed them.

**Rebuild is the operator command** ``python -m cli rebuild-graph <version>``: it removes
the version's graph documents and builds them again, which is what repairs a graph that was removed by
hand, built by an older configuration or left behind by a failure. ``RAG_GRAPH_ENABLED=false`` runs the
platform without a graph at all: no graph job is appended and the retrieval lane carries two channels.

Evidence: `backend/src/infrastructure/graph/lightrag.py`;
`backend/src/infrastructure/retrieval/graph_channel.py`;
`backend/src/application/ingestion/graph.py`;
`backend/src/application/cleanup/service.py` (both deletion paths' graph cleanup);
`backend/src/domain/graph.py`;
`backend/migrations/versions/0005_graph_build_runs.py`; `docs/research/official-docs-lightrag.md`;
`scripts/probes/graph.ps1` (retrieval before the graph exists, the rebuild command, the LightRAG tables
and collections, the mapping of graph hits back to business chunks, two isolated workspaces, and the
cleanup of both deletion paths).

## ADR-0023: Langfuse traces are thin, optional, and never in the request's way

Status: accepted

**The SDK only.** The platform emits observations through the ``langfuse`` SDK 4.16 and never reads or
writes Langfuse's tables (ADR-0014); the observability probe reads them back through Langfuse's public
API for the same reason — the **observations API v2** (``GET /api/public/v2/observations``), because a
self-hosted v4 deployment runs in ``events_only`` write mode by default and the legacy trace and
observation reads answer 404 there ("This endpoint is not available on deployments running in Langfuse
v4 events_only mode", measured on this stack).

**Tracing is optional and cannot fail a request.** ``RAG_LANGFUSE_PUBLIC_KEY``/``RAG_LANGFUSE_SECRET_KEY``
are optional settings: without them the process runs with tracing disabled, because observability must
not be a dependency of answering a question. Every call into the SDK is wrapped and its failure is
logged at warning level and swallowed — an observability outage must not become an availability
outage. ``RAG_LANGFUSE_HOST`` defaults to the local stack; the keys, the database and the bucket are
provisioned by ``python -m cli observability-init`` and seeded by the Compose stack's
``LANGFUSE_INIT_*`` variables.

**What is emitted, and what is deliberately not.** One observation per agent run and one per ingestion
stage attempt. A run's trace id *is* its ``run_id``, so the trace of a run is findable by the identifier
the platform already logs and already streams to the client. The metadata carries identifiers only —
run, conversation, knowledge base, user, stage, document version, job — and never a document's text.
The observation's input is the question and its output is the answer, which is what a trace is for;
a grounded answer quotes the evidence it was given, so the *output* is deliberately not where the
no-corpus rule is enforced. The probe asserts exactly that: the identifiers are present in the
metadata, and the document's own sentence appears in neither the metadata nor the input.

**A trace is flushed when the run ends**, rather than whenever the SDK's batching decides to send it:
an operator looking at a trace they just produced, and a probe asserting that one exists, both depend
on it. The flush is the price of a trace that is *there* rather than eventually there, and it is paid
once per run rather than once per observation.

Evidence: `backend/src/infrastructure/observability/langfuse_tracing.py`;
`backend/src/agent_runtime/runner.py` (one observation per run);
`backend/src/application/ingestion/document_ingestion.py` (one per stage attempt);
`infra/compose.yaml` (the stack and its isolation); `scripts/probes/observability.ps1` (the stack's
health with the configured keys, a run's trace readable by its run id, the ingestion stages' traces,
and the absence of document text); `docs/research/official-docs-langfuse-aegra.md`.

## ADR-0024: There is no scheduler process

Status: accepted

`backend/src/scheduler/` is deleted. It performed no scheduled work: it validated configuration and
waited for shutdown, so it was a process for a use case that does not exist. The platform's only
periodic work — the cleanup sweep — runs inside the worker, which already owns the event loop and the
queue consumer (ADR-0004's rule is unchanged: periodic work dispatches through Taskiq and never
becomes a queue). A future scheduled task gets its own process and the `apscheduler` dependency then,
not before.

Evidence: `docs/architecture/system-overview.md`; `docs/operations/local-development.md`;
`scripts/dev.ps1`; `backend/src/worker/main.py`.

## ADR-0025: Per-process connection budgets: one pooled provider client, one sized database pool

Status: accepted

Two resources this platform opens are held per *process*, and both are now sized by the process that
owns them rather than inherited from a library default.

**Provider HTTP clients.** Each of the three SiliconFlow adapters (embeddings, chat, rerank) holds one
HTTPX client for the lifetime of the process instead of opening and closing one per call. HTTPX's own
guidance is the basis: a request made without a `Client` establishes a new connection "for every
single request", while a `Client` reuses the underlying TCP connection, which brings "significant
performance improvements ... Reduced latency across requests (no handshaking)". Every call this
platform makes is an HTTPS request to one host, and one answer or one document is many calls: the
classifier and the streamed answer, or one embedding batch per sixteen children. The client is created
on first use inside the event loop that will use it, under a lock — the shape
`QdrantChildChunkIndex` and `IngestionJobQueue` already use, so a process that never calls a provider
opens no connection — and each process runtime's `close()` releases it. `max_connections` is stated
(`RAG_PROVIDER_MAX_CONNECTIONS`, default 16) because HTTPX's default of 100 per client is more
parallelism than the provider's quota or this deployment's own concurrency admits; `keepalive_expiry`
is left at HTTPX's documented default, because no measurement of this deployment's call spacing exists
to argue with it. Because a shared client cannot be a context manager (`__aenter__` raises on an
already-open client), the block scope moves down to the response (`client.stream(...)`), which is what
keeps a cancelled stream releasing its connection. The OCR adapter is deliberately unchanged: it
already reuses one client across the submit, every poll and the result fetch of one `parse()`, and the
`DocumentParser` port carries no lifecycle to widen for the other three parsers.

**Database pools.** `create_database` takes its `pool_size` from the calling runtime, so the API, the
agent runtime and the worker each size their own pool (`RAG_API_DATABASE_POOL_SIZE`,
`RAG_AGENT_DATABASE_POOL_SIZE`, `RAG_WORKER_DATABASE_POOL_SIZE`, default 8) with one shared
`RAG_DATABASE_MAX_OVERFLOW` (default 4), and every operator command reuses the worker's number. The
number that matters is the total — those three plus their overflow, plus `RAG_CHECKPOINT_POOL_SIZE`,
plus operations headroom, under the database's `max_connections` — which is
why one global constant was the wrong shape. `pool_timeout` is the database timeout rather than
SQLAlchemy's 30 s default, so an exhausted pool fails as fast as an unreachable server instead of
waiting past the deadline of the request that is holding it. `pool_pre_ping` stays: container
networking and long-lived connections are what this deployment has, and the round trip it costs is what
turns a connection the server closed during an idle period into a reconnect.

Not decided here, because they need measurement rather than a reading of the docs: the calibrated
values of these pools and of `RAG_PROVIDER_MAX_CONNECTIONS`, `keepalive_expiry`, `pool_recycle` and
`use_lifo`. The stage-level durations and the step-level retrieval latencies now logged are what those
measurements will read from; the doc's own rule applies — provider concurrency, queue prefetch, task
count and pool size are four separate budgets and none of them is tuned from a profile that does not
exist.

Evidence: `docs/research/official-docs-httpx.md` (§1–§4, and §6 for why OCR/Qdrant/S3 are unchanged);
`scripts/probes/http_client.py` (a pooled client reuses one connection across calls, `max_connections`
bounds concurrent connections, and a cancelled call leaves the client usable);
`backend/src/infrastructure/providers/http_client.py`;
`backend/src/infrastructure/db/engine.py`;
`backend/src/infrastructure/config/settings.py`; `composition/{api,agent,worker,cli}/runtime.py`.

## ADR-0026: The schema states the business invariants, and one row owns each fact

Status: accepted

The business schema, its migrations, the ORM mappings and the real queries were reviewed together
before this change. Its conclusions are implemented here, and this ADR records the decisions that
outlive it.

**The invariants the application maintained are now the database's.** A child chunk could name a
parent of another version and a conversation could name a knowledge base another user owns: the
application never writes either, but nothing in the schema refused it, so one hand-run statement or
one future regression could produce cross-version chunks or an owner-scope mismatch. `child_chunks`
now carries the composite foreign key `(parent_id, document_version_id)`, and `conversations` the
composite foreign key `(knowledge_base_id, owner_id)`, each replacing the single-column key it
subsumes rather than sitting beside it. The price is two unique constraints that exist only to be a
foreign key's target (`parent_chunks(parent_id, document_version_id)`,
`knowledge_bases(id, owner_id)`) and one column pair that is constrained rather than copied freely.
That is the trade: a redundant-looking key the database checks is cheaper than a correctness bug the
application can only avoid by convention. Value domains the application already maintained followed
the same rule: non-negative sizes, ordinals, token counts and attempt counters, a positive revision,
a line range whose end is not before its start, and a page count that is null or non-negative.

**An email is stored canonically, and the index is an equality.** `normalize_email` lowercases and
trims every write, so the repository-wide functional unique index on `lower(email)` was paying for a
guarantee the data already had while making every lookup an expression the planner evaluates per row.
It is replaced by a plain unique constraint on `email` plus `ck_users_email_canonical`, which refuses
a row that bypassed the application. A lookup is now `where email = :canonical`, which is the index
itself.

**A version has one parse artifact, and its identity is the version.** `parse_artifacts` and
`chunk_artifacts` each held exactly one row per version (`unique(document_version_id)`) behind a
surrogate `id` that neither the mappings nor any DTO read. `document_version_id` is the primary key
of both, so the upsert that replaces a row conflicts on the key that means something and there is no
second identifier to keep in step. This is what `graph_build_runs` already did.

**One fact, one row: the parse result lives in `parse_artifacts`.** *This refines ADR-0016*, which
wrote the parse result into both the version row and the artifact row and justified it as "the static
metadata `data-flow.md` requires of a version". The requirement is real; the copy was not. Both
tables were written by one transaction, so they agreed — until a future writer updated one of them,
at which point the version's pointer and the artifact's record would disagree about which bytes are
the version's Markdown. The version row now keeps only the version's own facts (identity, ordinals,
status, source object, mime, checksum, size, timestamps) and `parse_artifacts` owns the parse result
(object key, parser identity, page count, page spans, warnings, the measured digest and size). Nothing
on the wire changed: the version detail response reports the parser identity and the page count from
the artifact — that is where it already read them — and the two internal readers that used the
version's copy (the deletion paths reporting the object keys they removed) read the artifact table in
the same pre-delete statement set that already read the chunk artifacts and the child identifiers.

**Indexes follow queries, and a composite key already answers its own left prefix.** The owner-scoped
lists gained the ordering they actually ask for — `(owner_id, created_at desc, id)` for knowledge
bases, `(owner_id, updated_at desc, id)` for conversations, `(conversation_id, created_at, id)` for a
message history — with `id` as the tie-breaker every list orders by, so two rows created in the same
instant cannot swap places between reads. The cleanup claim's two live states gained a partial index
each, over `(updated_at, id)`, and the single index over `(status, updated_at)` that carried every
terminal row into two more index pages is gone. Three single-column indexes were dropped because a
composite unique constraint already serves their left prefix, and PostgreSQL scans a B-tree backwards:
`parent_chunks(document_version_id)`, `child_chunks(document_version_id)` and `citations(message_id)`.
`child_chunks(parent_id)` stayed: it is not a left prefix of any constraint, and it is the path the
parent expansion and the parent's cascade delete read.

**The cleanup claim is a queue read, so it locks like one.** The claim was one statement over
`pending` and lease-expired `running` rows at once. It is now three statements in one transaction: a
spent `running` claim is recorded terminal, a lease-expired one is re-claimed, and a `pending` one is
taken — each a `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` inside the `UPDATE` that consumes it. Two
sweeps racing on the same row therefore do not queue behind each other's lock; the second takes the
next claimable row or reports that nothing is owed. The ingestion jobs' claim needed no such change:
it addresses one row by primary key with its status in the `WHERE` clause, which the rule above
already accepts.

**Tenant isolation stays where it is.** Every store filters on `owner_id` and no client reaches the
database directly, so row-level security is deliberately *not* enabled: without an API/worker role
and transaction-context contract it would be a second, unverifiable mechanism that could deny
everything or leak a pooled context. The decisions that would force it are recorded — a client, a
Supabase Data API or another untrusted SQL consumer entering the deployment — together with the
requirement that it then arrives with `FORCE ROW LEVEL SECURITY`, a trusted worker role and a
transaction-scoped `set_config`, and that the application filter stays in place either way.

**No partitioning, no materialized views, no triggers, no native enums.** Not rejected in principle:
rejected for a schema with no measured volume, no retention policy and no hot/cold split. The `CHECK`
constraints are added as validating constraints rather than `NOT VALID` + `VALIDATE`, because that
pair exists to keep a large production table writable while a backlog is cleaned and this deployment
is pre-production — a row that violates one of these is a bug to fix, not data to serve. For the same
reason the new indexes are plain `CREATE INDEX`: a large production table needs
`CREATE INDEX CONCURRENTLY`, which cannot run inside Alembic's transaction and therefore needs an
autocommit block, and the migrations record that.

**Deliberately not done, and what would trigger it.** Each of these was considered in the review and
left out with a named trigger, so a later reader can tell a decision from an oversight:

| Not done | Why, and the trigger |
|---|---|
| `ix_ingestion_jobs_pending_updated_id` | No query scans `ingestion_jobs` by `status`: the claim addresses one row by primary key and `append_stage_job` uses the `(version, stage, revision)` unique constraint. A partial index with no reader only adds insert and vacuum cost. Add it with the first pending-sweep query. |
| `ix_document_versions_ready_document` | The keyword channel filters `status = 'ready'` after joining `document_versions` by primary key, so a `(document_id) where ready` index cannot help that plan. It matters only for a query that starts from a `document_id` and looks for ready versions. |
| Keyset pagination and an explicit limit contract | It changes the API and the frontend contract, so it lands with the frontend, not before it. |
| Row-level security and the `rag_migrator`/`rag_app`/`rag_readonly` roles | This deployment has no direct client. The implementation requirements are stated above and travel with the Data API. |
| Splitting the cleanup intent's object list into its own table | The JSONB arrays are small and unjoined; split it when a row width or a single deletion's duration is measured to matter. |
| `CREATE INDEX CONCURRENTLY` | Development and pre-production do not need it; the production procedure is recorded in `0007`'s docstring. |
| Partitioning, materialized views, triggers, native enums | No capacity, retention or hot/cold evidence. |
| `pg_stat_statements` and plan collection | They need a long-running real workload; this round recorded query shapes and index matches instead. |
| A history partial index on `messages` | Left to an `EXPLAIN` of a real history query; this round only added `id` to the existing indexes. |

Evidence: `backend/migrations/versions/0007_schema_hardening.py`,
`0008_artifact_identity.py`, `0009_drop_parse_projection.py`; `scripts/probes/migrations.ps1`
(`upgrade head`, `alembic check` with no drift, `downgrade base`, re-upgrade, business database
untouched, and the index listing that shows the dropped and the added indexes);
`scripts/probes/database.py` (a cross-version child refused, a cross-owner conversation refused, a
non-canonical email refused, two concurrent claims granted exactly one, the newest-version list and
the single parse artifact per version); `scripts/probes/hardening.py` (the ingestion fence and the
cleanup lease re-run against the new claim).

## ADR-0027: A citation is located by its line range, not by a page

Status: accepted

**The coordinate that was dropped, and why.** `page_start`/`page_end` were on `parent_chunks`,
`child_chunks`, `citations` and the Qdrant payload, and they were null on every route but one.
`anydoc` reports no page number and no page marker for PDF, DOCX, PPTX or XLSX (ADR-0016), and HTML
and plain text have none either, so every chunk and every citation produced from a PDF carried a null
page. Only the OCR route had real page numbers, because PaddleOCR-VL's `layoutParsingResults` holds
one element per page; it recorded them as `page_spans`, a page-to-line-range map, and `page_range()`
intersected that map with a chunk's line range to fill the two columns.

What locates a citation is `line_start`/`line_end` plus `quote`, and both address the normalized
Markdown artifact the answer was built from (ADR-0016). A page number added nothing to that pair: it
was null where it was not known, and where it was known it was a line range by another name. The
field is therefore dropped, and with it the mechanism that existed only to fill it — `page_spans`,
the `PageSpan` type, the normalization remap that kept the map addressing the right lines after the
Markdown was rewritten, and `page_range()` itself. Keeping the map would be a field nothing reads,
which the deletion rule forbids; keeping `page_range()` would be an unreachable function over a
dropped column.

**What stays, and why it is not the same thing.** `page_count` stays on `parse_artifacts`. It is a
fact about the document ("this scan is twenty pages"), the OCR route is the only route that can report
it, it needs no line map, and the parse stage logs it while the ingestion stepper shows it. It is
reported as far as the parser knows it, and is null where it does not.

**The wire changes, and that is why this is written down.** The `citation` SSE frame,
`CitationResponse`, `RetrievalContextSourceResponse` and the retrieval-debug `context_sources` all
lose the two fields, and `ParseArtifactResponse` loses `page_spans` and `PageSpanResponse`. The
frontend loses the page half of its location labels: `locationLabel`, the citation popover and the
evidence inspector now show the line range and the quote, which is what a reader can actually check
against the stored Markdown. A client that rendered "no page" for every PDF now renders nothing,
because there is no longer a distinction to render.

**The downgrade restores the columns, not the coordinates.** Migration 0010 re-adds them as null. The
dropped values are not recoverable: they were null on every non-OCR route, and on the OCR route they
came from a page map that no longer exists. A schema migrated down and up again holds the columns it
started with.

**Rejected: deriving a page from the line numbers.** A page could have been synthesised from the
normalized Markdown's line count, or the map could have been kept for the OCR route alone so that a
page was reported wherever it was knowable. Both were rejected for the reason ADR-0016 already gave
for not guessing: a page number a reader cannot verify against the original file is worse than no page
number, because it looks like a location and is not one. The line range and the quote are verifiable
against the stored artifact; a derived page is not.

Evidence: `backend/migrations/versions/0010_drop_page_coordinates.py`; `domain/chunks/planning.py`
(no `page_range`), `domain/normalization.py` (no page-span remap), `domain/parsing.py` (no
`PageSpan`), `domain/embedding.py` (no page in the payload),
`infrastructure/parsing/paddleocr_parser.py` (per-page text concatenated, page count kept);
`scripts/probes/parsing.ps1` (the OCR route reports a page count and `anydoc` does not;
`Get-VersionRow` now asks `parse_artifacts` whether the artifact row exists instead of reading parse
facts off the version row, which Migration 0009 had already moved); `scripts/probes/chunking.ps1`,
`indexing.ps1`, `retrieval.ps1`, `agent.ps1`, `database.py`, `hardening.py` (every artifact, chunk,
citation and vector-payload comparison runs without the two columns).

## ADR-0028: Graph workspace writes are serialized across processes, and instances are a bounded resource

Status: withdrawn by ADR-0029

> Removed with the channel (ADR-0029): the workspace lock, the instance cache, the storage-environment
> contract, the `graph` field on the version detail and the `graph` probe all go with it. The body is
> kept as the record of the concurrency and resource decisions that were measured.

*This refines ADR-0022*, which decided the graph's storage, its scope and its lifecycle but left two
things implicit: who may write one knowledge base's LightRAG workspace at the same time, and how the
process-level objects that writes and queries need are bounded. Both are now decided, and the checks
this decision rests on were read out of the pinned `lightrag-hku` 1.5.7 in this repo's `.venv`, not out
of the upstream `main` branch.

**LightRAG's own coordination is in-process, so it cannot be the platform's.** `ainsert` is
`apipeline_enqueue_documents` followed by the awaited `apipeline_process_enqueue_documents`
(`lightrag/lightrag.py`), and that drain joins every parse/analyze/process worker and its queues before
returning (`lightrag/pipeline.py`): a returned insert did finish in this process. But the locks that
make concurrent drains safe are `pipeline_status` plus `get_namespace_lock` and the `KeyedHolderTable`,
and `lightrag/kg/shared_storage.py` holds all of them in module state — a `SyncManager` table spans
processes on *one host* in the server's `--workers` mode, and nothing spans two containers.
`adelete_by_doc_id`'s documented concurrency check is the same mechanism, reading a `job_name` off that
same in-process status (`lightrag/lightrag.py`, "Concurrency Control Design"). So a Worker process
cannot learn from LightRAG whether another Worker is draining the same workspace.

**And the drain's scope is wider than the job that started it.** `ainsert` processes the whole
workspace's `pending` documents and re-runs every `failed` document in it each pass, so two documents of
one knowledge base arriving as two jobs is two writers of one workspace even though the job rows are
disjoint — which is why "the other document's job is not `running`" was never evidence that the
workspace is free. The platform therefore serializes workspace *writes* itself, with a PostgreSQL
session-level advisory lock: `select pg_advisory_lock(hashtextextended(:workspace, 0))` on a dedicated
`NullPool` connection, taken by `build`, `rebuild` (delete and insert under **one** acquisition, since
the half-state between them is the state a rebuild exists to remove), `delete_documents` and
`delete_knowledge_base`, and released when that connection is closed.

**Why an advisory lock and not a lease row.** The operation is long (a workspace drain is minutes to
hours) and its holder can be killed. A session-level advisory lock needs no table, no migration, no
cleanup task and no lease duration, has no false-blocking window after a crash, and cannot be left held
by a process that died — the lock is the connection. The price is one dedicated connection per writing
(or waiting) process, which is stated below rather than hidden. The lock is taken on a `NullPool` engine
so a multi-hour hold cannot consume a business pool slot, and `command_timeout` is deliberately *not*
set on it: asyncpg would cancel the waiting `pg_advisory_lock` and turn a queue into a failure. The
repository's own rule ("use `pg_try_advisory_xact_lock` only for a global operation that corresponds
to no database row, and only inside a short transaction") is consistent with this and is extended by
one sentence: the workspace drain *is* that operation, and because it is long the lock is
session-scoped on a connection of its own instead of transaction-scoped.

**Waiting, not refusing.** A writer that finds the workspace taken waits for it, bounded by the same
`RAG_GRAPH_TIMEOUT_SECONDS` that already bounds the attempt — inside one `asyncio.timeout`, so the wait
and the work share a budget and no new knob appears. Refusing instead would have been worse than slow:
`claim_job` has already spent an attempt by the time the lock is reached, so a *queue* of concurrent
builds on one knowledge base (an ordinary bulk upload) would exhaust `RAG_JOB_MAX_ATTEMPTS` on
contention alone and mark healthy documents failed. Waiting also has the better outcome — the first
writer's drain processes its siblings' documents too, so the writers behind it acquire the lock, find
their documents already `processed`, and finish immediately.

**A reset job is only retried if the broker knows the exception.** `BuildDocumentGraph` resets a
transiently failed graph job to `pending` and re-raises, and the redelivery is
`SmartRetryMiddleware`'s job — which only retries the exception types it was configured with. The graph
stage's `TransientGraphBuildError` was not among them while every other stage's was, so a transient
graph failure left the row `pending` with its message discarded into the dead-letter queue and nothing
left to deliver it: it was the one stage whose documented retry did not exist. It is registered now,
and the comment on `_RETRYABLE_STAGE_ERRORS` states the rule for the next stage.

**A refused deletion is not a completed deletion.** LightRAG's `adelete_by_doc_id` returns
`not_allowed` rather than raising when *its* pipeline is busy (which, in one process, another workspace's
drain can make it), and the cleanup lane counts a returned call as a finished one. Reading only
`success` and letting everything else pass meant a cleanup intent could be recorded `succeeded` with the
graph documents still present. `success` counts, `not_found` is the idempotent no-op it is, and any other
status becomes a transient store error so the lane's own retry budget owns it.

**Instance caching is bounded, because an instance is not free.** A cached LightRAG instance holds nine
Qdrant clients — `QdrantVectorDBStorage` builds one client per vector namespace and `drop()`/`query`
use it — and a reference into the process-wide PostgreSQL pool that `ClientManager` shares across every
PG storage in that process. Unbounded per-knowledge-base caching therefore accumulates clients and
directories for knowledge bases nobody is querying. `RAG_GRAPH_INSTANCE_LIMIT` (default 4) bounds the
cache and the least-recently-used instance is finalized on eviction; finalization is safe for a sibling
because the shared PostgreSQL pool is reference-counted and only closes with its last reference. An
initialization that fails *midway* is the case LightRAG's own `finalize_storages` cannot clean up:
`initialize_storages` sets `INITIALIZED` only after every storage succeeded, and `finalize_storages`
returns early on any other status, so the already-connected PostgreSQL references and Qdrant clients
would leak. The failure path therefore finalizes each storage object directly, and the instance is never
cached. `close()` releases every instance and the lock engine, and every runtime's `close()` already
called it.

**The connection budget, stated.** LightRAG's asyncpg pool is **process-wide** and is sized by
`POSTGRES_MAX_CONNECTIONS`, which this platform now sets from `RAG_GRAPH_DATABASE_MAX_CONNECTIONS`
(default 8, the value the previous `graph_max_async * 2` produced) — it is the ceiling for *all* of a
process's cached instances together, not per instance, and it belongs in the same total as the API,
agent, worker and checkpoint pools under the database's `max_connections` (ADR-0025). The workspace lock
adds one `NullPool` connection per in-flight graph *write* — that is, per graph-writing task, not per
cached instance — and none at all for queries.

**Storage configuration is a process-start contract, and a conflict is fatal.** LightRAG reads its
PostgreSQL and Qdrant configuration only from the environment, so the platform must write it. That write
now happens once, at startup, in `open_knowledge_graph`, and `POSTGRES_WORKSPACE`/`QDRANT_WORKSPACE` are
a **hard error** rather than being silently removed: `PGKVStorage.initialize` overrides an instance's
workspace with `POSTGRES_WORKSPACE` whenever it is set (`lightrag/kg/postgres_impl.py`), which would put
every knowledge base's graph in one workspace, and the previous `pop()` turned a cross-tenant isolation
failure into a warning nobody read. Refusing to start is the smaller blast radius.

**The graph's readiness is reported, and it is not the version's.** `graph_build_runs` already held the
graph's own `pending | building | ready | failed`, and it is now on the wire:
`GET /document-versions/{id}` answers `graph = {status, documents, attempt, error_class, error_message}`
or `null`, beside `parse_artifact` and *not* merged into the version's `status`. The two are independent
by construction (ADR-0022) and a `ready` version with a `pending` graph is exactly the normal state of a
knowledge base whose graph has not been built yet, so the response has to say both or a reader will infer
one from the other. No frontend change is part of this.

**Not in this ADR, deliberately.** Four things are known and recorded rather than fixed here.
(i) The graph channel's retrieval semantics are still LightRAG's defaults — `mode="mix"` with
`enable_rerank` left at its `True` default while this platform configures no `rerank_model_func`, so
LightRAG logs a warning per query and returns the chunk list unreranked. `mix` fuses graph and chunk
vector recall and is therefore a mixed candidate source, not a pure relation channel; choosing it, the
entity/relation/chunk budgets and `enable_rerank=False` are a measurement (dense/keyword/`mix`/`local`/
`global` on the evaluation set, with channel overlap) and are left to it with the current behaviour
pinned, not assumed to be right. (ii) A graph job whose worker is killed mid-build stays `running`; the
`rebuild-graph` operator command is the recovery path, and a stale-claim sweep for the graph stage
mirroring the parse lane's `stale_after` does not exist yet. (iii) `adelete_by_doc_id` is one call per
document, so a version's deletion cost is linear in its chunk count; the cleanup lane's attempt and
lease budgets are what bound it, and no measurement of a large version exists yet. (iv) LightRAG's
Qdrant storage is a **synchronous** client called from async methods with no thread offload
(`lightrag/kg/qdrant_impl.py`), so a graph query blocks the event loop for the duration of the Qdrant
call — including the agent runtime's, where it runs concurrently with the other channels' work. It is
LightRAG's code, reimplementing the storage is ADR-0022's explicit non-goal, and the mitigation that
does exist is the per-channel timeout. It is recorded as a standing risk instead of being papered over.

Evidence: `backend/src/infrastructure/graph/workspace_lock.py` (the session-level advisory lock on a
dedicated `NullPool` connection);
`backend/src/infrastructure/graph/storage_environment.py` (the startup contract and the refusal);
`backend/src/infrastructure/graph/instances.py` (the bounded cache, eviction, the direct per-storage
release on a failed initialization, and `drop_workspace` finalizing in a `finally`);
`backend/src/infrastructure/graph/lightrag.py` (one timeout per write covering the lock wait, the single
acquisition that spans `rebuild`'s delete and insert, the delete path's refusal of a non-`success`
status, and `duration_ms` on the build/query logs);
`backend/src/infrastructure/queue/job_queue.py` (the registered `TransientGraphBuildError`);
`backend/src/composition/shared/lightrag.py` and `backend/src/infrastructure/config/settings.py`
(`RAG_GRAPH_INSTANCE_LIMIT`, `RAG_GRAPH_DATABASE_MAX_CONNECTIONS`, the process-start environment);
`backend/src/api/knowledge_schemas.py`, `backend/src/api/documents.py`,
`backend/src/application/knowledge/document_catalog.py`,
`backend/src/infrastructure/db/stores/document_store.py` (the `graph` field and its read);
`docs/architecture/frontend-contract.md` (the wire contract); `lightrag-hku` 1.5.7 in `.venv`
(`lightrag/lightrag.py`, `lightrag/pipeline.py`, `lightrag/kg/shared_storage.py`,
`lightrag/kg/postgres_impl.py` `ClientManager`, `lightrag/kg/qdrant_impl.py`);
`scripts/probes/graph.ps1`.

## ADR-0029: The knowledge graph channel is removed; retrieval is dense + keyword

Status: accepted

**The decision.** The platform has two retrieval channels, not three. LightRAG leaves the dependency
graph, the `graph` channel leaves the retrieval lane, the `graph_build` stage leaves the ingestion
chain, and the tables, settings, wire fields, operator command, probe and frontend surfaces that only
existed for it are deleted rather than kept dormant.

**Why, in one paragraph each.**

*The channel did not earn its cost.* It carried a weight of 0.8 against two channels at 1.0 — the
lowest of the three — while accounting for by far the largest share of the platform's machinery: a
second storage registry, a per-knowledge-base workspace concept, a cross-process advisory lock, an
instance cache, a process-start environment contract that could refuse to boot, its own pool against
the database's `max_connections` (ADR-0025, ADR-0028), its own job stage, table and wire field. That is
a large surface for the weakest signal in the fusion.

*Its quality was never measured.* `docs/adr/README.md` ADR-0028 records the graph channel's retrieval
semantics as still LightRAG's defaults (`mode="mix"`, and LightRAG's own warning that it returns the
chunk list unreranked), and no evaluation of its contribution to the fused ranking exists. Keeping a
channel whose marginal recall is unquantified while it holds the largest blast radius is the opposite of
what a retrieval budget is for.

*Removing it costs nothing that is not rebuildable.* The graph was derived data: one document per child
chunk, keyed by the business identifiers (ADR-0022). Nothing in the citation path depended on it — a
citation is located by line range against the normalized Markdown (ADR-0016, ADR-0027) — and the
dense and keyword channels serve every `ready` version on their own.

**What this deletes, exactly.** `backend/src/infrastructure/graph/`, `domain/graph.py`,
`application/ingestion/graph.py`, `application/shared/knowledge_graph.py`,
`infrastructure/ingestion/graph_runs.py`, `infrastructure/retrieval/graph_channel.py`,
`composition/shared/lightrag.py`, the `graph_top_k`/`graph_weight`/`graph_*` settings, the
`graph` field on the version detail response, the `rebuild-graph` CLI command, migration
`0005_graph_build_runs`, `scripts/probes/graph.ps1`, the `lightrag-hku` and `numpy` dependencies (numpy
existed only for the embedding function handed to LightRAG) and the frontend's third channel, fifth
stage and graph settings group. `ChannelName` is `dense | keyword` and `IngestionStage` ends at
`index`.

**The schema is migrated, not rewritten.** A database already at `0010` holds `graph_build_runs` and a
`ck_ingestion_jobs_stage` that accepts `'graph_build'`, so `0011_drop_graph_channel` drops the table and
narrows the constraint (after deleting any `graph_build` job rows the narrower constraint would
reject). `0001_phase1_schema` is *not* edited — its own comment says later value changes arrive as new
revisions, and a migration records the schema as it was written. The table's own migration is gone
from the history, so a fresh database never creates it and `0005` no longer has a successor:
`0006_cleanup_intents` now revises `0004_conversations`. A database left sitting at exactly
`0005_graph_build_runs` is the one case that must be re-migrated by hand; it is the state of an
abandoned development database, not of a deployment, and this deployment is pre-production.

**The downgrade does not restore the table.** `0011`'s downgrade widens the stage constraint again
because that is a value domain a downgrade can honestly restore; it deliberately does not recreate
`graph_build_runs`, because no code in this revision writes it and a table restored by a downgrade
would then survive `downgrade base` (the migration that would have owned it is no longer in the
history).

**Two things `0011` deliberately leaves alone.** LightRAG provisioned its own PostgreSQL tables
(`lightrag_*`) and its own Qdrant collections (`lightrag_vdb_*`) outside this Alembic history
(ADR-0022). A database that once built a graph still carries them, and neither belongs to a migration:
their names and shapes are LightRAG's own version's, not this platform's schema. They are also why
`alembic check` reports drift on such a database — pre-existing behaviour, since the check has never
seen those tables in the metadata. Dropping them is a one-time operator step on a database that was
already migrated, not part of the upgrade:

```sql
-- one statement per table, because the list is the old LightRAG version's, not this schema's
DROP TABLE IF EXISTS lightrag_doc_full, lightrag_doc_chunks, lightrag_doc_status,
  lightrag_full_entities, lightrag_full_relations, lightrag_entity_chunks,
  lightrag_relation_chunks, lightrag_llm_cache, lightrag_graph_nodes, lightrag_graph_edges
  CASCADE;
```

The Qdrant side is a collection listing away (`GET /collections`, then delete every `lightrag_vdb_*`).
A database that never ran the graph channel needs neither.

**Reversal is a revert, not a setting.** The alternative considered was `RAG_GRAPH_ENABLED=false`
forever — a dormant channel with its code, dependency and pool still in the image. That was rejected:
`docs/development/coding-standards.md` and AGENTS.md both say a compatibility shim or a dormant second
path is worse than a deletion, and git is the record that makes the removal reversible.

Evidence: `backend/migrations/versions/0011_drop_graph_channel.py`;
`backend/src/domain/retrieval.py` (`ChannelName`); `backend/src/domain/knowledge.py` (`IngestionStage`);
`backend/src/composition/agent/runtime.py` (the two-channel tuple);
`backend/src/application/cleanup/service.py` (the index-only cleanup);
`pyproject.toml` (the removed dependencies); `scripts/probes/retrieval.ps1` (two channels, and their
count asserted); `scripts/probes/indexing.ps1` and `scripts/probes/chunking.ps1` (four stage rows).

## ADR-0030: The ingestion job row is the delivery contract, and the broker is only a wake-up

Status: accepted (supersedes ADR-0017's retry and delivery halves)

**One owner for delivery and retry.** A row in `ingestion_jobs` is the record of the work the platform
owes; a message is a hint that says "look at this job now". `pending` plus `not_before` is what is due,
`lease_expires_at` is how long a claim owns a job, and `dispatched_at` is the last publish, so the
dispatcher does not repeat one on every tick. `IngestionDispatch.reconcile()` — a background task in the
worker, every `RAG_JOB_DISPATCH_INTERVAL_SECONDS` (default 2 s) — reclaims expired leases and publishes
every job that is due. The publish that happens right after a commit, and the one that follows a
completed stage, stay as latency hints: their failure is logged and the next reconcile publishes the
job. At-least-once delivery is therefore a property of the row, not of the message.

**Why the job row is the outbox.** The pattern from microservices.io is "a table in the same database
holding the messages that must be sent, plus a relay". That table already exists here: every intent to
send is exactly one `pending` job row, written in the transaction that made it due
(`document_store.register` publishes a parse job, `append_stage_job` appends the next stage, and the
retry endpoint appends a revision). A second outbox table would be a second ledger that has to be
reconciled against this one, which is a new consistency problem rather than a solved one. River's
transactional enqueueing is the same conclusion at industrial scale: when the job row is committed with
the business change, there is no window in which the work exists but nothing will ever run it — the
window ADR-0017 left to the retry endpoint and to an operator.

**Retry has one owner, and it is not the transport.** `SmartRetryMiddleware`, the delay queue and the
`types_of_exceptions` whitelist are gone; the task is declared with no retry labels at all. The
middleware returned silently for an exception type that was not listed, while the stage's own recorder
had already put the job back to `pending` — a split state in which the row owed an attempt and no
message would ever arrive (the defect the audit reported as F-02). Now the stage writes the decision:
`RetrySchedule.next_attempt_at(attempt)` returns the next permitted delivery time, linear in the attempt
in a configured band (`min(delay x attempt, max)`, the same formula the middleware used, minus its
jitter), and otherwise the attempt is terminal. An unclassified exception is terminal
(`*_failed`/`manual_retry_required` with its `error_class`), which is what ADR-0017 already decided for
the parse stage and what the active `ingestion-pipeline.md` states as "retry only transient failures";
the chunk, embed and index stages now follow it instead of recording an unknown failure as retryable.

**A dead worker is recovered by the lease, not by an operator.** The lease is
`RAG_JOB_STALE_AFTER_SECONDS` (the same knob that named the staleness bound before, and it must stay
above the longest stage timeout). A claim whose lease expired is taken over: the job goes back to
`pending` with `not_before = now`, or — when the attempt budget is spent — terminal with
`error_class = AttemptLeaseExpired` and the version in its stage's failure status. Every takeover and
every settlement is fenced on `(id, status = 'running', attempt)`, the same shape ADR-0017 introduced
for cleanup intents, so a zombie delivery that returns after the takeover records nothing.

**The trade-off accepted.** Retry latency is now bounded by the dispatcher's tick plus the backoff
instead of by a per-message TTL in `taskiq.delay_queue`, and the dead-letter queue is observability only
(a failed delivery's message lands there, and the row is what carries the outcome). A deployment that
needs sub-second retries should add a dedicated dispatcher loop or PostgreSQL `LISTEN`/`NOTIFY`, not a
second retry layer: the row stays the source of truth either way.

Evidence: `backend/src/application/ingestion/dispatch.py`; `backend/src/infrastructure/ingestion/store.py`
(the claim/settlement/reclaim lifecycle, all fenced on the attempt);
`backend/src/infrastructure/ingestion/attempts.py`; `backend/src/domain/knowledge.py`
(`RetrySchedule`, `running_status_for`, `failure_status_for`);
`backend/migrations/versions/0012_ingestion_leases.py`; `backend/src/infrastructure/queue/job_queue.py`
(no middleware, no delay queue); `backend/src/worker/main.py` (the dispatcher task);
`scripts/probes/queue.ps1` (the topology no longer declares a delay queue, the retry decisions are read
back from the rows, the delays are the measured gaps between attempts, and the reconciler is asserted to
have published them); `scripts/probes/hardening.py` (the fence). Probes must be run in the container
topology before this is claimed as verified.

## ADR-0031: The parent chunk feeds generation and the child chunk anchors the citation

Status: accepted

**Two fields, two jobs.** `CitationSource` carries `context_text` — the parent chunk's aggregated text —
and the child's anchor (`child_id`, `line_start`, `line_end`, `quote`). `render_context` reads only the
former; `CitationService.resolve` re-reads the child row and takes the quote from there, so parent text
can never be presented as the quoted clause. `ChunkRecord` now carries `parent_content` and
`parent_token_count`, loaded by the same single query that hydrates the children (a join on
`parent_chunks`), so the retrieval lane does no second round trip and no per-candidate lookup.

**A parent's text enters the prompt once.** Sources stay one per child — a citation must point at a
child's line range — but the first source of a parent renders the section text and the following ones
render `Section: see [S1]`. Without that, three hits inside one 1600-token section would spend 4800
tokens on the same bytes.

**The budget counts what actually ships.** `select_context` renders each candidate block and counts the
rendered text with the same `TokenCounter` the chunker uses, so document names, heading paths and the
block markers are inside the budget rather than dropped from it (the audit's F-09). A group whose first
source does not fit is skipped whole, so a section never enters the prompt half-way. On top of the
context budget the settings validate the window arithmetic at startup —
`RAG_MAX_CONTEXT_TOKENS + RAG_CHAT_MAX_TOKENS + RAG_CHAT_PROMPT_RESERVE_TOKENS <= RAG_CHAT_CONTEXT_WINDOW`
— and `AnswerService` logs the token count of the whole assembled prompt, because the context is only
part of what a request costs.

Evidence: `backend/src/domain/citation.py`; `backend/src/infrastructure/db/stores/chunk_store.py`;
`backend/src/application/retrieval/{context,service}.py`; `backend/src/application/agent/answer.py`;
`backend/src/infrastructure/config/settings.py`; the contract this implements is
`docs/architecture/data-flow.md` ("Child is embedded and retrieved; parent is expanded for context")
and `docs/architecture/retrieval-pipeline.md` ("select parents under the context-token budget, keep
child anchors for citations"). The pattern is the one LlamaIndex's `SentenceWindowNodeParser` and
Anthropic's citations API describe: the window is generation context, the located span is the citation.

## ADR-0032: Untrusted document text has its own message, and citation trust has three layers

Status: accepted

**The boundary.** Retrieved document text never reaches the system prompt. The system message carries the
policy plus one paragraph that names the boundary: everything between `<evidence>` and `</evidence>` in
the following user message is quoted contract text — data, not instructions — and no text inside it can
change the rules, be executed, or become a source of citation numbers. The evidence travels as its own
user message, so the model's instruction layer and the analysed material are not the same message. This
is the shape OWASP's prompt-injection cheat sheet calls for ("keep trusted instructions separate from
untrusted data, but do not treat text labels or prompt wording as an enforcement boundary") — which is
also why the next point matters more than the wording.

**Our own protocol markers are sanitized out of source text.** Rendering strips `[source:S#]`,
`[/source:S#]` and `[S#]` from parent text, quotes and headings before they reach the prompt, so an
uploaded contract cannot forge a citation block, close one early, or hand the model a citation label the
backend would then have to reject. This is a structural check in our code, not a request to the model.

**Three layers, stated separately.** L1, citation-id legitimacy: every emitted `[S#]` must belong to
this request's evidence set and resolve to a stored child row (already implemented, unchanged). L2,
coverage: a grounded answer must carry at least one resolvable citation, and when it does not,
`validate_citations` writes `EvidenceStatus.UNVERIFIED` into the run's record instead of letting a
citation-free answer pass as a grounded one. L3, semantic support: whether the cited text actually
supports the sentence is a probabilistic question, so it stays in the evaluation lane
(`RAGAS faithfulness` in `V1_METRICS`) and must never be implied by "the citation was validated".

**Residual risk, stated rather than hidden.** None of this is a formal security boundary; the answer
text is still model output. What the design changes is the blast radius: no tools, no privileged actions,
sanitized markers, and an answer whose citations are either resolvable or explicitly unverified.

Evidence: `backend/src/application/agent/answer.py`; `backend/src/domain/citation.py`;
`backend/src/application/retrieval/citations.py`; `backend/src/agent_runtime/graph.py`;
`backend/src/domain/retrieval.py` (`EvidenceStatus.UNVERIFIED`);
`backend/src/infrastructure/evaluation/specs.py` (the faithfulness metric);
`scripts/probes/agent.ps1` (the adversarial-document, no-citation and unknown-id gates).

## ADR-0033: The demonstration deployment has no login; one platform principal owns everything

Status: accepted (withdraws ADR-0015)

The platform ships as a demonstration surface, so the login it used to require was removed rather than
kept behind a flag: the `users` and `sessions` tables are gone, the `/api/v1/auth/*` routes are gone,
`argon2-cffi` is out of the dependency set, and the frontend has no login route, no session query and no
route guard. Every request is the platform's own.

**One principal, not many.** `domain.identity.PLATFORM_OWNER_ID` is the identifier every API handler
passes as `owner_id`. It is a constant because there is exactly one caller; it lives in the domain
because a knowledge base and a conversation both carry `owner_id` as part of their identity, and one
constant keeps "nobody is logged in" a single fact instead of three routers' worth of assumptions.

**Why `owner_id` stays.** Migration `0014_remove_login` drops the account tables but keeps the column on
`knowledge_bases` and `conversations`: `uq_knowledge_bases_owner_id_name`, both owner-leading indexes and
`fk_conversations_owner_matches_kb` — the constraint that keeps a conversation inside its own knowledge
base — are built on it. Dropping the column would be a schema rewrite of the knowledge, conversation and
cleanup lanes for no demonstration value; the migration instead re-keys every existing row to the
platform principal, so the data that used to belong to the probe accounts (the CUAD corpus among it)
stays visible. The composite foreign key had to step aside for that re-key, because it is checked at the
end of each statement and the parent cannot move to the new owner while its children still name the old
one; it is recreated unchanged once both tables are on the platform principal.

**What the removal costs.** Two invariants die with the accounts, and their probes with them: "every
endpoint answers 401 without a session" and "a second user sees none of the first user's resources, 404
and never 403". `scripts/probes/auth.ps1` is deleted, and the ingestion probe's ownership section is
replaced by the surviving half of the same rule — an identifier nothing owns is answered 404, never 403
and never 500. The per-request isolation code is gone, so anything reachable from the browser can read
and delete everything in the platform. That is the trade this decision makes, and it is why the platform
must not be exposed with data that matters.

**Reversal.** Regaining login means a migration that recreates `users` and `sessions` (0014's downgrade
restores their shape, with the platform principal as the only account and a hash no verification can
match), a new authentication service, and the guard, login route and session query back on the frontend.
The `owner_id` plumbing never left, so the isolation half of the reversal is already in place.

Evidence: `backend/src/domain/identity.py`; `backend/migrations/versions/0014_remove_login.py`;
`backend/src/api/conversations.py`; `scripts/probes/ingestion.ps1`;
`frontend/src/routes/app-routes.tsx`.
