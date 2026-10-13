# ParadeDB + pgvector 替代 Qdrant：ClauseRAG 实施评估

> 状态：实施设计与发布检查清单，尚未执行数据库迁移或性能验收。
>
> 调研日期：2026-10-12。本版依据用户选择，取代此前“只迁移 Keyword、保留 Qdrant”的建议。目标是 PostgreSQL/ParadeDB 统一承载业务事实、pgvector Dense 和 pg_search BM25，最终退役 Qdrant；不是增加长期向量双写。

## 1. 决策与技术边界

**采用 ParadeDB 镜像中的 pgvector 原生 `vector(1024)` + HNSW cosine 索引替代 Qdrant；采用 `pg_search` 替代 `pg_trgm` 关键词召回；保留应用层双通道、RRF、BGE reranker、Parent-Child hydration 和 citation gate。**

必须区分三个概念：

| 能力 | 实现 | 本次选择 |
|---|---|---|
| PostgreSQL 中的向量类型及 ANN | pgvector 的 `vector`、HNSW/IVFFlat | 使用原生 HNSW，作为 Dense adapter |
| 全文检索 | ParadeDB `pg_search` 的 BM25 | 使用，作为 Keyword adapter |
| ParadeDB 自身的向量/混合索引 | 在 ParadeDB index 内建立向量索引，使用 pgvector 类型但不使用其 HNSW/IVF | 不使用；官方标记为 beta |

ParadeDB 自身的向量能力从 `0.25.0` 起为 beta，并不意味着 pgvector 原生 HNSW 也是该 beta 功能。[S3] 两路数据位于同一个 PostgreSQL 集群，也不要求把 RRF 移入 SQL 或取消现有 reranker。

```text
API / Agent / Worker / CLI
  -> existing application ports
      -> pgvector Dense adapter -> child_chunk_embeddings -> HNSW cosine
      -> pg_search Keyword adapter -> child_chunks -> BM25
  -> application RRF (k=60) -> BGE reranker
  -> authoritative chunk hydration -> evidence gate -> citation validation

PostgreSQL/ParadeDB = sole relational and vector storage after cutover
RabbitMQ = sole business queue; object storage = authoritative document artifacts
Qdrant = migration source / bounded rollback artifact, then retired
```

这减少一个独立服务、HTTP 向量写入和跨 PostgreSQL/Qdrant 的同步边界，但把 ANN、BM25、业务事务、摄取和 checkpoint 的 CPU、内存、磁盘及故障集中到数据库。**运维简化不等于性能提高，也不等于全链路自动成为单一事务。** 数据库整体故障会同时影响 Dense、Keyword 和 hydration，无法再依靠另一数据库完成检索。[S5][S9]

本次只形成实施文档，不修改业务代码、镜像、数据库或 Qdrant 数据。实施前必须将存储决策归档至 ADR，并同步现有设计契约中对 Qdrant Collection 的要求；本评估不表示仓库已经完成架构切换。

## 2. 官方版本与证据基线

| 项目 | 本次核实 | 发布要求 |
|---|---|---|
| ParadeDB release | GitHub API 最新非预发布为 `v0.26.1`，发布于 `2026-10-08T22:34:53Z` | 候选版本，不代表已完成运行时验收 |
| 该 tag 的 PG18 Dockerfile | `FROM postgres:18-trixie`；安装 `postgresql-18-pgvector=0.8.6-1.pgdg13+1` | 使用真实存在的 PG18 镜像 tag 并固定 digest，不推测 tag 后缀 |
| `pg_search` 依赖 | tag 内 control 文件 `requires = 'vector'`；官方要求先安装 pgvector | 迁移角色显式创建 `vector` 和 `pg_search` |
| pgvector 上游 | 官方 tags / README 当前到 `v0.8.7` | 不把上游最新版本当成 ParadeDB 镜像实际版本 |
| 现有部署 | Compose 使用 `postgres:18-alpine`、Qdrant `v1.19.1` | 保持 PG major 为 18；Alpine -> Debian 不能原地盲换数据卷 |

版本信息来自 release API、固定 tag Dockerfile/control、pgvector 官方 README/tags。[S1][S2][S4] `0.8.6` 满足 iterative scan 的 `>=0.8.0` 要求，但上线前仍需检查该版本之后的修复与目标工作负载是否相关。

**在线 ParadeDB 文档可能领先于固定 release。** 当前文档使用 `USING paradedb`、`pdb.score(column)` 和 `|||`/`&&&` match 运算符，并声明 `key_field` 已 deprecated/ignored；不得复制旧稿的 `USING bm25`、`paradedb.score(child_chunks)`、假想 `id` 列和含 `WHERE ...` 的伪迁移。[S6][S7][S8] 下文 SQL 都是设计形状，必须在锁定镜像上验证后再写 Alembic migration。

发布工件应记录：镜像仓库/tag/digest、CPU 架构、PostgreSQL 完整版本、`pg_search`/`vector` 的 `extversion`、Alembic revision、tokenizer、embedding 模型和维度。镜像内有文件不等于目标数据库已创建扩展。

