# Probe: Python 3.12 dependency resolution & key class availability

> **Historical (ADR-0029).** The LightRAG sections below (together with `.probe\lightrag-out.txt`) were
> measured while the graph channel existed; `lightrag-hku` and `numpy` are no longer dependencies and
> `lightrag` is not importable. The rest of the resolution record still describes this environment.

Date: 2026-10-02 · Env: Windows, PowerShell 7 · cwd `D:\YZB\RAG` · `uv 0.12.13`
Interpreter: CPython 3.12.14 (`uv venv .probe\venv-resolution --python 3.12`)
All evidence below is from commands actually executed in this session. Raw outputs kept in
`.probe\resolution-freeze.txt`, `.probe\imports-out.txt`, `.probe\langgraph-pg-out.txt`,
`.probe\taskiq-broker-out.txt`.

Install command (resolved cleanly, no conflict, 129 distributions):

```powershell
New-Item -ItemType Directory -Force .probe
uv venv .probe\venv-resolution --python 3.12
uv pip install --python .probe\venv-resolution fastapi "uvicorn[standard]" pydantic pydantic-settings `
  sqlalchemy alembic asyncpg taskiq structlog argon2-cffi boto3 redis qdrant-client langchain `
  langgraph langgraph-checkpoint-postgres langchain-openai lightrag-hku langfuse httpx `
  python-multipart aio-pika
```

---

## (a) Full resolved version table — `uv pip freeze --python .probe\venv-resolution`

```
aio-pika==10.1.0
aiohappyeyeballs==2.7.1
aiohttp==3.14.3
aiormq==7.2.1
aiosignal==1.4.0
alembic==1.20.0
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.15.1
argon2-cffi==25.1.0
argon2-cffi-bindings==26.1.0
ascii-colors==0.12.3
asyncpg==0.31.0
attrs==26.1.0
backoff==2.2.1
boto3==1.43.106
botocore==1.43.106
certifi==2026.7.22
cffi==2.1.1
charset-normalizer==3.5.2
click==8.5.0
configparser==7.2.0
cryptography==50.0.2
distro==1.9.0
fastapi==0.142.2
frozenlist==1.8.0
google-api-core==2.40.0
google-auth==2.59.1
google-genai==2.26.0
googleapis-common-protos==1.75.5
grpcio==1.84.0
h11==0.16.0
h2==4.4.1
hpack==4.2.0
httpcore==1.0.9
httpcore2==2.13.1
httptools==0.8.0
httpx==0.28.1
httpx2==2.13.1
hyperframe==6.1.0
idna==3.20
jiter==0.17.0
jmespath==1.1.0
json-repair==0.63.5
jsonpatch==1.33
jsonpointer==3.1.1
langchain==1.4.3
langchain-core==1.6.6
langchain-openai==1.6.7
langchain-protocol==0.0.19
langfuse==4.16.0
langgraph==1.2.12
langgraph-checkpoint==4.2.0
langgraph-checkpoint-postgres==3.1.2
langgraph-prebuilt==1.1.0
langgraph-sdk==0.4.5
langsmith==0.14.2
lightrag-hku==1.5.7
mako==1.4.3
markupsafe==3.0.3
multidict==6.9.1
nano-vectordb==0.0.4.3
networkx==3.7
numpy==2.5.3
openai==3.22.0
opentelemetry-api==1.45.0
opentelemetry-exporter-http-transport==0.66b0
opentelemetry-exporter-otlp-common==0.66b0
opentelemetry-exporter-otlp-proto-common==1.45.0
opentelemetry-exporter-otlp-proto-http==1.45.0
opentelemetry-proto==1.45.0
opentelemetry-sdk==1.45.0
opentelemetry-semantic-conventions==0.66b0
orjson==3.12.0
ormsgpack==1.12.2
packaging==26.3
pamqp==4.0.1
pandas==3.0.6
pipmaster==1.1.13
portalocker==3.2.0
propcache==0.5.4
proto-plus==1.28.4
protobuf==7.36.2
psycopg==3.3.6
psycopg-pool==3.3.3
pyasn1==0.6.4
pyasn1-modules==0.4.2
pycparser==3.0
pycron==3.3.0
pydantic==2.13.5
pydantic-core==2.46.5
pydantic-settings==2.15.0
pypinyin==0.55.0
python-dateutil==2.9.0.post0
python-dotenv==1.2.3
python-multipart==0.0.32
pywin32==312
pyyaml==6.0.3
qdrant-client==1.19.1
redis==8.1.0
regex==2026.9.10
requests==2.34.2
requests-toolbelt==1.0.0
s3transfer==0.19.2
setuptools==84.0.0
six==1.17.0
sniffio==1.3.1
sqlalchemy==2.1.1
starlette==1.7.0
structlog==26.1.0
taskiq==0.13.0
taskiq-dependencies==1.5.7
tenacity==9.1.4
tiktoken==0.14.0
truststore==0.10.4
typing-extensions==4.16.0
typing-inspection==0.4.4
tzdata==2026.4
urllib3==2.8.0
uuid-utils==0.17.1
uvicorn==0.54.0
watchfiles==1.3.0
wcwidth==0.9.1
websockets==16.1.1
wrapt==2.5.0
xlsxwriter==3.2.9
xxhash==4.0.1
yarl==1.25.1
zstandard==0.25.0
```

### Required additions found by this probe (must be pinned in the project lock)

| Package | Why | Evidence |
|---|---|---|
| `psycopg[binary]` (→ `psycopg-binary==3.3.6`) | `import langgraph.checkpoint.postgres` **fails** without a libpq wrapper | see (b) FAIL line; fixed by `uv pip install --python .probe\venv-resolution "psycopg[binary]"`, then `pq impl: binary`, `libpq: 180004` |
| `taskiq-aio-pika==0.6.1` | taskiq core ships **no** RabbitMQ broker | see (c) |
| `apscheduler==3.11.3` | 4.x is alpha-only | see (d) |

Note (dependency burden, not a blocker): `lightrag-hku` **base** install (no extras) already
requires `google-genai>=1.0.0,<3.0.0` and `google-api-core`, which dragged in
`google-genai==2.26.0`, `grpcio==1.84.0`, `protobuf==7.36.2`, `googleapis-common-protos`,
`proto-plus`, `pandas==3.0.6`, `numpy==2.5.3`, `tiktoken`, `xlsxwriter`. Also
`langgraph-checkpoint-postgres` pins `langgraph-checkpoint<5.0.0,>=4.1.0` → resolved `4.2.0`.
`lightrag.kg.postgres_impl` imports `asyncpg` directly (module-level), so `asyncpg` is a hard
requirement for any PG-backed LightRAG storage; `lightrag.kg.pgtable_impl` has no third-party
runtime import beyond `tenacity`.

---

## (b) Per-module import smoke (`/.probe/venv-resolution/Scripts/python.exe .probe/smoke_imports.py`)

```
python 3.12.14 (main, Sep  1 2026, 14:17:39) [MSC v.1944 64 bit (AMD64)]
OK   fastapi 0.142.2
OK   pydantic 2.13.5
OK   pydantic_settings 2.15.0
OK   sqlalchemy 2.1.1
OK   alembic 1.20.0
OK   asyncpg 0.31.0
OK   taskiq 0.13.0
OK   structlog 26.1.0
OK   argon2 25.1.0        (DeprecationWarning: accessing argon2.__version__ is deprecated)
OK   boto3 1.43.106
OK   redis 8.1.0
OK   qdrant_client        (no __version__ attr; use importlib.metadata -> 1.19.1)
OK   langchain 1.4.3
OK   langgraph            (no __version__ attr; namespace pkg, __file__=None -> 1.2.12)
FAIL langgraph.checkpoint.postgres: ImportError: no pq wrapper available.
       - couldn't import psycopg 'c' implementation: No module named 'psycopg_c'
       - couldn't import psycopg 'binary' implementation: No module named 'psycopg_binary'
       - couldn't import psycopg 'python' implementation: libpq library not found
