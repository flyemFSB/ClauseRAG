# 实证探针：真实依赖契约（Live dependency contracts）

日期：2026-10-02 · 环境：Windows PowerShell 7 / Docker 29.8.0 · cwd `D:\YZB\RAG`
本机镜像（只用这些，未 pull 任何镜像）：`postgres:18-alpine`、`qdrant/qdrant:v1.19.1`、
`redis:8-alpine`、`rabbitmq:4.3.6-management-alpine`、`rustfs/rustfs:1.0.0`。

全部结论来自本轮实际执行的命令。原始输出保存在 `.probe\live\out-*.txt` 和探针脚本
`.probe\live\*.py`（`.probe/` 已被 `.gitignore` 忽略，故关键输出在本文内联）。
探针容器统一前缀 `ragprobe-`，端口 `55xxx/56xxx/59xxx`；本轮结束时已 `docker rm -f` 全部删除，
`docker ps -a` 计数为 0，5 个镜像保持原样。

> **后续变更（ADR-0029 / ADR-0034）**：文中 LightRAG 相关的隔离验证随图谱通道一并删除（ADR-0029）；
> Qdrant 与 pg_trgm 亦已随 ADR-0034 废弃并统一迁移至 ParadeDB（pgvector HNSW 密集向量 + pg_search BM25 词项检索）。
> 本文保留为当时的底层依赖实测历史记录。

## 0. 探针环境

容器启动（确切命令）：

```powershell
docker run -d --name ragprobe-pg   -e POSTGRES_PASSWORD=probe -p 55432:5432 postgres:18-alpine
docker run -d --name ragprobe-qdrant -p 56333:6333 -p 56334:6334 qdrant/qdrant:v1.19.1
docker run -d --name ragprobe-redis  -p 56379:6379 redis:8-alpine
docker run -d --name ragprobe-rabbit -e RABBITMQ_DEFAULT_USER=probe -e RABBITMQ_DEFAULT_PASS=probe `
  -p 55672:5672 -p 55673:15672 rabbitmq:4.3.6-management-alpine
docker run -d --name ragprobe-rustfs -e RUSTFS_ACCESS_KEY=probeaccess -e RUSTFS_SECRET_KEY=probesecret `
  -p 59000:9000 -p 59001:9001 rustfs/rustfs:1.0.0
```

客户端环境：

```powershell
uv venv .probe\venv-live --python 3.12
uv pip install --python .probe\venv-live\Scripts\python.exe sqlalchemy asyncpg alembic `
  langgraph-checkpoint-postgres greenlet qdrant-client redis pika boto3 taskiq taskiq-aio-pika `
  "psycopg[binary]"
```

实测客户端版本：`sqlalchemy 2.1.1`、`asyncpg 0.31.0`、`alembic 1.20.0`、`greenlet 3.5.6`、
`langgraph-checkpoint 4.2.0`、`langgraph-checkpoint-postgres 3.1.2`、`psycopg 3.3.6`（+`psycopg-binary 3.3.6`）、
`qdrant-client 1.19.1`、`redis 8.1.0`、`pika 1.4.4`、`boto3 1.43.106`、
`taskiq 0.13.0`、`taskiq-aio-pika 0.6.1`、`aio-pika 10.1.0`、`aiormq 7.2.1`、CPython 3.12.14。

两个操作细节（会在后续开发里反复踩到）：

- `uv venv` 生成的虚拟环境**没有 pip**：`.probe\venv-live\Scripts\python.exe -m pip list` →
  `No module named pip`。装包必须用 `uv pip install --python <venv>\Scripts\python.exe`。
- PowerShell 控制台默认按 GBK 解码子进程 stdout，中文会变乱码。探针统一
  `[Console]::OutputEncoding=[System.Text.Encoding]::UTF8` + `PYTHONUTF8=1` + `python -u` + `Out-File -Encoding utf8`。

---

## 1. PostgreSQL 18.6（`postgres:18-alpine`）

### 1a. pg_trgm 是否内置；pg_trgm / vector 可用性

命令：`.probe\venv-live\Scripts\python.exe -u .probe\live\pg_ext.py`（脚本用 asyncpg 连
`postgresql://postgres:probe@127.0.0.1:55432/postgres`）

观测输出（裁剪）：

```
== server ==
  PostgreSQL 18.6 on x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit
  default_text_search_config: pg_catalog.english
  server_encoding: UTF8
== pg_available_extensions (filtered) ==
  {'name': 'btree_gin', 'default_version': '1.3', 'installed_version': None}
  {'name': 'btree_gist', 'default_version': '1.8', 'installed_version': None}
  {'name': 'fuzzystrmatch', 'default_version': '1.2', 'installed_version': None}
  {'name': 'pg_trgm', 'default_version': '1.6', 'installed_version': None}
  {'name': 'pgcrypto', 'default_version': '1.4', 'installed_version': None}
  {'name': 'unaccent', 'default_version': '1.1', 'installed_version': None}
  {'name': 'uuid-ossp', 'default_version': '1.1', 'installed_version': None}
  present of interest: ['btree_gin','btree_gist','fuzzystrmatch','pg_trgm','pgcrypto','unaccent','uuid-ossp']
  pg_trgm available: True
  vector available: False
== CREATE EXTENSION pg_trgm ==
  ok: pg_trgm created
== CREATE EXTENSION vector ==
  FAILED: FeatureNotSupportedError extension "vector" is not available
HINT:  The extension must first be installed on the system where PostgreSQL is running.
== pg_extension installed ==
  {'extname': 'pg_trgm', 'extversion': '1.6'}
  {'extname': 'plpgsql', 'extversion': '1.0'}
```

**判定**：`pg_trgm` 1.6 内置可用（contrib 已在官方 alpine 镜像内），`CREATE EXTENSION pg_trgm` 直接成功，
无需换镜像、无需装额外包。**`vector`（pgvector）在该镜像内不可用**，报文是
`extension "vector" is not available`；因此第一版向量检索不得依赖 pgvector，Qdrant 是唯一向量库
（与 ADR-0002 一致）。若将来需要 pgvector，必须换成 `pgvector/pgvector` 镜像——这是新的镜像依赖，
当前本机没有。