```sql
SELECT version();
SELECT extname, extversion FROM pg_extension
WHERE extname IN ('vector', 'pg_search');
SELECT name, default_version, installed_version
FROM pg_available_extensions WHERE name IN ('vector', 'pg_search');
```

## 3. 仓库真实改造边界

当前路径，而非理想化接口：

| 文件/边界 | 当前行为 | 实施工作 |
|---|---|---|
| `backend/src/application/shared/vectors.py` | `VectorIndex` 定义 ensure/upsert/search/count/delete/close | 保留存储无关能力；修正 Collection 术语，按并发写入门控需要传递 attempt fence |
| `backend/src/infrastructure/retrieval/dense_channel.py` | embedding 后调用 `search_dense()` | 保留；改文档描述，不复制检索编排 |
| `backend/src/infrastructure/retrieval/qdrant_index.py` | Qdrant cosine、payload 过滤、精确 count | 最终删除，以 pgvector adapter 替换 |
| `backend/src/infrastructure/db/models/chunks.py` | PK 是 `child_id`；child 没有 `knowledge_base_id` 或 embedding | 增加专用 embedding 表模型；不能假设 child 已有知识库列 |
| `backend/src/infrastructure/db/stores/chunk_store.py` | Keyword JOIN version/document，过滤知识库及 READY；hydration 同样过滤 | 替换关键词 SQL；保留 authoritative JOIN、READY 与回表校验 |
| `backend/src/application/ingestion/embed.py` | 分批 upsert 后 `complete_embed()` | 保留重试/取消/状态机；PG batch 写入也须检查 lease/attempt |
| `backend/src/application/ingestion/index.py` | 点数量与 child_count 一致后完成 INDEX | count 改为当前模型的有效向量数；版本 READY 不能只凭表里存在 child |
| `backend/src/composition/shared/qdrant.py`、agent/worker/cli runtime | 构造并关闭 Qdrant client | 改装配为共用 session factory 的 pgvector adapter，删除旧导入和具体类型 |
| `backend/src/composition/shared/health.py`、`infrastructure/probes/qdrant_probe.py` | Qdrant readiness | 删除旧探针；数据库 readiness 增加扩展/schema/index 验证，不重复造健康框架 |
| `backend/src/infrastructure/config/settings.py`、配置响应/前端设置 | Qdrant URL/key/collection/timeout | 删除旧配置；只增加确有调参需求的有界 ANN 参数，响应不暴露 DSN/凭据 |
| `docker-compose.yml`、`.env.example`、`scripts/dev.ps1` 及关联脚本 | QDRANT_URL、depends_on、服务/卷、宿主依赖 | 改 PG18 镜像/资源/初始化；最终移除 Qdrant 服务依赖，但不自动删除旧卷 |
| `pyproject.toml`、`uv.lock` | 有 `qdrant-client`、SQLAlchemy、asyncpg，无 pgvector Python adapter | 增加官方 `pgvector` Python 包并锁定；退役后移除 qdrant-client |
| CLI storage-init/reindex/cleanup、清理用例 | 复用 VectorIndex，多处 runtime 装配 | 覆盖初始化、重新向量化、版本/知识库删除、失败补偿和关闭 |
| README、DESIGN、架构文档、AGENTS 存储约束 | Qdrant + pg_trgm | 实施时同步 ADR、运维与契约；不添加 deprecated shim |

保留 `RetrievalChannel`、FanOut、领域 RRF（`k=60`）、BGE reranker、证据门控、引用防伪、已有 goldenset 和四个前端逻辑测试。不要重写 LangGraph、消息队列或业务领域规则。

## 4. 数据模型与一致性

### 4.1 选择专用 child embedding 表

推荐新建 `child_chunk_embeddings`，一行对应一个 child，向量与 BM25 不共用同一索引。保持 child/parent/版本/权威原文模型原样，避免把 4KB 向量拖入每次 citation hydration 或复制 Qdrant 全套 payload。该表独立于任何派生索引/观测用途；不写 parent embedding。

```sql
-- 概念 DDL：在目标镜像验证并落实为 Alembic migration。
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;

CREATE TABLE child_chunk_embeddings (
    child_id uuid PRIMARY KEY
        REFERENCES child_chunks(child_id) ON DELETE CASCADE,
    knowledge_base_id uuid NOT NULL
        REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    embedding vector(1024) NOT NULL,
    embedding_model text NOT NULL
        CHECK (embedding_model = 'BAAI/bge-m3'),
    CHECK (vector_norm(embedding) > 0)
);
CREATE INDEX ix_child_embeddings_knowledge_base
    ON child_chunk_embeddings (knowledge_base_id);
```

固定模型约束是本次部署契约，不是泛化的多模型框架；若模型改变，显式迁移/重建整个语料，不能只改环境变量。BGE-M3 的 1024 维低于 pgvector `vector` HNSW 的 2000 维索引上限；`vector` 类型本身支持更多维度，**类型上限不能当成 HNSW 上限**。[S4]