OK   lightrag 1.5.7
OK   langfuse 4.16.0
OK   httpx 0.28.1
OK   aio_pika 10.1.0
OK   multipart 0.0.32
```

The single FAIL is a **real dependency gap, not an environment quirk**.
`langgraph_checkpoint_postgres-3.1.2.dist-info/METADATA` says:

```
Requires-Dist: psycopg>=3.2.0
```

i.e. bare `psycopg` (no extra). The package README states verbatim:

> By default, `langgraph-checkpoint-postgres` installs `psycopg` (Psycopg 3) without any
> extras. You can choose a specific installation that best suits your needs … for example
> `psycopg[binary]`.

After `uv pip install --python .probe\venv-resolution "psycopg[binary]"` the import succeeds
(`psycopg 3.3.6`, `pq impl: binary`, `libpq: 180004`).

**Action for pyproject:** declare `psycopg[binary]` (or `psycopg[c]`) explicitly.

Related imports verified in the same venv while checking log/trace wiring:

```
from langfuse.langchain import CallbackHandler  -> <class 'langfuse.langchain.CallbackHandler.LangchainCallbackHandler'>
langfuse top-level (4.16.0): Langfuse, get_client, observe, propagate_attributes, api, types,
  LangfuseGeneration, LangfuseSpan, LangfuseAgent, LangfuseEmbedding, LangfuseRetriever, media, ...
```

`qdrant_client` and `langgraph` expose no `__version__`; pin/read them through `importlib.metadata
.version("qdrant-client") == "1.19.1"` and `version("langgraph") == "1.2.12"`.

---

## (c) Taskiq RabbitMQ broker — decision

PyPI existence probe (`Invoke-RestMethod https://pypi.org/pypi/<name>/json`):

| candidate | result |
|---|---|
| `taskiq-aio-pika` | **FOUND 0.6.1**, `requires_python >=3.10,<4`, summary "RabbitMQ broker for taskiq", author Pavel Kirilin (taskiq author), classifier `Development Status :: 3 - Alpha`, `Requires-Dist: taskiq>=0.12.0,<1`, `aio-pika>=9.0.0` |
| `taskiq-rabbitmq` | MISS — HTTP 404 |
| `taskiq-amqp` | MISS — HTTP 404 |
| `taskiq-aiopika` | MISS — HTTP 404 |