**未决项**：无（结论明确）。

### 1b. CJK 文本上的 pg_trgm：真实返回与局限（ADR-0003 证据）

建立 `child_chunks(text)` + GIN `gin_trgm_ops` 索引的 DDL：

```sql
create table child_chunks (
    id uuid primary key default gen_random_uuid(),
    document_version_id uuid not null,
    content text not null
);
create index ix_child_chunks_content_trgm on child_chunks using gin (content gin_trgm_ops);
```

#### 事实 1：CJK 会被切成 trigram，但以“哈希三元组”形式存储

```
show_trgm('知识库检索增强生成系统') n=12 -> {0x81c871,0x89c885,0xa9dbaf,0xbacb3d,0xc7aa4e,0xcda5b3,0xfe1fc6,0x0dd813,0x285e64,0x5f15d0,0x6a887a,0x7acf5b}
show_trgm('hello world')            n=12 -> {"  h","  w"," he"," wo",ell,hel,"ld ",llo,"lo ",orl,rld,wor}
```

整段连续 CJK 被当作一个“词”，n 个字符产生 n 个 trigram，非 ASCII trigram 以 `0x…` 哈希值显示。
**后续所有“中文得不到 trigram”的猜测都被证伪**：索引确实对中文生效（见事实 4）。

#### 事实 2：算子语义（从 `pg_operator`/`pg_proc` 读取 + 方向实证）

```
%    -> similarity_op(text,text)
<%   -> word_similarity_op(text,text)
%>   -> word_similarity_commutator_op(text,text)
<<%  -> strict_word_similarity_op(text,text)
%>>  -> strict_word_similarity_commutator_op(text,text)
阈值默认：pg_trgm.similarity_threshold=0.3 / word_similarity_threshold=0.6 / strict_word_similarity_threshold=0.5
```

方向实证（doc=`知识库检索增强生成系统`，query=`知识库检索`）：

```
similarity(doc,query)=0.38462      -> doc %    query = True   （similarity(doc,query) >= 0.3）
word_similarity(doc,query)=0.41667 -> doc <%   query = False  （word_similarity(doc,query) >= 0.6）
word_similarity(query,doc)=0.83333 -> doc %>   query = True   （word_similarity(query,doc) >= 0.6）
strict_word_similarity(query,doc)=0.38462 -> doc %>> query = False
```

**判定**：做“查询词出现在文档里”的关键词召回，正确算子是 **`content %> :query`**
（等价于 `word_similarity(:query, content) >= word_similarity_threshold`）。
`<%` 方向反了（是“文档落在查询里”），`%>>` 是 strict 版本，`%` 是整体相似度。

**踩坑**：`show pg_trgm.similarity_threshold` 在**本会话第一次调用 pg_trgm 函数之前会直接报错**
`unrecognized configuration parameter "pg_trgm.similarity_threshold"`（GUC 在库加载时才注册）。
健康检查/初始化代码若先读 GUC，必须先调一次 `select show_trgm('warmup')` 之类的函数。

#### 事实 3：CJK 的召回矩阵（真实返回）

doc=`知识库检索增强生成系统与父子块切分策略`（20 字），`like` 为 `content LIKE '%q%'`：

| query | like | similarity | `%`@0.3 | word_similarity(q,doc) | `%>`@0.6 |
|---|---|---|---|---|---|
| 知识 | 1 | 0.0952 | 0 | 0.6667 | **1** |
| 知识库 | 1 | 0.1429 | 0 | 0.7500 | **1** |
| 知识库检索 | 1 | 0.2381 | 0 | 0.8333 | **1** |
| 检索增强 | 1 | 0.0870 | 0 | 0.4000 | 0 |
| 库检 | 1 | **0.0000** | 0 | **0.0000** | 0 |
| 切分策略 | 1 | 0.1364 | 0 | 0.6000 | **1** |
| 父子块切分策略 | 1 | 0.2727 | 0 | 0.7500 | **1** |

英文对照（doc=`Retrieval augmented generation pipeline and child chunk splitting`）：

| query | similarity | `%`@0.3 | word_similarity(q,doc) | `%>`@0.6 |
|---|---|---|---|---|
| ret | 0.0469 | 0 | 0.7500 | **1** |
| retrieval | 0.1587 | 0 | 1.0000 | **1** |
| chunk | 0.0952 | 0 | 1.0000 | **1** |
| chunk splitting | 0.2540 | 0 | 1.0000 | **1** |

**判定**：默认阈值下 `similarity()`/`%` 对中文子串召回**基本失效**——`知识库检索`（真实子串）
只有 0.2381，低于 0.3，0 命中。要召回必须用 `%>`（或 LIKE）。

#### 事实 4：CJK 的真正致命局限——短词与“跨边界片段”得分 0

对 12 字连续 CJK 串 `知识库检索增强生成系统` 做 4 字滑窗，方向为召回算子方向
`word_similarity(q,doc)` + `doc %> q`（阈值 0.6）：

```
slice[0:4]='知识库检' word_similarity(q,doc)=0.8000 doc%>q=True  like=True
slice[1:5]='识库检索' word_similarity(q,doc)=0.4000 doc%>q=False like=True
slice[2:6]='库检索增' word_similarity(q,doc)=0.4000 doc%>q=False like=True
slice[3:7]='检索增强' word_similarity(q,doc)=0.4000 doc%>q=False like=True
slice[4:8]='索增强生' word_similarity(q,doc)=0.4000 doc%>q=False like=True
slice[5:9]='增强生成' word_similarity(q,doc)=0.4000 doc%>q=False like=True
slice[6:10]='强生成系' word_similarity(q,doc)=0.4000 doc%>q=False like=True
slice[7:11]='生成系统' word_similarity(q,doc)=0.6000 doc%>q=True  like=True
2/3 字探针：知识=0.6667(True) 知识库=0.7500(True) 库检=0.0000(False) 检索=0.0000(False) 系统=0.3333(False)
把 word_similarity_threshold 降到 0.3：上述全部 slice 均 doc%>q=True
```