注意：`knowledge_base_id` FK 只能证明知识库存在，不能证明它属于这个 child。写入必须 `INSERT ... SELECT` / JOIN 从 `child_chunks -> document_versions -> documents` 推导知识库，不信任旧 payload 或调用者提供的关联；冲突更新不允许改归属。Dense 查询同时校验权威 document 的知识库条件，避免错误冗余 ID 使候选进入诊断或消耗 top-K。可用数据库约束或 RLS 加固，但不能声称两个独立 FK 已实现跨表归属一致性。

不冗余 `parent_id`、`document_id`、`document_version_id`、合同正文、标题路径、行号到向量表；查询 JOIN 权威表返回 `ChannelMatch`。content/切分变化通过现有 replace_version_chunks 删除旧 child，FK cascade 自动删除对应 embedding。缺向量行、零向量、模型不匹配不能视作索引完成。

### 4.2 写入、租约与并发

- embedding HTTP 调用在数据库事务外执行，避免等待模型服务时长持行锁或连接。
- 每批 vectors 用独立短事务批量写入，按 child PK 幂等 upsert。批次从现有 16 开始，按 WAL、commit 延迟和内存测量再调，不预设巨大 batch。
- 同一数据库并不自动让 `upsert()` 和 `complete_embed()` 原子化：当前是分批写入后独立完成状态。继续由 INDEX 门控确认完整性，不把部分成功标为 READY。
- 状态写入已有 attempt 防护不能保护“先于状态写入发生的 embedding 覆盖”。PG 写入事务应锁定对应版本/任务，核对当前 job、attempt、lease 与合法状态后才 upsert；为此需将写入 fence 从应用层传到 adapter（现有 upsert(points) 没有该信息），不能只在最终 complete_embed 检查。
- 删除与旧任务竞态必须显式处理：FK 防止已删除 child 被重建为孤儿向量；不为缺失 child 自动创建数据，记录 VANISHED/SUPERSEDED 并保留现有状态语义。
- 数据库断连、死锁/serialization 等已分类瞬态错误可由既有有界任务策略重试；维度、模型、权限、FK 错误为确定性失败，不盲重试。超时取消后先回滚/释放会话，不吞 `CancelledError`。
- `ensure_ready()` 只检查扩展、维度契约、表和有效索引；不在请求或每个 embedding batch 中创建扩展/重建 HNSW。DDL 由 migrate/受控 CLI 执行。

`count_for_version()` 必须 JOIN child 并限定当前模型/有效向量，不能把 child 行数直接当向量点数；PK + FK + NOT NULL + 固定模型/非零约束使计数核验有实质意义。切换验收再用 child ID 集合双向差集核对，不能仅比较两个总数。

## 5. Dense 查询与索引实践

### 5.1 原生 HNSW cosine

首版保持 float32、cosine 和现有 embedding 服务，避免同时改变模型、量化精度与检索引擎。Qdrant 当前配置 `Distance.COSINE`；迁移后用 `<=>` / `vector_cosine_ops`，通道分数为 `1 - distance`。Qdrant cosine 存储可能已经归一化，导出后仍须检查维度、有限值、非零范数及来源模型，不凭集合维度相同就认定模型一致。[S4][S13]

```sql
-- 初次离线回填：先载入向量，再创建索引。
CREATE INDEX ix_child_embeddings_hnsw_cosine
ON child_chunk_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
ANALYZE child_chunk_embeddings;
```

HNSW 无需训练；比 IVFFlat 的 speed/recall tradeoff 更好，但 build 更慢、用更多内存。`m=16`、`ef_construction=64` 是官方默认起点，不是本项目 benchmark 结论。IVFFlat 仅在 HNSW 超出内存/build 预算时作为候选，需要有代表性的训练数据；lists/probes 按数据分布验证，不按经验替换默认上线。[S4]

### 5.2 必须保留索引可用的 ORDER BY 形状

```sql
-- :query_vector 由 typed bind 绑定；SET LOCAL 值为已校验的配置。
BEGIN;
SET LOCAL hnsw.ef_search = 100;
SET LOCAL hnsw.iterative_scan = strict_order;
SET LOCAL hnsw.max_scan_tuples = 20000;
SET LOCAL hnsw.scan_mem_multiplier = 1;

SELECT e.child_id, c.parent_id, c.document_version_id,
       1 - (e.embedding <=> :query_vector) AS score
FROM child_chunk_embeddings e
JOIN child_chunks c ON c.child_id = e.child_id
JOIN document_versions v ON v.id = c.document_version_id
JOIN documents d ON d.id = v.document_id
WHERE e.knowledge_base_id = :knowledge_base_id
  AND d.knowledge_base_id = :knowledge_base_id
  AND v.status = 'ready'
  AND e.embedding_model = 'BAAI/bge-m3'
ORDER BY e.embedding <=> :query_vector
LIMIT :candidate_limit;
COMMIT;
```

`candidate_limit` 是有界候选预算，不是无限扩张。ANN 内层按距离升序直接 ORDER BY + LIMIT，不能改为 `ORDER BY score DESC` 的函数表达式而假设仍用 HNSW。若需稳定 UUID tie-break，先获取有界候选，再在外层按 distance/child_id 排序截取通道 limit；在真实计划中验证 JOIN、READY 和授权过滤位于截断之前，不能全库 top-K 后在 Python 筛选。[S4]