taskiq **core 0.13.0** ships only `taskiq.brokers.{inmemory_broker, shared_broker, zmq_broker}`;
top-level broker exports are `AsyncBroker, BrokerMessage, InMemoryBroker, ZeroMQBroker`. There is
no RabbitMQ/AMQP broker inside taskiq itself.

Installed (`uv venv .probe\venv-broker` + `uv pip install taskiq taskiq-aio-pika aio-pika`) →
`taskiq==0.13.0, taskiq-aio-pika==0.6.1, aio-pika==10.1.0, aiormq==7.2.1, pamqp==4.0.1`.

Import path: `import taskiq_aio_pika` → `__all__ = ['AioPikaBroker', 'Exchange', 'Queue', 'QueueType']`;
class is `taskiq_aio_pika.broker.AioPikaBroker` (subclass of `taskiq.AsyncBroker`).

Construction smoke (no network) — verbatim signatures:

```
AioPikaBroker.__init__(self, url: str | None = None, result_backend: AsyncResultBackend | None = None,
  task_id_generator: Callable[[], str] | None = None, qos: int = 10, loop=None,
  exchange: Exchange | None = None, task_queues: list[Queue] | None = None,
  dead_letter_queue: Queue | None = None, delay_queue: Queue | None = None,
  delayed_message_exchange_plugin: bool = False, delayed_message_exchange: Exchange | None = None,
  label_for_routing: str = 'queue_name', label_for_priority: str = 'priority', **connection_kwargs)
InMemoryBroker.__init__(self, sync_tasks_pool_size: int = 4, max_stored_results: int = 100,
  cast_types: bool = True, max_async_tasks: int = 30, max_async_tasks_jitter: int = 0,
  propagate_exceptions: bool = True, await_inplace: bool = False)
```

Broker built OK: `AioPikaBroker("amqp://probe:probe@127.0.0.1:55672//")` → `.result_backend` is a
`DummyResultBackend` by default, `.middlewares == []`, `.serializer` is `JSONSerializer`,
`is_worker_process == False`. `@broker.task` decoration works and derives
`task_name = .probe.smoke_taskiq_broker:probe_task` from module path.

Signature deltas — `only in AioPikaBroker`: `url, result_backend, task_id_generator, qos, loop,
exchange, task_queues, dead_letter_queue, delay_queue, delayed_message_exchange_plugin,
delayed_message_exchange, label_for_routing, label_for_priority, connection_kwargs`.
`only in InMemoryBroker`: `sync_tasks_pool_size, max_stored_results, cast_types, max_async_tasks,
max_async_tasks_jitter, propagate_exceptions, await_inplace`. Both subclass `AsyncBroker`; the
`AioPikaBroker` surface used by the app must be `kick/listen/startup/shutdown/with_result_backend/
with_middlewares/with_serializer` (all present; `kick(message) -> None`,
`listen() -> AsyncGenerator[AckableMessage, None]`).

Also useful for queue/DLX configuration at construction time:
`Queue.__init__(declare=True, type=QueueType.QUORUM, name='taskiq', durable=True,
exclusive=False, passive=False, auto_delete=False, max_priority=None, arguments={},
timeout=None, routing_key=None, bind_arguments={}, bind_timeout=None, consumer_arguments={})`,
`QueueType ∈ {QUORUM, CLASSIC, STREAM}`, and
`Exchange.__init__(name='taskiq', type=ExchangeType.TOPIC, internal=False, passive=False,
auto_delete=False, declare=True, durable=True, arguments={}, timeout=None)`.
Note there is no `broker.queue_name` / `broker.exchange_name` attribute — queue identity lives in
`task_queues`/`exchange`, so app config must be passed as those objects.

**Decision:** RabbitMQ via taskiq requires the third-party `taskiq-aio-pika==0.6.1` (alpha).
`aio-pika` alone gives no taskiq broker. Keep `aio-pika` in the matrix as the underlying transport
that `taskiq-aio-pika` uses; do not use it as the broker abstraction directly.

---

## (d) APScheduler 3 vs 4

`uv pip install --python .probe\venv-aps4 --prerelease=allow "apscheduler>=4"`:

```
× No solution found when resolving dependencies:
╰─▶ Because only apscheduler<=4.0.0a6 is available and you require apscheduler>=4,
    we can conclude that your requirements are unsatisfiable.
```

PyPI JSON (`https://pypi.org/pypi/apscheduler/json`): `info.version = 3.11.3`,
`requires_python = >=3.8`; release list ends `…3.9.1.post1, 4.0.0a1 … 4.0.0a6`; `4.0.0a6`
uploaded `2025-04-27`. **There is no stable 4.x release — only alphas.**

4.x *can* be installed with an exact pin: `uv pip install --python .probe\venv-aps4 "apscheduler==4.0.0a6"`
→ `apscheduler==4.0.0a6` (+ `anyio, attrs, tenacity, tzdata, tzlocal`).

4.0.0a6 shape (verbatim):