**判定（ADR-0003 的核心证据）**：pg_trgm 对中文**只在查询与连续 CJK 串的边界（起止）对齐时有效**
（上表中只有起点切片 `知识库检`=0.8 与终点切片 `生成系统`=0.6 达阈）。
原因是它只在词的起止处生成带 padding 的 trigram：2 字中文查询（如 `检索`、`库检`）的 trigram
几乎全是 padding 组合，在串内部不存在，于是**真实子串得到 0.0000 分**；
4 字中段查询稳定停在 0.4，低于默认 0.6。阈值降到 0.3 可以全部命中，但此时
“命中”退化为 trigram 有交集，排序信号很弱。**`LIKE '%q%'` 语义正确（上表 like 全为 1），
且能被 GIN trgm 索引加速**，这才是中文关键词召回该用的算子。

#### 事实 5：阈值扫描（5 篇混合语料，真实命中 id）

```
content % probe（similarity）：thr=0.3 -> 仅 知识库检索->d1
                              thr=0.2/0.15 -> +向量检索->d2, 父子块->d3, retrieval->d4
                              thr=0.1 -> +检索增强->d1
                              thr=0.05 -> +RAG->d2（误召回）
content %> probe（word_similarity）：thr=0.6/0.5 -> 知识库检索->d1, 向量检索->d2, 父子块->d3, retrieval->d4
                              thr=0.4 -> +检索增强->d1
                              thr=0.3 -> +chunk->d5
                              thr=0.2 -> +RAG->d2,d4（误召回）
```

#### 事实 6：GIN trgm 索引对 CJK 真实可用

5000 行语料、`content %> :query` / `content LIKE '%q%'`（`set enable_seqscan=off` 强制索引）：

```
Bitmap Index Scan on ix_child_chunks_content_trgm  (Index Cond: (content %> '知识库'::text))
  rows=2500  Execution Time: 7.3 ms          ← %> 走索引
Bitmap Index Scan on ix_child_chunks_content_trgm  (Index Cond: (content ~~ '%死信%'::text))
  rows=5000 → Recheck 后 625  Execution Time: 1.6 ms   ← LIKE 走索引且带 recheck
```

但**规划器在 5000 行时仍选 Seq Scan**（`cost=0.00..138.50` 的 seqscan 对
`cost=0..1794` 的 bitmap；实测 Seq 17.7 ms vs 强制索引 4.3 ms）。trgm 索引的代价估算偏保守，
真实语料量级上需要实测/必要时用 `gin_trgm_ops` + 更好的统计信息或改索引策略。

**1b 综合判定**：

1. 关键词通道**不要**用 `content % :query`（默认 0.3）——中文召回会大面积丢失。
2. 若用 trigram 算子，唯一正确方向是 `content %> :query`，且必须显式下调
   `pg_trgm.word_similarity_threshold`（实证 0.3）；但 **2 字中文查询仍会 0 分**。
3. 建议 keyword 通道实现为 **`content LIKE '%'||:q||'%'`（GIN trgm 索引加速，语义精确）
   + 用 `similarity(content,:q)` / `word_similarity(:q,content)` 仅作打分排序**，不要用阈值算子做过滤。
4. 这条证据支持 ADR-0003 中“用最终语料评估，必要时转向应用侧分词的 `tsvector`/外部检索”的表述，
   且给出了明确的失败模式；纯 pg_trgm 无法胜任中文短词召回。

**未决项**：最终语料上的召回质量评估（ADR-0003 明确要求的步骤）尚未做；
`word_similarity_threshold` 的最终取值、是否引入应用侧分词后写 `tsvector`，需要真实语料决定。

### 1c. Alembic 异步迁移：必需配置项

工程目录 `.probe\live\alembicproj`：`alembic.ini` + `migrations\env.py` + `migrations\script.py.mako`
+ `migrations\versions\0001_probe.py`。迁移里包含 `create extension if not exists pg_trgm`、
`sa.Uuid` 主键、`postgresql_using="gin"` + `postgresql_ops={"content": "gin_trgm_ops"}` 的索引。

命令与观测（干净库 `probe_migrate`）：

```powershell
$env:PROBE_DB_URL="postgresql+asyncpg://postgres:probe@127.0.0.1:55432/probe_migrate"
.probe\venv-live\Scripts\python.exe -m alembic upgrade head
```

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_probe, Bootstrap schema for the async-alembic probe.
alembic current  -> 0001_probe (head)
alembic history  -> <base> -> 0001_probe (head)
psql \dt         -> alembic_version, child_chunks
version_num      -> 0001_probe
indexdef         -> CREATE INDEX ix_child_chunks_content_trgm ON public.child_chunks USING gin (content gin_trgm_ops)
```

**最小配置实验**：

- 只留 `[alembic] script_location = migrations`、去掉 `[loggers]/[handlers]/[formatters]` 全部日志段，
  env.py 保留标准模板的 `fileConfig(config.config_file_name)` → **失败**：
  `KeyError: 'formatters'`（`logging.config.fileConfig` 要求这些段存在）。
- 只留 `[alembic] script_location = migrations-min`，env.py **不调用 fileConfig**，URL 由 env.py 内部提供
  → `alembic upgrade head` **成功**（干净库 `probe_migrate3`，建出 `alembic_version` + `child_chunks`）。

**判定（必需项）**：

| 项 | 必需性 |
|---|---|
| `[alembic] script_location` | **必需**（否则找不到 env.py） |
| `[loggers]/[handlers]/[formatters]/[logger_*]/[handler_*]/[formatter_generic]` | 仅当 env.py 调用 `fileConfig()` 时必需；保留标准模板即必须保留这些段 |
| `sqlalchemy.url` | 可选：env.py 自行提供 URL 时可省略；用 `config.get_main_option("sqlalchemy.url")` 时必需 |
| async env.py 关键点 | `async_engine_from_config(..., poolclass=pool.NullPool)` + `async with connectable.connect()` + `await connection.run_sync(do_run_migrations)` + `await connectable.dispose()`；4 处缺一不可 |
| `prepend_sys_path = .` | 当迁移脚本 import 项目包时必需（本项目后续会需要） |
| `version_path_separator = os` | 多版本目录（如 LightRAG 独立版本树）时才需要 |

**未决项**：LightRAG 自管表与业务 Alembic 的边界（研究文档已定为“不由业务 Alembic 管理”），
本轮未验证在同一个库里共存的迁移顺序问题。

### 1d. LangGraph `AsyncPostgresSaver.setup()` 与真实建表

命令：`.probe\venv-live\Scripts\python.exe -u .probe\live\pg_langgraph.py`（库 `probe_lg`）

观测输出（裁剪）：

```
== versions ==
  langgraph-checkpoint==4.2.0 / langgraph-checkpoint-postgres==3.1.2 / psycopg==3.3.6 / psycopg-pool==3.3.3
  from_conn_string: (conn_string: str, *, pipeline: bool = False, serde: SerializerProtocol | None = None) -> AsyncIterator[AsyncPostgresSaver]
  setup: (self) -> None
  __init__: (self, conn: _ainternal.Conn, pipe: AsyncPipeline | None = None, serde: SerializerProtocol | None = None) -> None
  MIGRATIONS count: 10