该 SQL 是查询语义，不保证 PostgreSQL 必然选择 HNSW；选择 B-tree + 精确距离排序在小知识库可能更好。验收保存 `EXPLAIN (ANALYZE, BUFFERS)`、实际行数与 plan，不在生产用全局 `enable_seqscan=off` 强迫 ANN。

### 5.3 过滤：性能隔离不等于授权隔离

pgvector 官方明确：ANN 通常先 index scan 再过滤。例如 10% 命中率、默认 `ef_search=40`，平均可能只有约 4 行通过；这不是 SQL WHERE 失效，而是有限 ANN 候选被过滤后不足。[S4]

处理顺序：

1. 小知识库或非常选择性的过滤：使用知识库 B-tree + 精确距离排序，建立同过滤范围 exact baseline。
2. HNSW：启用 `>=0.8.0` 的 iterative scan，首版 strict_order；以 ef_search、max_scan_tuples、scan_mem_multiplier 控制召回/延迟/内存，均有界，记录不足 K 的结果。
3. 真实分布证明共享 HNSW 下小租户召回或资源隔离不足后，采用 PostgreSQL LIST 分区/独立租户表，使各分区有自己的 HNSW；按大租户和租户数量制定分区生命周期，不给每个 UUID 自动建无数索引。
4. 少量固定知识库可评估 partial HNSW，但 generic prepared plan 未必证明参数化查询满足 partial predicate；必须验证真实 asyncpg 执行计划。

共享 HNSW 中其他租户数据会影响 recall/速度。SQL/RLS 防结果越权，分区解决性能和 ANN 候选干扰，二者不能混为一谈。首版不强行承诺共享索引满足任何规模，门禁失败则先分区、重新验收再切换。PostgreSQL 原生分区也不是 ParadeDB beta `partition_by`。[S4][S6]

### 5.4 Python 集成与超时

使用现有 SQLAlchemy AsyncSession/session factory；官方 `pgvector` Python 包的 `VECTOR(1024)`、`cosine_distance()` 与 typed bind，不手写向量字符串序列化或距离算法。底层 asyncpg 类型注册按官方示例执行；使用 SQLAlchemy async engine 时在 sync_engine connect hook 通过适配连接的 `run_async` 注册，验证普通 INSERT、upsert、typed query、COPY 与池复用的实际编码行为，不额外创建 asyncpg pool。[S10]

迁移创建扩展早于依赖 vector codec 的业务连接；Alembic 初始化连接不得因 vector 尚未创建而先注册失败。`VectorIndex.close()` 不 dispose 所有者共享的 engine；engine 生命周期仍由 runtime 统一负责。

Dense/Keyword 并发各自独立 AsyncSession，不能共享事务或可变会话；连接池 checkout timeout、asyncpg command timeout、事务内 `statement_timeout`/`lock_timeout` 和外层 channel timeout 都有界。沿用现有 database timeout（默认 5s）作为起点，ANN 若超预算先解释原因；调长不是默认修复。只用 SET LOCAL，避免池复用导致后续用户继承 ANN/租户参数。

## 6. BM25 替代 pg_trgm

当前 Keyword 先 JOIN 权威 document/version，过滤知识库和 READY，再执行转义的 LIKE substring；similarity 只排序。因此 BM25 不是等价替换：tokenizer 会改变合同定义词、条款编号、CJK 短词、中英文混排与拼写噪声的召回。

```sql
-- 当前官方文档 API 的概念示例；须对固定 tag 验证 tokenizer/SQL。
CREATE INDEX ix_child_chunks_lexical
ON child_chunks USING paradedb (child_id, content, document_version_id);

SELECT c.child_id, c.parent_id, c.document_version_id,
       pdb.score(c.child_id) AS score
FROM child_chunks c
JOIN document_versions v ON v.id = c.document_version_id
JOIN documents d ON d.id = v.document_id
WHERE d.knowledge_base_id = :knowledge_base_id
  AND v.status = 'ready'
  AND c.content ||| :query
ORDER BY pdb.score(c.child_id) DESC, c.child_id
LIMIT :limit;
```

这保留真实 `child_id` 和现有 JOIN，不假装 child 已有知识库列。**授权条件必须在同一 SQL 的 LIMIT 前，计划需确认 join/filter 与 Top-K 的行为和成本。** 如果过滤无法达到预算，再对 child 增加由事实关系推导并严格维护的知识库过滤列，纳入 BM25 index；不能静默引入不受约束的第二份归属。第一版先证明当前 JOIN 形状能满足预算，不把额外冗余 schema 作为既定需求。

词项实验：English/Unicode 或 ICU、ChineseCompatible、Lindera；定义词/条款编号可增加经验证的独立字段。Literal 是整字段 token 的方向，**并不自动保留任意 substring**；ChineseCompatible 的字符 token 也不等价于任意短语。不能把名称当召回证明。每张表当前仅允许一个 ParadeDB index，tokenizer A/B 在独立 staging 表/库或顺序重建进行，不在同一 child 表上创建两套 BM25 index。[S6][S7][S14]