```
top-level: AsyncScheduler, Scheduler, Schedule, Task, CoalescePolicy, ConflictPolicy,
           SchedulerRole, RetrySettings, current_async_scheduler, current_job, ...
submodules: abc, datastores, eventbrokers, executors, serializers, triggers
AsyncScheduler.__init__(self, data_store: DataStore = NOTHING, event_broker: EventBroker = NOTHING,
  lease_duration: timedelta|int = 30, *, identity: str = '', role=SchedulerRole.both,
  task_defaults=NOTHING, max_concurrent_jobs: int = 100, job_executors=NOTHING,
  cleanup_interval: timedelta|int = 900, logger=...)
apscheduler.schedulers.asyncio.AsyncIOScheduler -> ModuleNotFoundError: No module named 'apscheduler.schedulers'
apscheduler.datastores.memory.MemoryDataStore -> OK
apscheduler.datastores.sqlalchemy -> needs sqlalchemy[asyncio] (greenlet) + async driver
SQLAlchemyDataStore.__init__(self, engine_or_url: str|URL|Engine|AsyncEngine, *,
  retry_settings=RetrySettings(...), serializer=Serializer, start_from_scratch: bool = False,
  schema: str|None = None)
```

`SQLAlchemyDataStore` failed with `ModuleNotFoundError: No module named 'sniffio'`, then with
`ImportError: The SQLAlchemy asyncio module requires … 'greenlet'`; after
`uv pip install --python .probe\venv-aps4 "sqlalchemy[asyncio]" asyncpg sniffio` it imports and
exposes the signature above. So 4.x persistent store = **async** engine
(`sqlalchemy.ext.asyncio` + asyncpg).

3.11.3 shape (`uv venv .probe\venv-aps3` + `uv pip install "apscheduler==3.11.3" sqlalchemy`):

```
AsyncIOScheduler.__init__(self, gconfig={}, **options)
SQLAlchemyJobStore.__init__(self, url=None, engine=None, tablename='apscheduler_jobs',
  metadata=None, pickle_protocol=5, tableschema=None, engine_options=None)
AsyncIOExecutor.__init__(self)
add_job -> tick (trigger: interval[0:00:30], pending)   # scheduling API works without start()
remove_job ok; jobs left: []
create_engine("postgresql+asyncpg://…") -> ModuleNotFoundError: No module named 'asyncpg'   (sync Engine)
create_engine("postgresql+psycopg2://…") -> ModuleNotFoundError: No module named 'psycopg2'
create_engine("postgresql+psycopg://…")  -> ModuleNotFoundError: No module named 'psycopg'
```

Note: in 3.11.3 a job returned by `add_job` has **no** `next_run_time` attribute before the
scheduler starts (`AttributeError: 'Job' object has no attribute 'next_run_time'`; the repr shows
`pending`).

3.x persistent jobstore takes a **sync** SQLAlchemy URL/Engine → needs a sync driver
(`psycopg2` or `psycopg` sync); the project's `asyncpg` is not usable there. The strings
`postgresql+asyncpg` / `postgresql+psycopg2` / `postgresql+psycopg` all failed here only because
the driver wheels were absent from that probe venv — that is the point being evidenced: a driver
must be added.

**Decision: use APScheduler 3.11.3 (stable).** Reasons: (1) no stable 4.x exists — only
`4.0.0a6` alpha; (2) `>=4` is literally unresolvable by uv without `--prerelease=allow`; (3) 4.x
is a breaking rewrite (module paths change: `apscheduler.schedulers.*` and `apscheduler.jobstores.*`
disappear, replaced by `AsyncScheduler` + `datastores/`); (4) 3.11.3's `AsyncIOScheduler` +
`AsyncIOExecutor` is exactly the async scheduling the app needs, and a durable jobstore is available
via `SQLAlchemyJobStore(url=…)`. Cost of 3.x: a sync DB driver must be pinned for the jobstore
(pick `psycopg` sync, matching the psycopg already present). Revisit when 4.0.0 final ships.

---

## (e) LightRAG 1.5.7 and LangGraph 1.2.12 class availability

### LightRAG (`lightrag-hku==1.5.7`, imported top-level as `lightrag`)

`lightrag.LightRAG` → `<class 'lightrag.lightrag.LightRAG'>` ✔

**Correction to the assumed module paths** — `PGTableGraphStorage` is **not** in
`lightrag.kg.postgres_impl`:

| class | requested path | actual |
|---|---|---|
| `PGKVStorage` | `lightrag.kg.postgres_impl` | ✔ present (line 3120) |
| `PGDocStatusStorage` | `lightrag.kg.postgres_impl` | ✔ present (line 5457) |
| `PGTableGraphStorage` | `lightrag.kg.postgres_impl` | ✘ MISSING → actual path **`lightrag.kg.pgtable_impl.PGTableGraphStorage`** (line 267) |
| `QdrantVectorDBStorage` | `lightrag.kg.qdrant_impl` | ✔ present |
| `PGVectorStorage` | — | ✔ present in `lightrag.kg.postgres_impl` (line 3866) |
| `PGGraphStorage` | — | ✔ present in `lightrag.kg.postgres_impl` (line 7209) |

Other public classes in `lightrag.kg.postgres_impl`: `BaseGraphStorage, BaseKVStorage,
BaseVectorStorage, DocStatusStorage, PostgreSQLDB, ClientManager, DocStatus, DocStatusPage,
DocSchedulingRecord, KnowledgeGraph, KnowledgeGraphNode, KnowledgeGraphEdge, NameSpace,
SourceConflict…, PGGraphQueryException, PGGraphEdgeWriteLostError, StorageControlPlaneError,
StorageRecordNotFoundError, DataMigrationError`. `__all__` is undefined in both modules.