== A) setup() on a plain (non-autocommit) connection ==
  constructed: AsyncPostgresSaver
  conn: AsyncConnection autocommit = True          ← 库自己把 autocommit 打开了
  setup() OK on non-autocommit connection
== B) setup() with explicit autocommit=True connection ==
  setup() OK with autocommit=True
== C) idempotency: run setup() twice ==
  setup() twice OK (idempotent)
== D) checkpoint round-trip ==
  aput -> {'configurable': {'thread_id':'probe-thread-1','checkpoint_ns':'','checkpoint_id':'00000000-...-aa'}}
  aget_tuple found: True / channel_values: {'state': 'hello-pg'} / metadata: {'step': 1, 'source': 'input'}
  alist ids: ['00000000-0000-0000-0000-0000000000aa']
```

`psql -d probe_lg -c "\dt"`：

```
checkpoint_blobs | checkpoint_migrations | checkpoint_writes | checkpoints
```

（另建 7 个索引：`checkpoints_pkey`、`checkpoints_thread_id_idx`、`checkpoint_blobs_pkey`、
`checkpoint_blobs_thread_id_idx`、`checkpoint_writes_pkey`、`checkpoint_writes_thread_id_idx`、
`checkpoint_migrations_pkey`；`checkpoints` 主键为 `(thread_id, checkpoint_ns, checkpoint_id)`。）

**两个必须记住的约束**：

1. **`psycopg` v3 需要 libpq**。只装 `langgraph-checkpoint-postgres`（它只依赖 `psycopg`）在本机会
   `ImportError: no pq wrapper available ... libpq library not found`；必须显式加 `psycopg[binary]`。
   即项目依赖里要同时写 `psycopg[binary]`，否则 Windows 开发机直接起不来。
2. **psycopg v3 异步在 Windows 默认 ProactorEventLoop 下不可用**。原始失败：

```
InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode.
Please use a compatible event loop, for instance by running
'asyncio.run(..., loop_factory=asyncio.SelectorEventLoop(selectors.SelectSelector()))'
```

   实测修法：`asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())`（脚本顶部、
   建 loop 之前）后 A~D 全部通过。Linux 容器内无此问题，但本机（Windows）跑后端/worker 必须处理。

**判定**：`AsyncPostgresSaver.setup()` 可用，**连接串无 autocommit 要求**（无 DSN 参数即可，
库内部把连接设为 autocommit，`from_conn_string` 返回的连接实测 `autocommit=True`）；
`setup()` 幂等，可每次启动调用。表名集合 = `checkpoints` / `checkpoint_writes` / `checkpoint_blobs`
/ `checkpoint_migrations`。

**未决项**：项目将同时存在两个 PG 驱动（业务用 asyncpg，checkpoint 用 psycopg）；
是否统一、以及 checkpoint 连接池（`AsyncPostgresSaver` + `psycopg_pool`）在生产配置中的形态，需要决策。

---

## 2. Qdrant v1.19.1

命令：`.probe\venv-live\Scripts\python.exe -u .probe\live\qdrant_probe.py`（server info 实测
`version='1.19.1'`，client `qdrant-client 1.19.1`）

实际 API 形状（截取关键签名）：

```
query_points(collection_name, query=None, using=None, prefetch=None, query_filter=None,
             search_params=None, limit=10, offset=None, with_payload=True, with_vectors=False,
             score_threshold=None, lookup_from=None, consistency=None, shard_key_selector=None,
             timeout=None) -> QueryResponse
upsert(collection_name, points, wait=True, ordering=None, ...) -> UpdateResult
create_payload_index(collection_name, field_name, field_schema=None, field_type=None, wait=True, ...) -> UpdateResult
create_collection(collection_name, vectors_config=None, sparse_vectors_config=None, ...) -> bool
scroll(collection_name, scroll_filter=None, limit=10, order_by=None, offset=None, ...) -> tuple[list[Record], PointId|None]
client.search  -> **MISSING（1.19.1 已移除）**
```

观测输出（裁剪）：

```
collections: collections=[]
create_payload_index(document_version_id/knowledge_base_id) -> completed
business config: {'dense': VectorParams(size=8, distance=<Distance.COSINE>)}
upsert -> operation_id=5 status=<UpdateStatus.COMPLETED: 'completed'>; count = 5
QueryResponse type: QueryResponse ; runtime fields: ['points']
  id=3 score=1.000000 version=5 payload={'content':'biz-child-chunk-3','document_version_id':'biz-dv-1','knowledge_base_id':'biz-kb-1'}
       vector={'dense':[0.315877, 0.3264062, ...]}      ← cosine 下服务器返回归一化后的向量
legacy client.search() -> AttributeError: 'QdrantClient' object has no attribute 'search'
isolation: business payloads=[biz-*], lightrag payloads=[lrag-*]（两库点 id 相同 1..5，互不可见）
           business collection filtered by 'lrag-kb-1' -> []