普通用户 query 使用参数化 match（disjunction/conjunction 根据 goldenset 决定），不要透传可执行 SQL 或把 parser query language 当自然语言。处理空串、长度上限、特殊字符、无效语法和取消。UUID、query、limit 都通过 typed binding。

RRF 只融合 rank；pgvector cosine score 与 BM25 score 不直接相加。保持通道名 dense/keyword，不因换 provider 改稳定 API。候选一律调用现有 `load_records()`，只接受授权知识库的 READY child，再由权威对象存储核验原文与行号。

## 7. 部署、容量与数据库迁移

### 7.1 不原地盲换现有数据卷

Compose 的 PG18 数据卷挂载为 `/var/lib/postgresql`，现有镜像为 Alpine；候选为 Debian trixie。**同 major 不能证明 OS/locale/extension/PGDATA 兼容，严禁直接替换镜像并挂载唯一生产卷。** 推荐固定镜像建立新卷，在 staging 用逻辑备份/恢复验证数据库、角色、locale/collation、extension 和应用迁移。跨 OS/collation 的索引必须检查并按需重建；不在同一窗口再做 PG major upgrade。

当前 PostgreSQL 还承载 Langfuse 数据库，checkpoint 连接亦需要检查。全实例替换须盘点所有数据库/角色/权限和初始化脚本，分别恢复并验证；如果生产不允许共享搜索/业务/观测资源，将 Langfuse 放到独立 PostgreSQL 实例，但不要为本次 RAG 迁移无依据地重构观测平台。

目标 ClauseRAG 库装扩展，应用只授予 SELECT/DML 等必要权限；业务进程不使用超级用户、CREATE EXTENSION 或重建索引权限。数据库端口不直接对公网开放，WAL、备份、导出 vectors 和原文视作合同敏感数据。

### 7.2 资源预算

pgvector `vector` 裸类型存储为 `4 * dimensions + 8` bytes：1024 维为 **4104 bytes/行**，一百万向量约 **4.104 GB（3.82 GiB）**，不含 heap/TOAST、PK、B-tree、HNSW、BM25、WAL、旧行、备份和重建峰值。不能将其当内存预算或完整磁盘估算。[S4]

分别测量与预留：

- heap/TOAST、HNSW 和 BM25 的实际 `pg_relation_size`/`pg_total_relation_size`；build/reindex 同时保留旧新索引的磁盘峰值。
- shared_buffers、OS page cache、每条查询 work_mem、HNSW iterative scan 内存、并行 maintenance memory；乘以真实并发而非单请求。
- embedding 写入和索引构建对 API 事务、LangGraph checkpoint、Langfuse、WAL、fsync 和磁盘队列的影响。
- `maintenance_work_mem` 只在受控构建会话提高，不照抄官方 8GB 示例；Docker `shm_size` 按并行 HNSW build 要求配置，不超过容器/主机预算。[S4]
- 各进程 pool_size/max_overflow × 实例数，加 checkpoint/观测/运维连接，应低于 max_connections 且留维护余量。

先 COPY/批量回填，再建 HNSW/BM25、ANALYZE；不把索引创建放进每次文档 INDEX job。线上增建 HNSW 使用 `CREATE INDEX CONCURRENTLY` 的受控阶段，不能置于 Alembic 默认事务块；检查 `indisvalid`/`indisready`，失败后清理 INVALID 索引再重试。分区父索引不能直接并发创建，需逐分区构建/挂接。[S4][S11] BM25 的并发构建能力单独对固定 pg_search 版本验证，不能套用 pgvector 的结论。

## 8. 分阶段实施与切换

采用**staging 先验证、生产有界维护窗口切换**，优先避免新增长期 provider 矩阵、dual-write 或第二条生产编排。无法提供维护窗口才另立迁移 ADR，设计持久化增量同步/短期双写、删除传播和清理工单；任何临时双写必须标记 `ponytail: migration until M<X>` 并绑定清理工单。

### M0：固定版本和旧系统基线

1. 固定候选 PG18 镜像 digest、扩展版本，验证 Python 3.12/asyncpg/SQLAlchemy、初始化、迁移、连接池和 pgvector codec。
2. 备份所有 PostgreSQL 数据库与必要角色、Qdrant collection snapshot、对象存储元数据/制品；实际恢复验证，不只确认文件存在。
3. 对同一知识库/文档版本快照保存 Qdrant Dense、pg_trgm、RRF/reranker/gate 基线，记录模型、维度、top-K、query 桶、数据 hash 和延迟。
4. 记录待处理 RabbitMQ 作业、运行中 lease/attempt、删除/清理作业及容器资源预算；明确维护窗口、恢复责任人和回滚截止条件。

### M1：新 PostgreSQL/ParadeDB 与向量回填