Constructors (verbatim):

```
lightrag.kg.postgres_impl.PGKVStorage.__init__(self, namespace: str, workspace: str, global_config: dict[str, Any], embedding_func: EmbeddingFunc, db: PostgreSQLDB = None)
lightrag.kg.postgres_impl.PGDocStatusStorage.__init__(self, namespace: str, workspace: str, global_config: dict[str, Any], embedding_func: EmbeddingFunc, db: PostgreSQLDB = None)
lightrag.kg.postgres_impl.PGGraphStorage.__init__(self, namespace: str, workspace: str, global_config: dict[str, Any], embedding_func: EmbeddingFunc)
lightrag.kg.pgtable_impl.PGTableGraphStorage.__init__(self, namespace: str, workspace: str, global_config: dict[str, Any], embedding_func: EmbeddingFunc)
lightrag.kg.qdrant_impl.QdrantVectorDBStorage.__init__(self, namespace, global_config, embedding_func, workspace=None, meta_fields=None)
```

`lightrag.kg` module inventory (from `pkgutil.iter_modules(lightrag.kg.__path__)`):

```
factory, faiss_impl, json_doc_status_impl, json_kv_impl, memgraph_impl, milvus_impl, mongo_impl,
nano_vector_db_impl, neo4j_impl, networkx_impl, noop_vector_db_impl, opensearch_impl,
pgtable_impl, pipeline_ingress, postgres_impl, qdrant_impl, redis_impl, scan_job_store,
shared_storage, write_seq
```

Storage registry `lightrag.kg.factory.STORAGES` (config strings → modules) — the strings that must
be passed to `LightRAG(..., kv_storage=…, vector_storage=…, graph_storage=…, doc_status_storage=…)`:

```
PGKVStorage -> .kg.postgres_impl        PGDocStatusStorage -> .kg.postgres_impl
PGVectorStorage -> .kg.postgres_impl    PGGraphStorage -> .kg.postgres_impl
PGTableGraphStorage -> .kg.pgtable_impl QdrantVectorDBStorage -> .kg.qdrant_impl
NetworkXStorage -> .kg.networkx_impl    NanoVectorDBStorage -> .kg.nano_vector_db_impl
JsonKVStorage -> .kg.json_kv_impl       JsonDocStatusStorage -> .kg.json_doc_status_impl
(+ Chroma/Faiss/Milvus/Mongo/Neo4J/Memgraph/OpenSearch/Redis/AGE/Noop)
```

`LightRAG.__init__` defaults confirm the JSON/NetworkX/NanoVectorDB default set, so the project must
override all four storages explicitly.
`LightRAG.__init__` signature highlights relevant to config wiring: `working_dir,
kv_storage='JsonKVStorage', vector_storage='NanoVectorDBStorage', graph_storage='NetworkXStorage',
doc_status_storage='JsonDocStatusStorage', workspace=<factory>, chunk_token_size=None,
chunk_overlap_token_size=None, embedding_func, embedding_batch_num=10, embedding_func_max_async=8,
default_embedding_timeout=30, llm_model_func, llm_model_name='gpt-4o-mini', llm_model_max_async=4,
default_llm_timeout=240, entity_extraction_use_json=False, rerank_model_func,
rerank_model_max_async=4, default_rerank_timeout=30, min_rerank_score=0.0,
vector_db_storage_cls_kwargs=<factory>, max_parallel_insert=3,
pipeline_require_strict_storage_reads=False, cosine_better_than_threshold=0.2`.

Workspace isolation is real and lives inside these storages: `lightrag/kg/qdrant_impl.py` defines
`DEFAULT_WORKSPACE = "_"`, `WORKSPACE_ID_FIELD = "workspace_id"`,
`workspace_filter_condition(workspace)` (a Qdrant `FieldCondition` on `workspace_id`), and a
collection-name ladder preferring `"{workspace}_{namespace}"`; `pgtable_impl`/`postgres_impl` call
`validate_workspace`. This supports the "separate business vs LightRAG storage" requirement at the
library level, but the *effective* collection names must be confirmed against a live Qdrant
(see open item O6).

### LangGraph (`langgraph==1.2.12`, `langgraph-checkpoint-postgres==3.1.2`)

Availability after adding `psycopg[binary]`:

```
PostgresSaver: langgraph.checkpoint.postgres.PostgresSaver
  setup signature: (self) -> 'None'
  from_conn_string: (conn_string: str, *, pipeline: bool = False) -> Iterator[PostgresSaver]
  MIGRATIONS count: 10   # first: "CREATE TABLE IF NOT EXISTS checkpoint_migrations ( v INTEGER PRIMARY KEY );"
AsyncPostgresSaver: langgraph.checkpoint.postgres.aio.AsyncPostgresSaver
  setup signature: (self) -> 'None'      setup is coroutine function: True
  has asetup alias: False
  from_conn_string: (conn_string: str, *, pipeline: bool = False, serde: SerializerProtocol | None = None) -> AsyncIterator[AsyncPostgresSaver]
  MIGRATIONS count: 10
  async methods present: ['aget_tuple', 'aput', 'aput_writes', 'alist', 'adelete_thread']
package __all__: ['PostgresSaver', 'BasePostgresSaver', 'ShallowPostgresSaver', 'Conn']
hasattr(pkg, 'AsyncPostgresSaver'): False
```