scroll: first page ids [1,2] next_offset 3 ; second page ids [3,4] next_offset 5   ← offset 为排他游标
delete point -> count 4
using 不存在的向量名 -> 400 UnexpectedResponse {"status":{"error":"Wrong input: Not existing vector name error: does_not_exist"}}
不存在的 collection -> 404 UnexpectedResponse {"status":{"error":"Not found: Collection `...` doesn't exist!"}}
```

**两个类型/API 陷阱**（会直接让 strict Pyright 报错或运行时 AttributeError）：

1. `from qdrant_client import models` 得到的 `models.QueryResponse` 是
   **`qdrant_client.fastembed_common.QueryResponse`**（字段 `id/embedding/sparse_embedding/metadata/document/score`），
   **不是**检索返回类型。真正的返回模型是 `qdrant_client.http.models.models.QueryResponse`（字段 `['points']`）。
   注解必须用后者。
2. 1.19.1 没有 `client.search()`，统一用 `query_points(...)`；命名向量用 `using="dense"`，
   而不是旧版的 `query_vector=models.NamedVector(...)`。

**判定**：命名向量 + payload 索引 + 批量 upsert + 过滤检索 + 集合隔离全部通过；
两个 collection（business / lightrag）即使点 id 相同也完全互不可见，用错 `knowledge_base_id`
过滤返回空集——ADR-0002 的物理隔离在客户端层面可验证。

**未决项**：`vectors_config` 的维度/距离需按 BGE-M3（1024 维，cosine 待实测）确定 → **已确定**
（Phase 3：`BAAI/bge-m3` 实测输出 1024 维，业务集合以 `size=1024, distance=Cosine` 创建，见 ADR-0011/0019 与
`scripts/probes/indexing.ps1` 第 2 项从 client 读回的输出）。
生产是否开启 `on_disk` / quantization / HNSW 参数未定。`models.QueryResponse` 的别名陷阱
建议在代码规范里写明 → 已在 `docs/research/official-docs-qdrant.md` §6 记录，业务索引适配器用
`AsyncQdrantClient` 且不暴露检索 API（Phase 4 才需要 `QueryResponse`）。

---

## 3. Redis（`redis:8-alpine`）与 redis-py 8.1.0

命令：`.probe\venv-live\Scripts\python.exe -u .probe\live\redis_probe.py`（`redis://127.0.0.1:56379/0`）

```
redis-py: 8.1.0
PING: True ; server_version: 8.10.2 ; cluster_enabled: 0
SET: True / GET: v1 / TYPE: string / SET nx=True (已存在) -> None / INCR: 1 2
EXPIRE 10 -> True / TTL: 10 / PTTL > 0 / PERSIST: True TTL now: -1
SET px=50 -> 120ms 后 GET -> None（过期生效）
SET NX PX 5000 #1 -> True ; #2 -> None ; GET owner -> owner-a ; setnx(legacy) -> False ; TTL lock -> 5
pipeline(transaction=True).execute() -> [True, 1, 'a']
pipeline(transaction=False).execute() -> [True, True, True]
hset mapping -> 2 ; hgetall -> {'stage':'chunking','attempt':'0'} ; hincrby -> 1
scan_iter(match='probe:*') -> ['probe:b0','probe:b1','probe:b2','probe:counter','probe:h','probe:key','probe:p1','probe:p2']
Lua 释放锁：错误 owner -> 0 ; 正确 owner -> 1 ; key exists -> 0
blpop/xread/xadd 存在：True/True/True
清理：delete 8 个 key，remaining []
```

**判定**：基础串/过期/`SET NX PX` 锁/pipeline（含事务与批处理）/hash/scan/Lua 原子释放全部符合预期；
redis-py 8.1.0 对 redis 8.10.2 兼容无告警。连接参数里出现
`maint_notifications_config=MaintNotificationsConfig(enabled=auto, ...)`（redis-py 8 新增的
维护通知自动重连逻辑），需注意长连接行为。

按 ADR-0004，Redis 不承担业务队列职责；本轮只验证了缓存/锁能力。

**未决项**：是否需要 Redis 做结果缓存、幂等键或限流，属产品决策；本轮不涉及。

---

## 4. RabbitMQ 4.3.6 与 Taskiq

### 4a. pika 层面的消息契约

命令：`.probe\venv-live\Scripts\python.exe -u .probe\live\rabbit_pika_probe.py`

```
pika: 1.4.4 ; server_properties.version: 4.3.6 ; platform Erlang/OTP 27.3.4.18
capabilities: {"publisher_confirms":true,"basic.nack":true,"consumer_cancel_notify":true,"connection.blocked":true,...}
declare: durable direct exchange probe.direct + durable queue probe.q(x-dead-letter-exchange=probe.dlx)
         + fanout probe.dlx + durable probe.dlq
confirm_delivery 接受；basic_publish(mandatory=True) 可路由 -> None
basic_publish(mandatory=True) 不可路由 -> UnroutableError（len(messages)=1）
手动 ack：basic_get(auto_ack=False) -> ack，队列剩余 0
DLQ-A：nack(requeue=False) -> probe.dlq 收到
   x-death: [{"count":1,"reason":"rejected","queue":"probe.q","exchange":"probe.direct","routing-keys":["probe.key"],...}]
DLQ-B：x-message-ttl=700 -> 1.2s 后 probe.ttlq count=0，消息出现在 probe.dlq
   x-death: [{"count":1,"reason":"expired","queue":"probe.ttlq","exchange":"","routing-keys":["probe.ttlq"],...}]
DLQ-C：basic_reject(requeue=False) -> probe.dlq 收到
quorum 队列：x-queue-type=quorum 声明/收发成功
管理 HTTP API：/api/overview -> 4.3.6 ; /api/queues /api/nodes /api/definitions 均 200
```

**关键发现（会静默丢消息）**：`x-dead-letter-routing-key` 指向**不存在**的目标队列时，
RabbitMQ 4.3.6 **不会自动建队列，消息直接消失**（实测 dead-letter 后 `/api/queues` 里
没有 `probe.missing.dlq`，计数也无处可查）；目标队列已存在时正常投递。

**判定**：durable 队列/交换机、publisher confirm、mandatory 不可路由错误、
手动 ack、DLQ（rejected / expired / rejected-by-reject 三种 `x-death.reason`）、
quorum 队列、管理 HTTP API 全部通过。**死信目标队列必须由部署侧显式声明**。

