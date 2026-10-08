# Research: Langfuse self-host (v4 line) and Aegra — official-source verification

Scope: verify (A) the official Langfuse v4 self-hosting service list, image names/tags, required environment
variables, web/worker split, external-infrastructure reuse, Python SDK minimal API and the "do not read Langfuse
tables" statement, upgrade/migration and ClickHouse disk notes; and (B) what `github.com/aegra/aegra` actually is
(runtime/HTTP server, version, activity, license, production suitability).

Research date context: evidence collected from live official pages; newest artifacts observed were
`langfuse` SDK 4.16.0 (PyPI upload 2026-09-30) and `aegra-api` 0.10.8 (PyPI upload 2026-10-01).

---

## Summary

Langfuse v4 self-hosting officially uses exactly two application containers (`langfuse/langfuse` web +
`langfuse/langfuse-worker`) plus Postgres, ClickHouse, Redis/Valkey and S3-compatible blob storage; ClickHouse is
mandatory and has a hard version floor (>= 25.12, 26.4 recommended). External/managed Postgres, Redis and S3 are
explicitly supported and recommended — but Langfuse uses the `public` schema of the selected database, so logical
isolation must be a **separate database** (plus separate Redis keyspace/`REDIS_KEY_PREFIX` and separate bucket or
prefix), not a shared schema. Overall the project's system-overview claims are confirmed, with three concrete
conflicts/risks: single-container ClickHouse is only community/dev-supported, PostgreSQL is documented as
"16 recommended" (our local `postgres:18-alpine` is above the documented target), and RustFS is not an officially
listed blob-storage provider (falls under "Other S3-compatible providers" = Community support). Aegra exists, is
Apache-2.0, actively released (0.10.8, 2026-10-01) and is a self-hosted Agent Protocol / LangGraph HTTP server that
replaces LangSmith Deployments; it is classified by its own publisher as "Development Status :: 4 - Beta".

---

## Findings

### A) Langfuse self-hosting (v4)

1. **Service list (minimum) = 2 app containers + 4 storage components; only Web must be publicly reachable.**
   Claim: Langfuse consists of Langfuse Web, Langfuse Worker, Postgres (OLTP), ClickHouse (OLAP), Redis/Valkey
   (cache+queue) and S3/blob storage; an LLM API/gateway is optional.
   Source: https://langfuse.com/self-hosting/deployment/infrastructure/containers ,
   https://langfuse.com/self-hosting (architecture diagram + bullet list)
   Key text: "Langfuse consists of two application containers, storage components, and an optional LLM
   API/Gateway." / "**Langfuse Web**: The web server that serves the Langfuse Console and API." /
   "**Langfuse Worker**: The worker that handles background tasks such as sending emails or processing events." /
   "Only the langfuse-web container and minio must be accessible from outside the instance."
   Support: direct evidence. Confidence: high.