**Import-path correction:** `from langgraph.checkpoint.postgres import AsyncPostgresSaver` raises
`ImportError: cannot import name 'AsyncPostgresSaver' … Did you mean: 'BasePostgresSaver'?`. The
async saver must be imported from **`langgraph.checkpoint.postgres.aio`**. Also the legacy `asetup()`
alias no longer exists — the coroutine is named `setup()`. `setup()` migrations create the graph on
first use; the 10 migrations cover `checkpoint_migrations`, `checkpoints`, `checkpoint_blobs`,
`checkpoint_writes` (exact table list to be confirmed by the live probe, open item O1).
Additional classes present in 3.1.2: `ShallowPostgresSaver` (sync),
`AsyncShallowPostgresSaver` (aio), `BasePostgresSaver`.

---

## (f) Open items — each with its exact verification command

| # | Open item | Exact command to resolve |
|---|---|---|
| O1 | Real tables created by `AsyncPostgresSaver.setup()` against Postgres 18 (the script must run on a Selector loop on Windows — see the event-loop note below), and that `asetup` really is gone in production code | `.\probe\venv-resolution\Scripts\python.exe .probe\pg_setup_probe.py` then `docker exec ragprobe-pg psql -U postgres -c "\dt"` (live-probe container, owned by the `live` worker) |
| O2 | Whether `postgres:18-alpine` ships `pgvector` (decides `PGVectorStorage` usability) | `docker exec ragprobe-pg psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"` / `SELECT * FROM pg_available_extensions WHERE name='vector';` |
| O3 | `taskiq-aio-pika==0.6.1` runtime behaviour (alpha) against RabbitMQ 4.3.6: quorum `task_queues`, `dead_letter_queue`, `delay_queue`, worker `listen()` ack semantics | `uv venv .probe\venv-live-rmq; uv pip install --python .probe\venv-live-rmq taskiq taskiq-aio-pika` then a script that builds `AioPikaBroker("amqp://probe:probe@127.0.0.1:55672//", task_queues=[Queue(name="rag-probe", type=QueueType.QUORUM)])`, `await broker.startup()`, `await broker.kick(...)`, iterate `broker.listen()` |
| O4 | APScheduler decision confirmation (3.11.3 vs waiting for 4.0.0 final) is a product/architecture call | `uv pip install --dry-run --python .probe\venv-aps4 --prerelease=allow "apscheduler>=4"` → currently unsatisfiable; re-check with `Invoke-RestMethod https://pypi.org/pypi/apscheduler/json | % info.version` |
| O5 | Which sync driver to pin for the 3.x `SQLAlchemyJobStore` (`psycopg` sync vs `psycopg2`) | `uv pip install --python .probe\venv-aps3 "psycopg[binary]"; .\probe\venv-aps3\Scripts\python.exe -c "from sqlalchemy import create_engine; e=create_engine('postgresql+psycopg://postgres:probe@127.0.0.1:55432/postgres'); print(e.dialect.driver)"` |
| O6 | Effective Qdrant collection names for a given LightRAG `workspace` (proves business/LightRAG isolation) | `.\probe\venv-resolution\Scripts\python.exe -c "import asyncio;from lightrag.kg.qdrant_impl import QdrantVectorDBStorage"`; then live: build storage with `workspace='biz'` / `workspace='lightrag'` against `127.0.0.1:56333` and `client.get_collections()` |
| O7 | Whether `langfuse==4.16.0` interoperates with `langchain==1.4.3` / `langgraph==1.2.12` (LangChain callback handler) | `.\probe\venv-resolution\Scripts\python.exe -c "from langfuse.langchain import CallbackHandler; print(CallbackHandler)"` → **(RESOLVED: yes)** `<class 'langfuse.langchain.CallbackHandler.LangchainCallbackHandler'>`. The remaining open part is runtime trace delivery, which needs a live Langfuse server; provider facts are in the providers probe report. |
| O8 | Whether `lightrag-hku`'s transitive `google-genai`/`google-api-core`/`grpcio` load must be accepted in the runtime image | `uv pip tree --python .probe\venv-resolution --package lightrag-hku` (verified runnable — prints `lightrag-hku v1.5.7 ├── aiohttp v3.14.3 … ├── google-api-core v2.40.0 └── google-genai`; only matters if image size is constrained) |
| O9 | import-smoke re-run must include `langgraph.checkpoint.postgres` **and** `.aio` after `psycopg[binary]` is pinned in the real project env | `uv run python -c "import langgraph.checkpoint.postgres, langgraph.checkpoint.postgres.aio; print('ok')"` |

---

## Reproduction (all commands, in order)

```powershell
cd D:\YZB\RAG
uv --version                                              # 0.12.13
New-Item -ItemType Directory -Force .probe
uv venv .probe\venv-resolution --python 3.12
uv pip install --python .probe\venv-resolution fastapi "uvicorn[standard]" pydantic pydantic-settings `
  sqlalchemy alembic asyncpg taskiq structlog argon2-cffi boto3 redis qdrant-client langchain `
  langgraph langgraph-checkpoint-postgres langchain-openai lightrag-hku langfuse httpx `
  python-multipart aio-pika