### 4b. Taskiq 的 RabbitMQ broker 依赖哪个包

命令：`.probe\venv-live\Scripts\python.exe -u .probe\live\rabbit_taskiq_probe.py`、
`rabbit_taskiq_dlq.py`、`rabbit_taskiq_dlq2.py`

```
taskiq==0.13.0 ; taskiq-aio-pika==0.6.1 ; aio-pika==10.1.0 ; aiormq==7.2.1 ; pamqp==4.0.1
taskiq 核心 broker（taskiq.brokers）: ['inmemory_broker','shared_broker','zmq_broker']   ← 没有 RabbitMQ
taskiq 顶层 Broker 名: ['AsyncBroker','BrokerMessage','InMemoryBroker','ZeroMQBroker']   ← 没有 RabbitMQ
taskiq_aio_pika.__all__: ['AioPikaBroker','Exchange','Queue','QueueType']
AioPikaBroker 位置: taskiq_aio_pika.broker.AioPikaBroker
```

**判定：RabbitMQ broker 来自独立包 `taskiq-aio-pika`（实测 0.6.1），taskiq 核心不含 RabbitMQ broker。**
（`aio-pika 10.1.0` / `aiormq 7.2.1` 是被它带进来的传输实现。）

构造签名差异（`AioPikaBroker` vs `InMemoryBroker`，实测 `inspect.signature`）：

```
AioPikaBroker.__init__(self, url=None, result_backend=None, task_id_generator=None, qos=10, loop=None,
    exchange=None, task_queues=None, dead_letter_queue=None, delay_queue=None,
    delayed_message_exchange_plugin=False, delayed_message_exchange=None,
    label_for_routing='queue_name', label_for_priority='priority', **connection_kwargs)
InMemoryBroker.__init__(self, sync_tasks_pool_size=4, max_stored_results=100, cast_types=True,
    max_async_tasks=30, max_async_tasks_jitter=0, propagate_exceptions=True, await_inplace=False)
只在 AioPikaBroker: [connection_kwargs, dead_letter_queue, delay_queue, delayed_message_exchange,
                     delayed_message_exchange_plugin, exchange, label_for_priority, label_for_routing,
                     loop, qos, result_backend, task_id_generator, task_queues, url]
只在 InMemoryBroker: [await_inplace, cast_types, max_async_tasks, max_async_tasks_jitter,
                      max_stored_results, propagate_exceptions, sync_tasks_pool_size]
共同参数: []                ← 两个构造签名没有任何共同显式参数
共同点: 都继承 taskiq.AsyncBroker（MRO: [X, AsyncBroker, ABC, object]），都支持 with_result_backend/
        with_middlewares/with_serializer
```

即：只有 `url` / `result_backend` / `task_id_generator` 这一类在两者间“概念上”对应，
`InMemoryBroker` 的并发池参数在 RabbitMQ broker 上完全不存在（由 `qos` 与 worker 并发替代），
因此**测试用内存 broker 与生产 broker 不能靠同一组构造参数构造**。

真实连通性与拓扑（`AioPikaBroker("amqp://probe:probe@127.0.0.1:55672//")`）：

```
startup() OK
 read_conn: NoneType | write_conn: RobustConnection | read_channel: NoneType | write_channel: RobustChannel
queue 'taskiq' 存在，durable=True，arguments:
 {'x-dead-letter-exchange': '', 'x-dead-letter-routing-key': 'taskiq.dead_letter', 'x-queue-type': 'quorum'}
非 amq.* 交换机: ['', 'taskiq']
queue 'taskiq' 的 binding: ({'source':'', 'routing_key':'taskiq'}, {'source':'taskiq', 'routing_key':'taskiq'})
kiq() -> AsyncTaskiqTask task_id=a705a4de771b4960b10c92d500c17c30 ; 队列 message_count 变为 1
消息线格式: routing_key='taskiq', exchange='taskiq'
  headers={'probe_label':'yes','task_id':...,'task_name':'ragprobe.task','x-acquired-count':1,'x-delivery-count':1}
  body={"task_id":...,"task_name":"ragprobe.task","labels":{"probe_label":"yes"},"labels_types":{"probe_label":3},"args":[41],"kwargs":{}}
启动即自动声明死信队列 taskiq.dead_letter（源码 broker.py:116 `startup()` → :135 `_declare_queues()`
→ :245 `_declare_dead_letter_queue()`；默认值来自 :95 `dead_letter_queue or Queue(name="taskiq.dead_letter")`，
task 队列带 x-dead-letter-exchange=""/x-dead-letter-routing-key="taskiq.dead_letter"）
```

**判定（对 ADR-0004 的意义）**：Taskiq 侧开箱就有 durable **quorum** 队列 + 死信队列
（默认名 `taskiq` / `taskiq.dead_letter`，死信走默认交换机 + routing key `taskiq.dead_letter`）；
`AioPikaBroker(...).startup()` 单独一次调用就会把 `taskiq.dead_letter` 建出来（源码路径见上）。
配合 4a 的结论“死信目标队列必须显式存在”，部署期要保证 `taskiq.dead_letter` 被声明；
由于 Taskiq 自己声明的名字与类型固定，**业务侧不能用 classic 类型重复声明同名队列**
（实测会 `PRECONDITION_FAILED - inequivalent arg 'x-queue-type' ... received 'classic' but current is 'quorum'`）。

**未决项**：

1. 任务队列名、是否保留 quorum 默认、`qos` 取值、是否启用 `delay_queue` /
   `delayed_message_exchange_plugin`（需额外插件）——部署决策，未定。
2. `AioPikaBroker` 的 `label_for_routing='queue_name'` 机制与项目“按知识库/阶段分流”的需求
   如何映射，未定。
3. Windows 本机跑 aio-pika 同样需要 selector event loop（本轮脚本显式设置），
   容器内无此问题；生产 worker 的运行环境需确认。

---

## 5. RustFS 1.0.0

### 5a. 镜像 env 契约、凭证与端口契约

```powershell
docker image inspect rustfs/rustfs:1.0.0 --format '{{json .Config}}'
docker run --rm rustfs/rustfs:1.0.0 --help
```