1. 新卷恢复事实库；加载扩展并创建 embedding 表。保持 UUID、child/parent/version、原文与行号，不重新切分文档。
2. 优先从 Qdrant scroll 导出 dense vector（with_vectors=true）与 child identity，分页 offset 持久化，批次有超时/退避/重试上限；不将百万向量载入内存。[S13]
3. 与事实表 JOIN 验证真实 child、文档版本、知识库、模型 provenance 和 content/切分快照一致性；未知模型、错误维度、零/非有限值、孤儿或 payload 冲突进入审计隔离，不填零向量、不静默跳过后仍宣布完成。
4. 仅缺失或无法证明可复用的 child 通过现有 embedding 用例重新计算；若需全量重新 embedding，要单独计费和质量验收，不能宣称与旧向量逐元素一致。
5. 有界 COPY/upsert 回填，记录每批 checkpoint、输入输出 count/hash、失败 ID 和模型；PK 保证可恢复幂等。先回填后建索引，ANALYZE。
6. 核对 READY 版本的 child ID 集合、有效 embedding 集合、现有 Qdrant identity，差集为零；pending/failed 版本按现有作业状态分类，不强制伪装成 READY。

### M2：先验收 Dense，再验收 BM25

先比较“Qdrant + pg_trgm”与“pgvector + pg_trgm”，隔离 Dense 引擎变化；再比较“pgvector + BM25”。都使用相同模型、快照、授权范围和通道预算，不同时改 reranker 阈值掩盖召回下降。

同范围精确 cosine 排序作为 ANN ground truth，确认实际 plan 没有走近似索引；在隔离评估会话禁用 index scan 并 EXPLAIN 验证或使用独立无 ANN 的 staging 对照。ANN Recall 和业务 goldenset Recall 是不同指标，二者都要测。[S4]

完成 tokenizer、真实 asyncpg 参数化计划、租户过滤、删除、重试、取消、INDEX count、资源压力、恢复/升级演练后，才批准生产切换。

### M3：生产停写、最终追平与切换

1. 开启受控维护状态，停止新上传/重索引/删除/清理及会修改迁移数据的业务入口；停止 dispatcher 发新任务，让 worker 有界 drain，确认无活动写入/lease；不要 purge RabbitMQ。
2. 冻结后的最终备份/导出与新库恢复或最终差量追平须有明确时间点。旧任务不允许继续写旧库；记录 broker backlog、数据库 outbox/job 状态，保证新 worker 重启后可幂等恢复，不复制两套独立消费链。
3. 对最终快照重新执行 ID 差集、向量有效性、index validity、EXPLAIN 和关键查询检查；后台写入未停止的 scroll 不是一致性备份。
4. 部署 PG adapter 和新数据库连接，更新所有 API/agent/worker/CLI/checkpoint/观测 DSN 所有者；版本发布删除旧 Qdrant runtime 路径。先验收 pgvector + pg_trgm 可回滚版本，再启用已验收 BM25 发布，避免两个未知因素叠加。
5. 容器路径启动并通过 nginx readiness/config、真实合同摄取/问答/引用、版本与知识库删除核验后恢复写入；记录切换点与迁移工件。

这不是“改一个 Dense provider 开关”：还涉及数据库恢复、全进程装配、写入门控、连接池、清理和 Qdrant 退役。若维护窗口无法容纳 restore/index build，M0 必须量出 RTO 并改为经批准的在线迁移，不临场无限延长停机。

### M4：回滚与退役

- **恢复业务写入前**：保留旧 PG/Qdrant 快照和旧 release，可将所有进程一起切回并核对 broker/job 状态；不得让两个 release 同时消费同一待迁移状态。
- **恢复业务写入后**：旧 Qdrant 已经落后，不能只切环境变量。先冻结写入，将新 PG 的新增/修改/删除以及 embeddings 追平至回滚目标，并复核身份集合/引用；做不到则回滚应用到 PG 支持版本而非丢弃新数据。RPO 要显式批准，不默认接受数据丢失。
- BM25 相关性失败，可回退已验收的 pgvector + pg_trgm release，保持新事实库和向量；不要为了 Keyword 回滚把 Dense 一起退回旧快照。
- 观察窗口通过后删除 Qdrant adapter/composition/probe、配置、依赖、服务 depends_on、dev 脚本残留与前端配置显示，重新生成 uv.lock。暂存旧 snapshot/volume 是回滚工件，不是在线双写系统。
- 删除旧 Qdrant 卷与导出工件须经数据负责人批准、按保留期销毁；不得用 `docker compose down -v` 清理共享基础设施。

## 9. 安全、故障、备份与升级

### 隔离与失败

知识库 ID 来自授权后的应用入口，不由用户任意改写；数据库 SQL 同时执行 scope + READY 过滤，hydration 再复核。若采用 RLS，使用非 owner/非 BYPASSRLS 的真实应用角色，按需要 FORCE RLS、事务局部 tenant context；过滤到知识库不自动等于完成多用户授权。分别测 forged payload、越权 ID、已删 child、非 READY 版本以及并发 scope 切换。

Dense 单次超时可由现有 FanOut 分类并让 Keyword 继续；BM25 query 失败可让 Dense 继续。共享数据库故障会影响两路及 hydration，必须按现有协议受控失败/弃答，不写虚构证据。日志只记版本、provider、latency、plan/模型 schema 版本、聚合计数和错误类别，不记录向量、DSN、合同原文或完整用户 query。