2. **Official image names and tags: `langfuse/langfuse` (web) and `langfuse/langfuse-worker` (worker); floater tag
   `:4` selects the latest 4.x patch.**
   Claim: images are published on Docker Hub as `langfuse/langfuse` and `langfuse/langfuse-worker`; the docs' run
   examples use `docker.langfuse.com/langfuse/langfuse:4` and `.../langfuse-worker:4`; the Helm-side guidance says
   "You can automatically use the latest version of a major release by using `langfuse/langfuse:4` and
   `langfuse/langfuse-worker:4` as the image tags".
   Source: https://langfuse.com/self-hosting/deployment/infrastructure/containers ,
   https://langfuse.com/self-hosting/upgrade
   Support: direct evidence. Confidence: high.
   Note (interpretation): the worker listens on `3030`, web on `3000` (`PORT` default "3000 / 3030; 3000 for web,
   3030 for worker"). For reproducible pinning, pin an explicit 4.x patch rather than `:4`.

3. **ClickHouse image and version floor: `clickhouse/clickhouse-server`, Langfuse v4 requires >= 25.12 and
   recommends 26.4; ClickHouse is mandatory.**
   Claim: official docker-compose/infra guidance uses the upstream `clickhouse/clickhouse-server` image, and
   "Langfuse v4 requires ClickHouse >= 25.12 (26.4 recommended) for lightweight updates, the JSON type, and
   full-text search". Also: "Yes, ClickHouse is currently a required component for self-hosting Langfuse. There is
   no alternative OLAP database supported at this time."
   Source: https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse ,
   https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4 (step 1 table)
   Key text: "Langfuse v4 raises the minimum infrastructure versions: ClickHouse 25.12 minimum, 26.4 recommended.
   PostgreSQL 15 minimum, 16 recommended. Redis 7.0 minimum, 7.2 recommended."
   Support: direct evidence. Confidence: high.
   Consequence for this project (interpretation): our local image inventory has no ClickHouse image, so Phase 5
   needs `clickhouse/clickhouse-server:26.4` (or newer 26.x) pulled; a `CHANGEME`-style floating `:latest` is not
   acceptable for a pinned deployment.

4. **ClickHouse "single-container Docker" is officially only community-supported and marked development-only.**
   Claim: the support-level table lists "Single-container Docker (development only)" as **Community** (best-effort),
   while ClickHouse Cloud / BYOC / ClickHouse Kubernetes Operator are Official.
   Source: https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse (support-level table)
   Key text: "**Community**: Expected to work based on community usage. We do not systematically test these
   options; support is best-effort..." plus the same page's Docker section: "As there is no redundancy, this is
   not recommended for production workloads."
   Support: direct evidence. Confidence: high.
   Conflict flag (interpretation): running a single ClickHouse container (the obvious Phase-5 compose shape) is
   possible but is *not* an officially supported production topology; state this explicitly in the architecture doc
   or accept the risk consciously.

5. **Required environment variables, by category (all must be set on BOTH web and worker unless noted).**
   **PostgreSQL:** `DATABASE_URL` (required; alternatively `DATABASE_HOST`/`DATABASE_USERNAME`/`DATABASE_PASSWORD`/
   `DATABASE_NAME`/`DATABASE_ARGS`), `DIRECT_URL` (migrations; defaults to `DATABASE_URL`), `SHADOW_DATABASE_URL`
   (only if the DB user lacks `CREATE DATABASE`), `LANGFUSE_AUTO_POSTGRES_MIGRATION_DISABLED` (default `false`).
   **Redis:** `REDIS_CONNECTION_STRING` (required; or `REDIS_HOST`/`REDIS_PORT`/`REDIS_USERNAME`/`REDIS_AUTH`),
   `REDIS_KEY_PREFIX` (optional, isolation), plus `REDIS_CLUSTER_*`/`REDIS_SENTINEL_*`/`REDIS_TLS_*` only for those
   topologies.
   **ClickHouse:** `CLICKHOUSE_MIGRATION_URL` (required, TCP 9000/9440), `CLICKHOUSE_URL` (required, HTTP 8123/8443),
   `CLICKHOUSE_USER` (required), `CLICKHOUSE_PASSWORD` (required), `CLICKHOUSE_DB` (default `default`),
   `CLICKHOUSE_CLUSTER_ENABLED` (default `true` in docs; set `false` for single container),
   `LANGFUSE_AUTO_CLICKHOUSE_MIGRATION_DISABLED` (default `false`), `CLICKHOUSE_READ_ONLY_URL` (optional).
   **Object storage (S3/RustFS-compatible):** `LANGFUSE_S3_EVENT_UPLOAD_BUCKET` (required),
   `_REGION`, `_ENDPOINT`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY`, `_FORCE_PATH_STYLE`, `_PREFIX`;
   `LANGFUSE_S3_MEDIA_UPLOAD_*` (config table marks `LANGFUSE_S3_MEDIA_UPLOAD_BUCKET` as required; endpoint defaults
   to `http://localhost:9090` in the compose file because browsers upload media directly); `LANGFUSE_S3_BATCH_EXPORT_*`
   (opt-in, `LANGFUSE_S3_BATCH_EXPORT_ENABLED=false`); compatibility knobs `LANGFUSE_S3_DELETE_OBJECTS_CHECKSUM_ALGORITHM`,
   `LANGFUSE_S3_CONCURRENT_WRITES/READS`, and `LANGFUSE_BLOB_STORAGE_ENDPOINT` allowlist for private endpoints.
   **Encryption/secret keys:** `NEXTAUTH_URL` (required), `NEXTAUTH_SECRET` (required; `openssl rand -base64 32`),
   `SALT` (required; salts hashed API keys), `ENCRYPTION_KEY` (required; exactly 64 hex chars = 256 bits,
   `openssl rand -hex 32`).
   **One-time init (web container only):** `LANGFUSE_INIT_ORG_ID` (+`_NAME`), `LANGFUSE_INIT_PROJECT_ID`
   (+`_NAME`, `_RETENTION`), `LANGFUSE_INIT_PROJECT_PUBLIC_KEY`/`_SECRET_KEY`, `LANGFUSE_INIT_USER_EMAIL`/`_NAME`/
   `_PASSWORD` — "Langfuse will automatically create the specified resources on startup if they don't already
   exist"; org must be initialized before project/user.
   Sources: https://langfuse.com/self-hosting/configuration ,
   https://langfuse.com/self-hosting/administration/headless-initialization ,
   https://langfuse.com/self-hosting/deployment/infrastructure/blobstorage ,
   https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse ,
   https://langfuse.com/self-hosting/deployment/infrastructure/cache ,
   https://langfuse.com/self-hosting/deployment/infrastructure/containers ,
   https://langfuse.com/self-hosting/configuration/encryption ,
   https://github.com/langfuse/langfuse/blob/7c501c41/docker-compose.yml
   Support: direct evidence (variable names and defaults quoted from the official tables/YAML).
   Confidence: high, with one caveat: `NEXTAUTH_SECRET` appears only on `langfuse-web` in the official
   docker-compose.yml while the containers page sets `SALT`/`ENCRYPTION_KEY` on both — see Contradictions.

6. **Web vs worker are split by function, and running without the worker means traces never reach ClickHouse.**
   Claim: web serves UI/API, writes incoming events to S3 and only a queue reference to Redis; the worker picks the
   events from S3 and ingests them into ClickHouse. Worker also handles emails and (optionally) evals.
   Source: https://langfuse.com/self-hosting (ingestion bullets + diagram),
   https://langfuse.com/self-hosting/deployment/infrastructure/containers
   Key text: "**Queued trace ingestion**: All traces are received in batches by the Langfuse Web container and
   immediately written to S3. Only a reference is persisted in Redis for queueing. Afterwards, the Langfuse Worker
   will pick up the traces from S3 and ingest them into Clickhouse." / "Worker -..->|optional for evals| LLM"
   Support: direct evidence for the split; the "both must run" conclusion is source interpretation. Confidence: high.

7. **Official recommendation: run the app containers separately, ≥2 CPU / 4 GiB each; ≥2 web instances for HA.**
   Source: https://langfuse.com/self-hosting/deployment/infrastructure/containers
   Key text: "For production environments, we recommend to use at least 2 CPUs and 4 GB of RAM for all containers.
   You should have at least two instances of the Langfuse Web container for high availability."
   Support: direct evidence. Confidence: high.

8. **Reusing external Postgres/Redis/S3: yes — officially supported and recommended; isolation is by
   database / keyspace-prefix / bucket-prefix / ClickHouse DB, NOT by a shared schema.**
   - Postgres: "Langfuse supports Postgres versions >= 12 and uses the `public` schema in the selected database."
     (https://langfuse.com/self-hosting/deployment/infrastructure/postgres); the Helm docs state for new installs
     "we recommend connecting the chart to components that you manage outside of it wherever possible" and show
     `postgresql.deploy: false` + external host (https://github.com/langfuse/langfuse-k8s/).
   - Redis: "You can use a managed service on AWS, Azure, or GCP, or host it yourself. At least version 7 is
     required and the instance must have `maxmemory-policy=noeviction` configured."; `REDIS_KEY_PREFIX`
     = "Optional prefix for all Redis keys to avoid key collisions with other applications. Should end with `:`.";
     `REDIS_CONNECTION_STRING` format includes `/db-number` (separate logical DB).
     (https://langfuse.com/self-hosting/deployment/infrastructure/cache)
   - Blob storage: "Langfuse supports any S3-compatible storage provider"; official list = Amazon S3, GCS, Azure
     Blob, Cloudflare R2, SeaweedFS, MinIO/AIStor; `LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE` "Required for
     SeaweedFS and MinIO"; `LANGFUSE_S3_EVENT_UPLOAD_PREFIX` isolates a subpath of a shared bucket.
     (https://langfuse.com/self-hosting/deployment/infrastructure/blobstorage)
   - ClickHouse: `CLICKHOUSE_DB` (default `default`) selects the database name.
   Support: direct evidence for each mechanism; the mapping onto "one shared Postgres/Redis/RustFS" is source
   interpretation. Confidence: high.
   Conflict flag: because Langfuse hard-codes the `public` schema in its selected database, a **separate PostgreSQL
   database** is required — a "separate schema inside the shared business database" design is not documented as
   supported.

9. **Python SDK: current version 4.16.0 (2026-09-30); minimal observation API is `get_client()` +
   `start_as_current_observation(as_type=...)`.**
   Claim: pip package `langfuse`, `requires_python = ">=3.10,<4.0"`, latest observed release 4.16.0.
   Source: https://pypi.org/pypi/langfuse/json (info.version 4.16.0, upload_time_iso_8601 2026-09-30T09:55:54Z)
   Official minimal shape (verbatim from the quickstart):
   ```python
   # env: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL
   from langfuse import get_client
   langfuse = get_client()
   with langfuse.start_as_current_observation(as_type="span", name="process-request") as span:
       span.update(output="Processing complete")
       with langfuse.start_as_current_observation(
           as_type="generation", name="llm-response", model="gpt-3.5-turbo"
       ) as generation:
           generation.update(output="Generated response")
   langfuse.flush()
   ```
   Sources: https://langfuse.com/docs/observability/get-started ,
   https://langfuse.com/docs/observability/sdk/python/overview
   Support: direct evidence (code quoted from official quickstart; version from PyPI JSON). Confidence: high.
   Version-compatibility (direct evidence, https://langfuse.com/self-hosting/upgrade/versioning): "Python SDK v4 —
   OSS v3: ≥ 3.63.0; OSS v4: Full"; v2 observations/metrics APIs require server v4; "For real-time visibility on
   the v4 data model, use Python SDK ≥ 4.7.0" (upgrade guide) — i.e. pin `langfuse>=4.7` (prefer 4.16.x) for a v4
   server.

10. **Official statement matching the project rule "do not read Langfuse tables directly" — with a nuance.**
    Claim: Langfuse says not to *write* to its tables directly and warns the ClickHouse schema is not a stable API;
    it tells integrators to prefer the Public API / SDK query helpers / MCP server / Blob Storage Export, but it
    does *not* forbid read-only queries outright.
    Source: https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse
    Key text: "Do not write directly to Langfuse tables. Use the Public API or SDKs for creating and updating
    Langfuse data." / "The ClickHouse schema is not a stable API contract. Major Langfuse upgrades, background
    migrations, and performance work ... can change tables, columns, deduplication behavior, or join patterns at any
    time." / "... for integrations and custom applications, prefer the Public API, SDK query helpers, MCP server, or
    Blob Storage Export. These interfaces are the compatibility targets across Langfuse releases." / "If you do
    query ClickHouse directly: use a dedicated read-only user ..., keep direct analytical traffic away from the
    primary ingestion path."
    Support: direct evidence. Confidence: high.
    Interpretation: the project rule is stricter than the official text but consistent with its intent
    ("compatibility targets" are the APIs/SDK); our doc should cite the schema-instability sentence as the reason,
    not claim Langfuse bans reads.

11. **Upgrade/migration requirements.**
    - Within a major version: "Updates within a major version are designed to be non-disruptive and are
      automatically applied. On start of the application, all migrations are automatically applied to the
      databases." Upgrading = swap image (`docker compose up --pull always`) / update Helm release.
      (https://langfuse.com/self-hosting/upgrade)
    - Major version: follow the guide; v3→v4 requires (a) upgrading ClickHouse *before* the server (v3 releases
      run fine on new ClickHouse), (b) Postgres 15+ (16 recommended), Redis 7+ (7.2 recommended), (c) latest v3
      release with all background migrations finished, (d) a backup taken before the upgrade, (e) an explicit
      ClickHouse user grant set.
      (https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4)
    - Migration-only variables (not needed for a fresh v4 deploy; defaults: `events_only` / `direct` / `true` /
      backfill `true`): `LANGFUSE_MIGRATION_V4_WRITE_MODE` (`legacy|dual|events_only`),
      `LANGFUSE_MIGRATION_V4_NATIVE_OTEL_BEHAVIOUR`, `LANGFUSE_MIGRATION_V4_ALLOW_PREVIEW_OPT_IN`,
      `LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL`,
      `LANGFUSE_BACKGROUND_MIGRATION_V4_DROP_PID_TID_SORTING_TABLES`. "The `legacy` and `dual` modes are migration
      utilities, not permanent operating modes: they will be removed in an upcoming major version."
      (https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4)
    - Helm chart is versioned separately; bundled-ClickHouse installs must go chart v1→v2 before the v4 server
      upgrade. (https://langfuse.com/self-hosting/upgrade)
    Support: direct evidence. Confidence: high.
    Project consequence (interpretation): a Phase-5 *fresh* v4 deployment needs no migration flags; it must,
    however, treat image-tag bumps as "migrations run on startup" events and keep `DIRECT_URL`/grants ready.

12. **ClickHouse data-volume / disk guidance.**
    Claim: min spec 2 CPU/8 GiB, ≥16 GiB RAM recommended for larger deployments; ClickHouse disk growth is usually
    dominated by ClickHouse *system* log tables that Langfuse never reads; the primary lever is a data-retention
    policy, the secondary is disabling/ТTL-ing those log tables; the automated v3→v4 backfill needs roughly 3x the
    current data volume on disk.
    Sources: https://langfuse.com/self-hosting/configuration/scaling ,
    https://langfuse.com/faq/all/reduce-clickhouse-disk-size ,
    https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4
    Key text: "ClickHouse 2 CPU, 8 GiB Memory" (minimum table); "In general, we recommend at least 16 GiB of memory
    for larger deployments."; "On default ClickHouse configurations, the system log tables (`trace_log`, `text_log`,
    `opentelemetry_span_log`, `asynchronous_metric_log`, `metric_log`, `latency_log`) can dominate disk usage. They
    have no TTL by default ... Langfuse does not read from these tables, so you can safely reduce them."; "make sure
    the ClickHouse disks can handle roughly **3x the current data volume**"; S3 lifecycle advice: "For most
    customers, a default of 30 days is a good choice" (not for the media bucket).
    Support: direct evidence. Confidence: high.
    Also relevant: both Postgres and ClickHouse must run with timezone UTC (same pages) — "Non-UTC timezones will
    cause queries to return incorrect or empty results."

13. **ClickHouse user grants required (operational prerequisite for our compose/env).** Langfuse needs DDL, not just
    SELECT/INSERT: `GRANT SELECT, INSERT ON default.*`, `ALTER UPDATE, ALTER DELETE`, `CREATE, DROP TABLE, DROP VIEW`,
    `ALTER ADD COLUMN, ALTER MODIFY COLUMN, ALTER VIEW MODIFY QUERY`, `ALTER ADD|DROP|MATERIALIZE INDEX`, plus v4
    system-table reads (`system.parts`, `system.mutations`, `system.tables`, `system.processes`, `system.query_log*`).
    Source: https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse#user-permissions
    Support: direct evidence. Confidence: high.

### B) Aegra (github.com/aegra/aegra)

14. **Aegra exists and is a self-hosted LangGraph/Agent-Protocol HTTP runtime — not merely a library.**
    Claim: "Aegra is a drop-in replacement for LangSmith Deployments. Use the same LangGraph SDK, same APIs, but run
    it on your own infrastructure with PostgreSQL persistence." It is "Agent Protocol compliant" and works with
    Agent Chat UI, LangGraph Studio, AG-UI/CopilotKit; it exposes an HTTP API (`http://localhost:2026/docs`) plus a
    Redis-backed worker architecture with 30 concurrent runs per instance.
    Sources: https://github.com/aegra/aegra (README), https://docs.aegra.dev/why-aegra ,
    local clone of `github.com/aegra/aegra` (`README.md`, `docs/reference/*`)
    Support: direct evidence. Confidence: high.
    Found via the exact URL given in the task; the repo resolved and cloned successfully, so the "does not exist /
    renamed" hypothesis is rejected.

15. **Version, activity, license, Python support.**
    Claim: PyPI `aegra-api` latest observed = **0.10.8**, uploaded 2026-10-01; `requires_python >=3.12`; license
    `Apache-2.0` (`license_expression`), and the repo `LICENSE` file is the Apache License 2.0 text; PyPI classifier
    `Development Status :: 4 - Beta`; dependencies include `fastapi`, `langgraph>=1.0.3`, `sqlalchemy>=2.0`,
    `redis[hiredis]>=5`, `opentelemetry-*`, `psycopg[binary]>=3.2.9`; GitHub Releases list v0.10.8 … v0.10.2 with
    merged external-contributor PRs across releases; the clone's Alembic history runs to
    `20260822000000_add_thread_ttl_table.py`.
    Sources: https://pypi.org/pypi/aegra-api/json , https://github.com/aegra/aegra/releases ,
    local clone `pyproject.toml`/`LICENSE`/`libs/aegra-api/alembic/versions/`
    Support: direct evidence (versions, dates, license, classifier quoted from PyPI JSON/repo). Confidence: high.
    Caveat (missing evidence): a precise latest-commit timestamp could not be obtained (GitHub REST API returned
    HTTP 403 rate-limit; the HTML commits page rendered only one stale commit card). Freshness is therefore evidenced
    by the 2026-10-01 PyPI release plus recent migration files, not by a commit timestamp.

16. **Documentation target of "production": Aegra claims production deployment paths but self-labels beta.**
    Claim: docs present `aegra up` as "the recommended production deployment for your own infrastructure"
    (Postgres + Redis + app in Docker), with Kubernetes and HA guides; `why-aegra` says "Aegra covers the core
    capabilities needed for production agent deployments"; the PyPI classifier still says Beta.
    Sources: https://docs.aegra.dev/why-aegra , local clone `docs/guides/deployment.mdx`,
    `docs/guides/high-availability.mdx`, https://pypi.org/pypi/aegra-api/json
    Support: direct evidence for both statements; the tension is real, not resolved by the vendor.
    Confidence: high for the quotes, medium for any "safe to depend on in production" inference.

17. **Aegra's tracing path is OpenTelemetry fan-out, not the Langfuse SDK.**
    Claim: `OTEL_TARGETS="LANGFUSE"` + `LANGFUSE_BASE_URL`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`; Langfuse is
    listed as a supported OTLP backend alongside Phoenix/Jaeger/Datadog; "Aegra uses OpenTelemetry for all
    observability."
    Sources: local clone `docs/guides/observability.mdx`, https://github.com/aegra/aegra (README feature list)
    Support: direct evidence. Confidence: high.
    Interpretation relevant to this project: adopting Aegra means application-level traces reach Langfuse as OTLP
    spans (Langfuse officially supports `POST /api/public/otel/v1/traces`, GA), which is a *different* integration
    from "our own application code emits observations via the Langfuse Python SDK"; the architecture rule would need
    to say which path owns tracing.

18. **Cost/benefit of "LangGraph + our own FastAPI runtime" vs "adopt Aegra" — fact-level comparison.**
    The project architecture already states "FastAPI + Aegra/LangGraph runtime" and "No Aegra core worker fork", so
    the decision is about the deployment dependency, not existence.
    - Aegra gives, per its own docs: Agent Protocol compliance and LangGraph SDK compatibility
      ("Your existing LangGraph code works without changes"), assistants/threads CRUD with versioning, PostgreSQL
      checkpoints, SSE streaming (8 modes + Agent Protocol v2 thread-scoped streaming), HITL, cron, Redis worker
      queue with lease-based crash recovery and horizontal scaling, configurable auth handlers, pgvector semantic
      store, custom FastAPI routes, OTLP tracing fan-out, Docker/PaaS/K8s deployment guides.
      Sources: https://github.com/aegra/aegra , https://docs.aegra.dev/why-aegra , local clone `docs/feature-support.mdx`,
      `docs/guides/deployment.mdx`, `docs/guides/worker-architecture.mdx`.
    - Aegra costs/constraints, per its own docs: Apache-2.0 but Beta classifier; a second process topology plus
      Postgres schema and Redis queue to operate (`aegra up` = Postgres + Redis + app; `REDIS_BROKER_ENABLED=true`);
      API/schema surface owned by the project (its own Alembic migrations, thread TTL, assistants store) — i.e. the
      run/thread/assistant tables become part of our data model; tracing goes through OTLP rather than the Langfuse
      SDK; the project's own comparison table positions it against LangSmith Deployments (enterprise licensing) as
      its main alternative, not against a self-built runtime.
      Sources: local clone `docs/guides/deployment.mdx`, `docs/reference/configuration.mdx`, `docs/why-aegra.mdx`.
    - Building our own runtime gives: no extra runtime dependency, full control of the API/SSE/citation contracts,
      and reuse of our own auth/observability policy; it costs the whole thread/checkpoint/streaming/HITL/cron
      surface that Aegra already implements and tests, plus its crash-recovery/HA semantics.
      Support: the first two bullets are direct evidence; the third is researcher inference from the project's own
      architecture doc ("No Aegra core worker fork" implies selective adoption is already contemplated).
      Confidence: high (evidence) / medium (the build-vs-adopt cost inference).

19. **Aegra version-pinning surface is unusual but documented:** "Always install `aegra-cli` directly — not the
    `aegra` meta-package. The `aegra` package on PyPI is a convenience wrapper that does not support version pinning."
    Sources: https://github.com/aegra/aegra (README), https://pypi.org/pypi/aegra-api/json
    Support: direct evidence. Confidence: high.

---

## Contradictions

1. **`NEXTAUTH_SECRET` placement.** The official `docker-compose.yml` in `langfuse/langfuse` sets
   `NEXTAUTH_SECRET` only on the `langfuse-web` service (worker env block omits it), while the same repo's compose
   shares `SALT` and `ENCRYPTION_KEY` with the worker. The configuration page, however, describes `NEXTAUTH_URL`
   as "Keep it public on web and worker." → Verify at runtime whether the worker actually requires
   `NEXTAUTH_SECRET` before omitting it.
   Sources: https://github.com/langfuse/langfuse/blob/7c501c41/docker-compose.yml ,
   https://langfuse.com/self-hosting/configuration
2. **Image tag `:3` vs `:4`.** The compose file fetched from `langfuse/langfuse` (commit `7c501c41`) pins
   `langfuse/langfuse:3` / `langfuse/langfuse-worker:3`, whereas the documentation's container page and upgrade page
   use `:4`. Resolution: treat the docs as authoritative for the v4 line and pin an explicit 4.x patch (verify the
   tag/digest on the machine before deploying).
   Sources: https://github.com/langfuse/langfuse/blob/7c501c41/docker-compose.yml ,
   https://langfuse.com/self-hosting/deployment/infrastructure/containers
3. **PostgreSQL version claim.** Postgres page says "Langfuse supports Postgres versions >= 12", while the v4 text
   says "PostgreSQL 16 is recommended and the minimum PostgreSQL version is 15". Our local image `postgres:18-alpine`
   is above the documented "recommended" version and is not an explicitly named tested target.
   Sources: https://langfuse.com/self-hosting/deployment/infrastructure/postgres ,
   https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4
4. **`CLICKHOUSE_CLUSTER_ENABLED` default.** The ClickHouse page's variable table says default `true`, while the
   upgrade guide's step-1 guidance and the docker-compose example use `false` for single-container setups. Use
   `false` for our single-node ClickHouse and run migrations with `LANGFUSE_AUTO_CLICKHOUSE_MIGRATION_DISABLED`
   considered only if we manage migrations ourselves.
   Sources: https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse ,
   https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4
5. **"Do not read Langfuse tables" is stronger in our project doc than in the official text.** Official wording
   forbids *writes* and warns that the schema is not a stable contract; it explicitly allows direct read queries by
   self-hosters (with a read-only user). Our architecture rule should cite the schema-instability rationale.
   Sources: https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse
6. **"Community Redis-compatible" vs official support.** The cache page lists Redis (>= 7) and Valkey (>= 8) as
   official but states "Langfuse expects that the provided user has access to all keys and commands within the given
   database, i.e. the access control should be defined as `on ~* +@all`", which sits in tension with the documented
   `REDIS_KEY_PREFIX` isolation knob (prefix isolates keys but the ACL must still be all-keys).
   Sources: https://langfuse.com/self-hosting/deployment/infrastructure/cache
7. **Aegra "production" vs "Beta".** Aegra's docs describe `aegra up` as the recommended production deployment and
   claim production-grade feature coverage, while its own PyPI metadata is `Development Status :: 4 - Beta` and the
   README markets it as a replacement for LangSmith **Deployments** (a managed product). No official statement of
   support/SLA/versioning policy for breaking changes was found.
   Sources: local clone `docs/guides/deployment.mdx`, `docs/why-aegra.mdx`, https://pypi.org/pypi/aegra-api/json

---

## Missing evidence

1. **No official Langfuse statement that RustFS is supported.** RustFS does not appear anywhere in the Langfuse
   docs/site (searched the blob-storage page and Langfuse docs text). It would fall under "Other S3-compatible
   providers" = **Community** support, with `LANGFUSE_S3_*_FORCE_PATH_STYLE=true` and
   `LANGFUSE_BLOB_STORAGE_ENDPOINT` (if the endpoint is a private address) as required knobs. Needs real-machine
   verification — exact commands to run on the host:
   ```powershell
   # 1. Confirm the RustFS image/API actually implements the S3 calls Langfuse makes
   docker run --rm -it rustfs/rustfs:1.0.0 --help
   # 2. From inside a container on the same network, preflight bucket + permissions (List/Get/Put)
   docker run --rm --network <langfuse_net> --entrypoint sh minio/mc:latest -c `
     "mc alias set rfs http://rustfs:9000 <ak> <sk> && mc mb -p rfs/langfuse && mc cp <file> rfs/langfuse/events/ && mc ls rfs/langfuse"
   # 3. Then start langfuse-web with LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE=true and confirm ingestion:
   #    a test trace must appear in the UI, and `SELECT count() FROM events` in ClickHouse must be > 0
   ```
2. **No official statement on whether Langfuse's Prisma migrations work against PostgreSQL 18**, nor on whether a
   Postgres user without `CREATE DATABASE` requires `SHADOW_DATABASE_URL` in a Docker/Creatable-database setup.
   Verify: create a throwaway database, set `DATABASE_URL`/`DIRECT_URL` with a least-privilege user, start web, and
   watch startup migrations:
   ```powershell
   docker compose up -d langfuse-web; docker compose logs -f langfuse-web | Select-String -Pattern "migration|SHADOW|error"
   ```
3. **No precise Aegra commit timestamp / contributor count.** GitHub REST API was rate-limited (HTTP 403) and the
   commit page did not render dates. Activity proxy used: PyPI 0.10.8 (2026-10-01), release notes with outside
   contributors, and Alembic migration dated 2026-08-22. Verify with your own GitHub token:
   `curl -H "Authorization: Bearer $GH_TOKEN" https://api.github.com/repos/aegra/aegra` (fields `pushed_at`,
   `stargazers_count`) and `.../releases/latest` (`published_at`).
4. **No official Langfuse statement that the two containers are *both mandatory*.** Evidence is the ingestion
   pipeline description (worker picks events from S3 → ClickHouse) rather than an explicit "worker is required"
   sentence. Verify empirically: run web only and confirm traces never appear / `SELECT count() FROM events` stays 0.
5. **Aegra's support/compatibility policy for LangGraph SDK versions is unverified** (which `langgraph` and
   `langgraph_sdk` versions a given Aegra release guarantees). Verify from the pinned release metadata:
   `uv pip show aegra-api` / read `libs/aegra-api/pyproject.toml` at the tagged release.
6. **Production-readiness evidence for Aegra is vendor-claimed only** (docs pages, README). No independent
   benchmark, external case study, or third-party security review was found in this pass.
7. **Sizing of the Langfuse S3 blob storage for our workload**: Langfuse recommends keeping events "for as long as
   you want to access them within the UI", "a default of 30 days is a good choice" for lifecycle rules — there is no
   official per-trace size figure to plan RustFS capacity with.

---

## Sources

- Kept:
  - Self-host Langfuse overview — https://langfuse.com/self-hosting — service map, ingestion pipeline, UTC requirement.
  - Application Containers (self-hosted) — https://langfuse.com/self-hosting/deployment/infrastructure/containers — image names/tags, web/worker split, sizing, ports.
  - Configuration via Environment Variables — https://langfuse.com/self-hosting/configuration — canonical variable names/defaults (Postgres, Redis, ClickHouse, S3, secrets).
  - ClickHouse (self-hosted) — https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse — version floor, support levels (single-container = Community), grants, "do not write directly to Langfuse tables", schema-stability statement.
  - Cache (Redis/Valkey) — https://langfuse.com/self-hosting/deployment/infrastructure/cache — version/`noeviction`, `REDIS_KEY_PREFIX`, ACL expectation, memory sizing.
  - Postgres Database (self-hosted) — https://langfuse.com/self-hosting/deployment/infrastructure/postgres — `public` schema, support levels, v4 version guidance.
  - S3 / Blob Storage — https://langfuse.com/self-hosting/deployment/infrastructure/blobstorage — provider support levels, `FORCE_PATH_STYLE`, prefixes, private-endpoint allowlist.
  - Headless Initialization — https://langfuse.com/self-hosting/administration/headless-initialization — one-time `LANGFUSE_INIT_*` variables.
  - Scaling Langfuse — https://langfuse.com/self-hosting/configuration/scaling — minimum specs, ClickHouse memory advice, system-log tables, `CLICKHOUSE_READ_ONLY_URL`.
  - Reduce ClickHouse disk size FAQ — https://langfuse.com/faq/all/reduce-clickhouse-disk-size — retention vs system-table levers.
  - Upgrading a self-hosted deployment — https://langfuse.com/self-hosting/upgrade — minor vs major, auto-migrations, Helm chart versioning.
  - Migrate v3 → v4 (self-hosted) — https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4 — version floors, migration variables, 3x disk note, cutover semantics.
  - Versions & Compatibility (self-hosted) — https://langfuse.com/self-hosting/upgrade/versioning — SDK↔server matrix.
  - Python quickstart — https://langfuse.com/docs/observability/get-started and https://langfuse.com/docs/observability/sdk/python/overview — minimal `get_client()` + `start_as_current_observation()` example.
  - PyPI `langfuse` JSON — https://pypi.org/pypi/langfuse/json — version 4.16.0, 2026-09-30, `requires_python <4.0,>=3.10`.
  - Aegra repository — https://github.com/aegra/aegra (README) and local clone — purpose, features, install guidance.
  - Aegra Why/Deployment/Observability/Feature-support docs — https://docs.aegra.dev/why-aegra , local clone `docs/guides/deployment.mdx`, `docs/guides/observability.mdx`, `docs/feature-support.mdx`, `docs/guides/worker-architecture.mdx` — runtime topology, OTLP-to-Langfuse path, production phrasing.
  - Aegra releases — https://github.com/aegra/aegra/releases — v0.10.8 … v0.10.2 with changelogs.
  - PyPI `aegra-api` JSON — https://pypi.org/pypi/aegra-api/json — version 0.10.8 (2026-10-01), Apache-2.0, Beta classifier, `requires_python >=3.12`.
  - langfuse-k8s (external components) — https://github.com/langfuse/langfuse-k8s/ — official recommendation to connect the chart to externally managed Postgres/Redis/ClickHouse/blob storage, plus external-Postgres YAML.
- Rejected/deprioritized:
  - theneuralbase.com "ClickHouse for analytics" and perlod.com troubleshooting guide — third-party SEO content with stale/incorrect advice (e.g. `LANGFUSE_ANALYTICS_ENGINE`), superseded by official pages.
  - `https://langfuse.com/self-hosting/v2/deployment-guide` — v2-only variable set (`SALT`, `NEXTAUTH_SECRET`, `DATABASE_URL`), would mislead v4 configuration.
  - Langfuse GitHub Discussion #1957 / deployment-strategies page — relevant to multi-deployment isolation but secondary; referenced only where it supports the "single deployment + RBAC" recommendation.
  - `github.com/aegra/aegra/commits/main` HTML — rendered one stale commit without dates; replaced by PyPI release timestamps as activity evidence.
  - `api.github.com/repos/aegra/aegra` — HTTP 403 rate limit; returned no data.