```
Config.Env: RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS=*, RUSTFS_VOLUMES=/data,
            RUSTFS_OBS_LOGGER_LEVEL=warn, RUSTFS_OBS_LOG_DIRECTORY=/logs, RUSTFS_OBS_ENVIRONMENT=production
Entrypoint: ["/entrypoint.sh"]  Cmd: ["rustfs"]  User: rustfs  ExposedPorts: 9000/tcp, 9001/tcp  Volume: /data
--help WARNING: RUSTFS_ACCESS_KEY or RUSTFS_ACCESS_KEY_FILE is not set; ... (or RUSTFS_ROOT_USER or MINIO_ROOT_USER)
                RUSTFS_SECRET_KEY or RUSTFS_SECRET_KEY_FILE is not set; ... (or RUSTFS_ROOT_PASSWORD or MINIO_ROOT_PASSWORD)
                rustfs falls back to its built-in default credential.
--help 子命令: server(默认) / info / tls / diagnose / inspect / connect
```

凭证优先级（实证）：`RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY` 有效；
不设任何凭证时**内置默认凭证是 `rustfsadmin` / `rustfsadmin`**
（对未设凭证的第二个容器逐一试：`rustfsadmin/rustfsadmin -> OK`，
`minioadmin/minioadmin -> InvalidAccessKeyId`，`''/'' -> UnauthorizedAccess`）。

端口契约（实证）：

```
http://127.0.0.1:59000/  -> 403 application/xml  <Error><Code>AccessDenied</Code>  ← S3 API
http://127.0.0.1:59000/health            -> 200 {"status":"ok","service":"rustfs-endpoint","version":"1.0.0"}
http://127.0.0.1:59000/minio/health/live -> 200 同上（MinIO 兼容健康检查）
http://127.0.0.1:59001/  -> 200 text/html（34 510 字节控制台页面）← Console
http://127.0.0.1:59001/health -> 200 同上
```

**判定**：9000 = S3 API，9001 = 控制台；`/health`、`/minio/health/live` 可用于 Compose healthcheck
（返回 JSON，含 `version`）。**必须显式设置 `RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY`**，
否则等于公开的 `rustfsadmin/rustfsadmin`。

### 5b. boto3 端到端（endpoint_url=http://127.0.0.1:59000，path-style，s3v4）

命令：`.probe\venv-live\Scripts\python.exe -u .probe\live\rustfs_probe.py`

```
boto3 1.43.106 / botocore 1.43.106
create_bucket -> created ragprobe-documents ; head_bucket -> 200
put_object -> ETag "e5c4b223617acdff7619dfb9460251b7" HTTP 200
head_object -> ContentLength 23, ContentType text/markdown, 同 ETag
get_object -> b'RAG \xe6\x8e\xa2\xe9\x92\x88\xe5\x86\x85\xe5\xae\xb9 hello\n'   ← UTF-8 中文原样
get_object Range=bytes=0-8 -> 206, ContentRange "bytes 0-8/23", ContentLength 9
presigned GET -> URL(含 X-Amz-*) 实际抓取 200 'RAG 探针内容 hello\n'
                 同一个 presigned 方案对不存在 key -> 404
multipart 6MB: create_multipart_upload -> UploadId; part1 5242880B, part2 1048576B;
               complete -> ETag "15f26ae56c6762a8a1a6df5680243692-2"; head ContentLength 6291456;
               下载字节 6291456，内容完全一致 True
list_objects_v2 prefix=''/'docs/' -> KeyCount=2 keys=['docs/big.bin','docs/child.md']（字典序）
list_objects (v1) 同样可用；MaxKeys=1 -> IsTruncated=True
delete_object -> 204，之后 list 只剩 docs/child.md；head 已删 key -> NoSuchKey 404
list_object_versions -> Versions 长度 1（未显式开启版本控制时也有版本信息）
delete_bucket 成功，list_buckets -> []
```

**判定：本项全部通过**（create_bucket / put_object / head_object / get_object / Range /
presigned GET 真实抓取 / multipart 6MB / list_objects_v2 / delete_object）。
端点 URL `http://127.0.0.1:59000` + path-style + `signature_version="s3v4"` 是已验证可用组合。

**未决项**：

1. `list_object_versions` 在未开启版本控制时也返回版本条目，是否符合“文档版本=对象版本”的
   设计意图需确认；若需要真正的版本控制语义，需验证 `put_bucket_versioning` 的返回与行为。
2. 控制台（9001）是否需要独立的管理凭证、以及 `RUSTFS_VOLUMES` 多盘/多节点形态，本轮未验证；
   如需排查，确切命令：`docker run --rm rustfs/rustfs:1.0.0 info`。
3. 大文件（本例 6 MB 双分片）之外的并发分片/断点续传策略未验证。

---

## 6. 镜像可拉取性（只做 manifest 检查，未 pull）

命令与真实错误：

```powershell
docker manifest inspect clickhouse/clickhouse-server:latest
docker manifest inspect langfuse/langfuse:latest
docker manifest inspect langfuse/langfuse-worker:latest
```

```
clickhouse/clickhouse-server:latest -> exit=1 failed to configure transport: error pinging v2 registry:
    Get "https://registry-1.docker.io/v2/": context deadline exceeded
langfuse/langfuse:latest            -> exit=1 ... net/http: request canceled while waiting for connection
    (Client.Timeout exceeded while awaiting headers)
langfuse/langfuse-worker:latest     -> exit=1 ... context deadline exceeded
rustfs/rustfs:1.0.0(本机已有镜像)   -> exit=1 同样超时（证明该命令始终走远端，不用本地镜像）
```

原因定位（确切命令与输出）：

```
docker info --format "{{json .RegistryConfig}}"
 -> Mirrors:["https://docker.mdaocloud.io/"]        ← 本机已配置的镜像加速器
https://registry-1.docker.io/v2/         -> ERR 15s 超时
https://docker.mdaocloud.io/v2/          -> ERR 不知道这样的主机（DNS 不存在）← 已配置的加速器是死链
Resolve-DnsName registry-1.docker.io     -> AAAA 2a03:2880:f10a:83:face:b00c:0:25de / A 108.160.163.117   ← 被污染的解析
Resolve-DnsName auth.docker.io           -> AAAA 2a03:2880:f12d:83:face:b00c:0:25de / A 31.13.96.195
https://mirrors.aliyun.com/pypi/simple/  -> 200（外网可用，说明不是“完全断网”）
https://mirror.gcr.io/v2/                -> ERR 超时
```