### 复制和 HA 必须分别判断

- pgvector 原生 HNSW/IVFFlat 使用 PostgreSQL WAL，支持复制和 PITR。[S4]
- **这不表示 pg_search Community index 也支持物理复制。** ParadeDB 官方将 index 物理复制、HA failover/read replicas 放在 Enterprise/Cloud；Community 可做逻辑复制目标。[S5][S9]
- 如果 PostgreSQL/ParadeDB 成为唯一事实库，不能把备用机能启动 PG 当成完整检索 HA；须验证 PG 表、pgvector index、BM25 index 全部可查询。严格 HA 要求应选择 Enterprise/Cloud，或由业务批准故障后 BM25 重建的 RTO/降级窗口。
- logical replication 只复制数据，不复制 DDL/index/扩展安装；订阅端须安装相同 vector 类型、创建 schema、索引并验证 apply/backlog。[S12] 本方案不默认新增生产逻辑复制服务。

### 恢复与维护

逻辑备份包含 vector 表数据，目标必须先有可用扩展二进制；恢复 table/schema/data 后重建 HNSW/BM25，核对模型/identity/READY。pgvector 的 WAL/PITR 能力与 pg_search Community 的索引恢复限制分别演练；备份验收终点是可查询和真实 citation，不是 pg_isready。

监控 pg_stat_activity、pg_stat_statements、pool 等待、lock、WAL/磁盘、build progress、pgvector/BM25 索引体积、dead tuples/autovacuum、查询 rows 与不足 K 比例。pgvector 官方提示 HNSW vacuum 可能慢，可评估 `REINDEX INDEX CONCURRENTLY` 后 VACUUM，但要安排额外磁盘与 I/O 预算；不能成为每晚无条件重建策略。[S4]

ParadeDB 升级先安装新 binary，再更新 extension catalog；pgvector 同样按目标 extension upgrade 路径。每次锁定 digest，restore 至 staging，执行写入/ANN/BM25/引用/恢复检查。PG major upgrade、OS 切换、vector model、tokenizer schema、extension version 变更分开发布，不承诺旧 binary 可以读取新 index/catalog。[S15]

## 10. 验收与决策门

以下为建议发布阈值，不是已测结果；M0 基线后由发布负责人冻结，失败不能靠临时修改指标过关。

| 维度 | 发布门 |
|---|---|
| 数据一致性 | READY child 与当前模型有效 embedding 双向差集为零；无孤儿/错误归属/零向量；原文坐标不变 |
| 安全与引用 | 越权/跨知识库/非 READY 命中为零；每条接受 citation 均可核验对象存储原文与版本行号 |
| Dense ANN | 同 scope exact cosine 对照 Recall@30 起点 >= 0.95；小知识库/极低选择率必须分桶达标，不只看整体均值 |
| 业务相关性 | Dense/Keyword/final Recall@30 或实际 K、MRR/nDCG、citation candidate coverage 与既有 goldenset 基线比较；精确条款/CJK 关键桶不下降 |
| 延迟 | p50/p95/p99 在现有 channel/DB timeout 内；建议 p95 不超过旧基线 1.2 倍，若要接受回退必须显式批准 |
| 资源和写入 | 目标并发 + ingest + checkpoint/观测负载下无 OOM/连接耗尽/持续 WAL 增长；batch/index build/delete 在预先确定预算内 |
| 故障与取消 | 向量写入失败、ANN timeout、BM25 parser/index 故障、数据库整体故障、旧 attempt、删除竞态和请求取消均有受控结果 |
| 运维 | 固定版本 restore、扩展升级、索引重建和写入前/写入后回滚演练通过；记录实际 RTO/RPO |

评估桶至少包括：定义词、条款编号、CJK 短词、中英文混排、自然语言、拼写/格式噪声、跨段问题；知识库维度包括小/大、低命中比例、租户偏斜、大量非 READY/dead tuples。使用仓库现有 410 条 / 100 合同 goldenset 和评估 CLI，报告每桶及端到端结果，不新增浅层测试或永久 probe 套件。

实施完成必须执行两级验证：

```powershell
pwsh scripts/check.ps1
pnpm --dir frontend run check
pnpm --dir frontend run test

docker compose --profile app up -d --build --wait
Invoke-WebRequest http://localhost:5173/health/ready
Invoke-WebRequest http://localhost:5173/api/v1/config
```

在 nginx 入口真实导入合同并等待 EMBED/INDEX/READY，进行问答/SSE/引用核验、删除版本/知识库、重试及超时；配置与 readiness 不再依赖 Qdrant。两路候选都须经过原 hydration 和 citation gate。保存响应原文、计划、基线/新结果、版本 digest 与资源数据作为发布证据；静态门禁不能替代运行时验收。

## 11. 优先级与实施完成定义