uv pip freeze --python .probe\venv-resolution | Tee-Object .probe\resolution-freeze.txt
.probe\venv-resolution\Scripts\python.exe .probe\smoke_imports.py            # (b)
uv pip install --python .probe\venv-resolution "psycopg[binary]"
.probe\venv-resolution\Scripts\python.exe .probe\smoke_langgraph_pg.py       # (e) LangGraph
.probe\venv-resolution\Scripts\python.exe .probe\smoke_lightrag.py          # (e) LightRAG
uv venv .probe\venv-broker --python 3.12
uv pip install --python .probe\venv-broker taskiq taskiq-aio-pika aio-pika
.probe\venv-broker\Scripts\python.exe .probe\smoke_taskiq_broker.py          # (c)
uv venv .probe\venv-aps4 --python 3.12
uv pip install --python .probe\venv-aps4 --prerelease=allow "apscheduler>=4"  # fails (d)
uv pip install --python .probe\venv-aps4 "apscheduler==4.0.0a6"
uv venv .probe\venv-aps3 --python 3.12
uv pip install --python .probe\venv-aps3 "apscheduler==3.11.3" sqlalchemy
.probe\venv-aps3\Scripts\python.exe .probe\smoke_apscheduler.py aps3         # (d)
.probe\venv-aps4\Scripts\python.exe .probe\smoke_apscheduler.py aps4         # (d)
```

---

## Resolved dependency baseline (Phase 0)

Date: 2026-10-02 · same workstation as the probes above (`uv 0.12.13`, CPython 3.12.14).
This section records what the **repository** actually pins, so later phases can distinguish a probe
finding from a locked fact. It is derived from the files that ship in the repo, not from a probe venv.

### Project files

- `pyproject.toml` (root): `requires-python = ">=3.12,<3.13"`, direct dependencies declared as
  major/minor compatible ranges, `[tool.ruff]` and `[tool.pyright]` (`strict`, `pythonVersion 3.12`).
  `pyproject.toml` declares `[[tool.uv.index]]` (`aliyun`, `default = true`), so the project — not
  only the machine — owns the index that produced the lock (`docs/development/tooling.md`).
- `.python-version`: `3.12`.
- `uv.lock`: authoritative exact versions. Note that uv records the registry that produced the
  resolution, so each package carries `source = { registry = "https://mirrors.aliyun.com/pypi/simple/" }`.
  The lock binds to that declared index: `uv sync --locked` passes with project configuration only
  (measured with `--no-config`, i.e. the machine-level `uv.toml` ignored), while forcing another
  index with `UV_DEFAULT_INDEX=https://pypi.org/simple` fails with
  `error: The lockfile at uv.lock needs to be updated, but --locked was provided.` (measured; this is
  uv's intended semantics, not a defect). Versions are unaffected — only the recorded registry
  differs — so a machine that must use another index has to re-lock (`uv lock`) and can expect the
  same version table.

```powershell
cd D:\YZB\RAG
uv lock                 # Resolved 140 packages in 561ms
uv sync --locked        # Checked 138 packages (no changes)
uv pip freeze --python .venv\Scripts\python.exe | Out-File -Encoding utf8 .probe\phase0-freeze.txt   # 138 lines
```

### Direct dependencies: declared range → locked version

| declared | locked |
|---|---|
| `fastapi>=0.142,<1` | `fastapi==0.142.2` |
| `uvicorn[standard]>=0.54,<1` | `uvicorn==0.54.0` |
| `pydantic>=2.13,<3` | `pydantic==2.13.5` |
| `pydantic-settings>=2.15,<3` | `pydantic-settings==2.15.0` |
| `sqlalchemy[asyncio]>=2.1,<3` | `sqlalchemy==2.1.1` |
| `asyncpg>=0.31,<1` | `asyncpg==0.31.0` |
| `psycopg[binary]>=3.3,<4` | `psycopg==3.3.6` |
| `alembic>=1.20,<2` | `alembic==1.20.0` |
| `taskiq>=0.13,<1` | `taskiq==0.13.0` |
| `taskiq-aio-pika>=0.6,<1` | `taskiq-aio-pika==0.6.1` |
| `aio-pika>=10.1,<11` | `aio-pika==10.1.0` |
| `structlog>=26.1,<27` | `structlog==26.1.0` |
| `argon2-cffi>=25.1,<26` | `argon2-cffi==25.1.0` |
| `boto3>=1.43,<2` | `boto3==1.43.106` |
| `redis>=8.1,<9` | `redis==8.1.0` |
| `qdrant-client>=1.19,<2` | `qdrant-client==1.19.1` |
| `langchain>=1.4,<2` | `langchain==1.4.3` |
| `langgraph>=1.2,<2` | `langgraph==1.2.12` |
| `langgraph-checkpoint-postgres>=3.1,<4` | `langgraph-checkpoint-postgres==3.1.2` |
| `langchain-openai>=1.6,<2` | `langchain-openai==1.6.7` |
| `lightrag-hku>=1.5,<2` | `lightrag-hku==1.5.7` |
| `langfuse>=4.16,<5` | `langfuse==4.16.0` |
| `httpx>=0.28,<1` | `httpx==0.28.1` |
| `python-multipart>=0.0.32,<1` | `python-multipart==0.0.32` |
| `apscheduler>=3.11,<4` | `apscheduler==3.11.3` |
| `tenacity>=9.1,<10` | `tenacity==9.1.4` |
| dev `ruff>=0.15` | `ruff==0.16.9` |
| dev `pyright>=1.1` | `pyright==1.1.414` |

Transitive packages the probe findings depend on, as locked:

| package | locked | role |
|---|---|---|
| `greenlet` | `3.5.6` | required by the `sqlalchemy[asyncio]` extra |
| `psycopg-binary` | `3.3.6` | the `psycopg[binary]` extra that makes `langgraph.checkpoint.postgres` importable |
| `psycopg-pool` | `3.3.3` | checkpoint connection pool |
| `langgraph-checkpoint` | `4.2.0` | pinned by `langgraph-checkpoint-postgres` |
| `taskiq-dependencies` | `1.5.7` | taskiq 0.13.0 runtime |
| `aiormq` / `pamqp` | `7.2.1` / `4.0.1` | aio-pika 10.1.0 wire layer |
| `tzlocal` | `5.4.4` | APScheduler 3.11.3 dependency |
| `nodeenv` | `1.11.0` | pulled by the `pyright` wheel |
| `starlette` | `1.7.0` / `httpx2==2.13.1`, `httpcore2==2.13.1` | FastAPI 0.142.2 stack |

### Difference against `.probe/resolution-freeze.txt`

```powershell
Compare-Object -ReferenceObject (Get-Content .probe\resolution-freeze.txt) `
               -DifferenceObject (Get-Content .probe\phase0-freeze.txt)
```

```
=> -e file:///D:/YZB/RAG
=> apscheduler==3.11.3
=> greenlet==3.5.6
=> nodeenv==1.11.0
=> psycopg-binary==3.3.6
=> pyright==1.1.414
=> ruff==0.16.9
=> taskiq-aio-pika==0.6.1
=> tzlocal==5.4.4
```

Only additions appear — there is **no `<` line, i.e. not a single package resolved to a different
version than the probe freeze**, so the project lock accepted no downgrade or conflict resolution.
The additions are exactly the three packages the probe said had to be declared explicitly
(`psycopg[binary]`, `taskiq-aio-pika`, `apscheduler==3.11.3`) plus their extras/dependencies and the
dev tools:

- `psycopg-binary==3.3.6` and `taskiq-aio-pika==0.6.1` were installed *after*
  `resolution-freeze.txt` was captured (see (a) note and (c)), which is why they are new here.
- `greenlet==3.5.6` comes from the `sqlalchemy[asyncio]` extra (`sqlalchemy` alone was installed in
  the probe venv, which is why the probe had to add greenlet manually for the live probes).
- `tzlocal==5.4.4` is an APScheduler 3.11.3 dependency; `nodeenv==1.11.0`, `ruff`, `pyright` are
  dev-only; `-e file:///D:/YZB/RAG` is the editable install of the `rag_platform` package itself.

### Runtime baseline verification (same session, real containers)

```powershell
uv run ruff check backend/src          # All checks passed!
uv run ruff format --check backend/src # 27 files already formatted
uv run pyright backend/src            # 0 errors, 0 warnings, 0 informations   (strict)
docker compose -f infra/compose.yaml config --quiet   # exit 0
./scripts/smoke.ps1                    # exit 0
```

`GET /health/ready` with every dependency up (HTTP 200):

```json
{"status":"ready","duration_ms":219,"dependencies":[{"name":"postgres","state":"healthy","latency_ms":219,"detail":null},{"name":"redis","state":"healthy","latency_ms":136,"detail":null},{"name":"qdrant","state":"healthy","latency_ms":132,"detail":null},{"name":"rabbitmq","state":"healthy","latency_ms":49,"detail":null},{"name":"rustfs","state":"healthy","latency_ms":44,"detail":null}]}
```

`GET /health/ready` after `docker compose -f infra/compose.yaml stop rabbitmq` (HTTP 503):

```json
{"status":"unavailable","duration_ms":2101,"dependencies":[{"name":"postgres","state":"healthy","latency_ms":106,"detail":null},{"name":"redis","state":"healthy","latency_ms":82,"detail":null},{"name":"qdrant","state":"healthy","latency_ms":45,"detail":null},{"name":"rabbitmq","state":"unhealthy","latency_ms":2059,"detail":"AMQPConnectionError: [WinError 1225] 远程计算机拒绝网络连接。"},{"name":"rustfs","state":"healthy","latency_ms":6,"detail":null}]}
```

Two operational facts worth keeping with this baseline:

1. `.venv\Scripts\python.exe` created by `uv` on Windows is a **launcher shim**; the server runs in
   a child interpreter (`os.getpid()` differs from the started PID), so process teardown must kill
   the tree (`taskkill /PID <pid> /T /F`), not just the launcher.
2. `Settings` sets `hide_input_in_errors=True`: a missing `RAG_*` variable must report the field
   names only, because the configuration sources include the local `.env` with provider keys.
3. A `uv.lock` generated against the Aliyun mirror is not portable under `--locked` to a machine
   with a different index (see the project-files note above); `uv lock` re-records the registry
   without changing any version.