可达性探测结果（`/v2/` 返回 401 表示在说 Registry V2 协议、需要 token，属正常；仅此即视为可用候选）：

```
https://docker.m.daocloud.io/v2/  -> 401      https://docker.1ms.run/v2/     -> 401
https://docker.xuanyuan.me/v2/    -> 401      https://hub.rat.dev/v2/        -> 401
https://docker.nju.edu.cn/v2/     -> 403      https://quay.io/v2/ -> 401   https://ghcr.io/v2/ -> 401
https://docker.mirrors.sjtug.sjtu.edu.cn/v2/ -> ERR SSL
```

**不改任何全局配置**，用“镜像域名 + 原仓库路径”直接查 manifest（只取 manifest，不下载层），
三个镜像全部解析成功：

```powershell
docker manifest inspect docker.m.daocloud.io/clickhouse/clickhouse-server:latest
docker manifest inspect docker.1ms.run/clickhouse/clickhouse-server:latest
docker manifest inspect docker.m.daocloud.io/langfuse/langfuse:latest
docker manifest inspect docker.1ms.run/langfuse/langfuse:latest
docker manifest inspect docker.m.daocloud.io/langfuse/langfuse-worker:latest
docker manifest inspect docker.1ms.run/langfuse/langfuse-worker:latest
```

```
OK docker.m.daocloud.io/clickhouse/clickhouse-server:latest mediaType=application/vnd.oci.image.index.v1+json
   plats=linux/amd64,linux/arm64,unknown/unknown,unknown/unknown
OK docker.1ms.run/clickhouse/clickhouse-server:latest      同上
OK docker.m.daocloud.io/langfuse/langfuse:latest           mediaType=application/vnd.docker.distribution.manifest.list.v2+json
   plats=linux/amd64,linux/arm64
OK docker.1ms.run/langfuse/langfuse:latest                 同上
OK docker.m.daocloud.io/langfuse/langfuse-worker:latest    同上
OK docker.1ms.run/langfuse/langfuse-worker:latest          同上
```

**判定**：三个 Phase 5 镜像**在 Docker Hub 上存在且架构满足 linux/amd64**；
当前**不能**通过 `docker pull clickhouse/clickhouse-server:latest` 这类裸名拉取，原因不是镜像不存在，
而是本机 daemon 的 accelerator（`https://docker.mdaocloud.io/`）已失效 + `registry-1.docker.io` DNS 被污染。

**未决项（需要用户/parent 决策，涉及全局配置，本轮未改动）**：

1. 更换 daemon 的 registry mirror 为可达加速器（属全局配置，需授权）。示例（未执行）：
   `docker.m.daocloud.io` / `docker.1ms.run` 等，写入 Docker Desktop 的
   `Settings → Docker Engine` 的 `registry-mirrors` 后 `docker pull <image>`。
2. 或者不改配置，直接以镜像名拉取并 retag（未执行，供参考）：
   `docker pull docker.m.daocloud.io/clickhouse/clickhouse-server:latest`
   `docker tag docker.m.daocloud.io/clickhouse/clickhouse-server:latest clickhouse/clickhouse-server:latest`
3. `clickhouse/clickhouse-server:latest` 的 index 里含两个 `unknown/unknown` 平台条目
   （attestation/manifest 附件），不影响 amd64 拉取；若用 `--platform linux/amd64` 拉取可规避。
4. 三个镜像的**层大小与实际拉取耗时**未测（本轮按要求未 pull）。

---

## 7. 汇总

| 依赖 | 结论 | 关键证据 |
|---|---|---|
| PostgreSQL 18.6 | 通过。pg_trgm 1.6 内置可用；**pgvector 不可用** | `pg_available_extensions` + `CREATE EXTENSION vector` 失败 |
| PostgreSQL pg_trgm 中文 | 可用但**局限严重**；`%`@0.3 基本失效，短/中段 CJK 查询得 0.0 | 矩阵 + slice 实验 + 阈值扫描 + GIN 可被 LIKE/`%>` 使用 |
| Alembic async | 通过。最小必需 = `script_location` + 无 `fileConfig`；含日志段则必须齐全 | 两次对照实验 |
| LangGraph AsyncPostgresSaver | 通过。setup 幂等；**无 autocommit DSN 要求**；需 `psycopg[binary]` + Windows selector loop | 4 张表 + round-trip |
| Qdrant v1.19.1 | 通过。命名向量/索引/过滤/隔离全通；`search()` 已移除；`models.QueryResponse` 是别名陷阱 | 实测返回结构 |
| Redis 8.10.2 / redis-py 8.1.0 | 通过。锁/过期/pipeline/Lua 全通 | 冒烟输出 |
| RabbitMQ 4.3.6 | 通过。DLQ 三种 reason/quorum/confirm/管理 API 全通；**死信目标不存在即静默丢消息** | x-death + 不存在队列对照 |
| Taskiq | RabbitMQ broker = **`taskiq-aio-pika` 0.6.1**（taskiq 核心无 RabbitMQ）；两者构造签名无共同显式参数 | 签名对比 + 真实 startup/kiq |
| RustFS 1.0.0 | 通过全部 boto3 项；**必须显式设凭证**（否则默认 `rustfsadmin/rustfsadmin`）；9000=S3、9001=Console | 端到端输出 |
| Phase 5 三镜像 | 镜像存在且支持 amd64；当前裸名拉不动（加速器死链 + registry DNS 污染） | manifest 直连失败 + 镜像域名绕行成功 |

清理确认：`docker rm -f ragprobe-pg ragprobe-qdrant ragprobe-redis ragprobe-rabbit ragprobe-rustfs`
（含中途的 `ragprobe-rustfs2` 和二次启动的 `ragprobe-pg`），`docker ps -a` 计数 0；
本机 5 个镜像未被修改，未 pull 任何镜像。