1. **P0：版本与恢复可行性**。先证明固定 PG18 ParadeDB 镜像、内置 pgvector、现有全部数据库恢复、扩展/codec 和 HA/RTO 可接受；未通过不进入生产迁移。
2. **P1：Dense 替换闭环**。embedding 表/adapter、attempt fence、全部装配/cleanup/CLI/readiness、迁移回填、ANN/exact 和真实问答验收；先保留 pg_trgm 验证单因素变化。
3. **P2：BM25 闭环**。固定 API/tokenizer、scope/READY 的真实计划、goldenset 与 citation coverage 通过后替换 Keyword；保留可部署的已验收 PG + pg_trgm release 作回滚工件。
4. **P3：切换与删除**。执行有界停写/追平、恢复写入后的回滚演练、Qdrant runtime 硬删除与文档/锁文件同步，按保留期销毁旧卷。

完成定义：Qdrant 不再是运行依赖；Dense 只写/查 pgvector；Keyword 使用已验收 pg_search；没有长期 embedding 双写或 legacy shim；隔离、引用、摄取、清理、容器入口与恢复演练都有真实证据。

本次未给出已验证的镜像 digest、性能数字或可直接执行的迁移脚本。共享 ANN 下过滤召回、同库资源竞争、ParadeDB Community 的 BM25 HA 限制与停写恢复时长，是正式实施前必须实测并批准的四个发布风险。

## 12. 一手来源

研究结论依据官方材料；可变文档与固定 tag 需在发布时再次核对。raw.githubusercontent.com 直接抓取失败后，pgvector README 改经 GitHub 页面成功取得，版本文件通过 GitHub Contents API 核对；搜索结果中的 PR 线索不作为镜像实际版本证据。

- [S1] [ParadeDB v0.26.1 release](https://github.com/paradedb/paradedb/releases/tag/v0.26.1)、[latest release API](https://api.github.com/repos/paradedb/paradedb/releases/latest)。
- [S2] [固定 tag PG18 Dockerfile](https://github.com/paradedb/paradedb/blob/v0.26.1/docker/Dockerfile.paradedb-18)、[固定 tag pg_search control](https://github.com/paradedb/paradedb/blob/v0.26.1/pg_search/pg_search.control)、[Self-Hosted extension](https://www.paradedb.com/docs/operate/deploy/self-hosted/extension.md)。
- [S3] [ParadeDB Indexing Vectors](https://www.paradedb.com/docs/reference/indexing/indexing-vectors.md)、[Vector overview](https://www.paradedb.com/docs/reference/vector/overview.md)。
- [S4] [pgvector 官方 README](https://github.com/pgvector/pgvector/blob/master/README.md)、[v0.8.6 README](https://github.com/pgvector/pgvector/blob/v0.8.6/README.md)、[官方 tags](https://github.com/pgvector/pgvector/tags)。重点：HNSW/IVFFlat、Filtering、Iterative Index Scans、Tuning、Monitoring、Reference、WAL/PITR。
- [S5] [ParadeDB High Availability](https://www.paradedb.com/docs/operate/deploy/self-hosted/high-availability.md)、[Enterprise](https://www.paradedb.com/docs/operate/deploy/enterprise.md)。
- [S6] [Create an Index](https://www.paradedb.com/docs/reference/indexing/create-index.md)。当前 access method、key_field、单表单 index、tokenizer 与 partition_by beta。
- [S7] [Match](https://www.paradedb.com/docs/reference/full-text/match.md)、[Tokenizers](https://www.paradedb.com/docs/reference/tokenizers/overview.md)。
- [S8] [BM25 Scoring](https://www.paradedb.com/docs/reference/full-text/score.md)、[Indexed filters](https://www.paradedb.com/docs/reference/filtering/indexed.md)。分数/tie-break 与过滤计划。
- [S9] [ParadeDB Guarantees](https://www.paradedb.com/docs/concepts/guarantees.md)、[Limitations & Tradeoffs](https://www.paradedb.com/docs/concepts/limitations.md)。事务、复制和扩展边界。
- [S10] [pgvector-python 官方集成](https://github.com/pgvector/pgvector-python)、[SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)。SQLAlchemy VECTOR、asyncpg register_vector 与连接适配。
- [S11] [PostgreSQL 18 CREATE INDEX](https://www.postgresql.org/docs/18/sql-createindex.html)。并发构建、INVALID 索引、事务和分区限制。
- [S12] [PostgreSQL 18 logical replication restrictions](https://www.postgresql.org/docs/18/logical-replication-restrictions.html)。DDL/schema 不复制。
- [S13] [Qdrant points/scroll](https://qdrant.tech/documentation/manage-data/points/)、[Qdrant cosine](https://qdrant.tech/documentation/concepts/collections/)。源数据导出和距离语义。
- [S14] [ChineseCompatible](https://www.paradedb.com/docs/reference/tokenizers/available-tokenizers/chinese-compatible.md)、[Lindera](https://www.paradedb.com/docs/reference/tokenizers/available-tokenizers/lindera.md)。CJK tokenizer 候选，而非合同召回承诺。
- [S15] [Upgrading ParadeDB](https://www.paradedb.com/docs/operate/deploy/upgrading.md)、[Reindexing](https://www.paradedb.com/docs/operate/index-maintenance/reindexing.md)。
