# 恢复记录：flattening 误删后的后端重建（Recovery after package flattening）

日期：2026-10-05 · 依据：`docs/architecture/backend-recovery-after-flattening.md`
方法：先用 context7 核对各技术栈官方文档（见下），再从 Pi/Claude 会话 transcript 重建被删文件，最后用
静态检查逐条收敛契约。

> **历史记录（ADR-0029）**：文中涉及 LightRAG / 图谱隔离的部分随图谱通道一并删除，`lightrag-hku` 与
> `numpy` 已不在依赖中。本文件保留为当时的恢复记录。

**结论：Gate A / B / C 通过（ruff、format、strict pyright 全绿，9 个顶层包可导入，wheel 可构建）。
Gate D / E 未执行——本机 Docker daemon 未运行，真容器探针与最终 E2E 无法进行，恢复完成度不能据此宣称。**

---

## 1. 官方文档核对（写代码前）

仓库已存有上一轮用 context7 REST API 抓取的核对记录，本次沿用并补抓缺口：

| 技术栈 | 记录 | 本次补充（context7 MCP，2026-10-05） |
| --- | --- | --- |
| FastAPI | `docs/research/official-docs-fastapi.md`（依赖覆盖、lifespan、router 依赖） | — |
| SQLAlchemy 2.0 asyncio | `docs/research/official-docs-sqlalchemy.md`（`async_sessionmaker`、每任务一个 session、`session.begin()`） | 核对 store 的读写路径写法 |
| Taskiq | `docs/research/official-docs-taskiq.md`（broker/receiver/`SmartRetryMiddleware`、`supply_stage_runner` 取代 `TaskiqDepends`） | `/taskiq-python/taskiq`：task 声明、broker startup/shutdown、retry middleware |
| LangGraph | `docs/research/official-docs-langgraph.md` | `/langchain-ai/langgraph`：`StateGraph(context_schema=…)` + `Runtime[Context]` 注入、`AsyncPostgresSaver`、`astream` |
| Qdrant | `docs/research/official-docs-qdrant.md` | `/qdrant/qdrant-client`：`AsyncQdrantClient` 建集合/写入/按 payload 删除、timeout |
| LightRAG / Langfuse / SiliconFlow | `docs/research/official-docs-{lightrag,langfuse-aegra,siliconflow}.md` | — |

核对结论与实现一致：composition 用 `lifespan`/显式 `close()`；store 每次调用取自己的 `AsyncSession`，写路径
`async with sessions.begin()`，不引入自定义 Unit of Work；Taskiq 的 task 声明留在队列适配器、worker 装配时用
`supply_stage_runner` 注入阶段执行体；LangGraph 用 runtime context 注入检索/会话协作者，状态只留
`RetrievalRecord`。

## 2. 重建方法

`.probe/recover/extract.mjs`（本次新写，`--verify` 模式先证明方法可靠）：

1. 扫描全部 419 个会话 transcript，按路径把 `read`/`write`/`edit` 事件归到 `<package>/<module>.py`；
2. `read` 结果是某时刻磁盘内容的逐字窗口，按 offset 拼接；同一 burst 内首窗口从第 1 行开始、末窗口没有
   `[N more lines in file…]` 标记时，该 burst 即为该时刻的完整文件；
3. burst 之后的 `edit` 按时间顺序叠加（`edit` 是精确文本替换，命中即为证据，未命中会被报告而不是猜测）；
4. 用磁盘上仍存在的文件做对照：95 个在盘文件中 40 个可逐字节重建（仅差 `rag_platform.` 前缀），其余 9 个差异
   全部可解释为更早版本（`ChunkStore`→`ChunkRepository` 改名、中间态空行等）。

因此重建可信；随后按下面的分类落盘。

## 3. 从 transcript 重建并落盘的文件

**3.1 被整体删除的 14 个模块**

| 文件 | 证据（重建来源） | 行数 |
| --- | --- | --- |
| `application/cleanup_lane.py` | read@2026-10-03T15:24:38Z + 7/7 后续 edit | 250 |
| `application/document_ingestion.py` | read@2026-10-03T12:50:42Z + 28/33 后续 edit | 391 |
| `application/ingestion_store.py` | read@2026-10-04T06:20:18Z（与前缀归一化后的在盘版本逐字节一致） | 436 |
| `composition/agent.py` | read@2026-10-04T06:17:14Z | 175 |
| `composition/api.py` | read@2026-10-04T06:17:14Z | 109 |
| `composition/cli.py` | read@2026-10-03T15:20:11Z | 270 |
| `composition/resources.py` | read@2026-10-03T12:50:28Z + 12/12 后续 edit | 436 |
| `composition/worker.py` | read@2026-10-04T06:18:09Z | 138 |
| `domain/cleanup.py` | read@2026-10-03T15:23:38Z + 2/2 后续 edit | 95 |
| `infrastructure/chunk_store.py` | 两个 read burst 拼接 | 263 |
| `infrastructure/cleanup_store.py` | read@2026-10-03T15:18:23Z + 5/5 后续 edit | 258 |
| `infrastructure/conversation_store.py` | read@2026-10-03T12:49:24Z | 315 |
| `infrastructure/document_store.py` | read@2026-10-03T12:53:15Z + 8/8 后续 edit | 396 |
| `infrastructure/ingestion_store.py` | read@2026-10-03T12:53:15Z + 34/39 后续 edit | 1181 |

**3.2 在盘但被回退到更早版本的模块**（candidate 才是全树调用的那份契约）

| 文件 | 该版本带回来的契约 |
| --- | --- |
| `application/retrieval.py` | `RetrievalService.retrieve` / `RetrievalResult` / `RetrievalDiagnostics` / `RetrievalRecord` |
| `application/document_catalog.py` | 删除不再内联调用已废弃的 `application/{graph,vector}_cleanup`，改由持久化 cleanup intent 承担 |
| `application/knowledge_bases.py` | 同上（H4） |
| `application/storage.py` | `StoredObject.size_bytes` / `sha256` |
| `application/dispatch.py` | `dispatch_committed_job`（提交后投递、失败只上报） |
| `application/parse_document_version.py` | claim token 随写入（H1） |
| `application/chunk_document_version.py` | attempt 作用域对象键 + 对 parse artifact 的 digest/size 校验 |
| `application/embed_document_version.py` | 同上（claim 令牌） |
| `application/index_document_version.py` | 同上 |
| `application/build_document_graph.py` | 同上 |
| `application/stage_failure.py` | 同上 |
| `domain/parsing.py` | `ABANDONED_ATTEMPT_CLASS` / `ABANDONED_ATTEMPT_MESSAGE` |
| `infrastructure/job_queue.py` | `supply_stage_runner`，适配器不再导入应用模块（H3） |
| `infrastructure/knowledge_base_repository.py` | 删除时在同一事务写入 cleanup intent（H4） |

## 4. 无法逐字恢复、按契约手写/补齐的部分

这些位置的 transcript 版本比在盘版本更旧（例如 orm 的在盘版本已有 `DomainUuid` 与扁平导入），因此**不整体覆盖**，
只做最小补齐：

- `infrastructure/orm.py`：新增 `CleanupIntentRow` 与 `to_cleanup_intent`（对齐 `0006_cleanup_intents`）。
- `infrastructure/settings.py`：新增 `cleanup_retry_delay_seconds`、`cleanup_lease_seconds`。
- `domain/ports.py`：重写为**共享端口子集**，不再是中央目录（708 → 83 行，只剩 3 个协议）。按“只被一个
  application 模块使用就搬过去”的规则逐个确认消费者数：`SessionRepository`（仅 `application/auth.py`）已移入
  `application/auth.py`，`DependencyProbe`（仅 `application/health.py`）已移入 `application/health.py`；
  `PasswordHasher`、`UserRepository`（`accounts.py` 与 `auth.py` 各两个消费者）与 `DocumentParser`
  （`application/parse_document_version.py` 与 `composition/resources.py`）保留在共享模块，并在模块 docstring
  里写明为何在此、为何它不是旧的总线。`TokenCounter` 移到 `domain/chunking.py`，`ConversationRepository`
  移到 `application/conversations.py`，`KnowledgeBaseRepository` 归 `application/knowledge_bases.py`，
  `DocumentRepository` 删除（由 `IngestionStore` 取代），`RetrievalChannel` 删除（`application/retrieval.py`
  自带同名协议，且无人导入）。
- `domain/chunking.py`：新增 `TokenCounter`；`ChunkTarget` 增加 `markdown_checksum`/`markdown_size_bytes`；
  `ChunkClaim` 增加 `job_id`；`chunks_object_key(version_id, job_id)` 改为 attempt 作用域键。
- `domain/embedding.py` / `domain/graph.py`：`EmbeddingClaim`、`IndexClaim`、`GraphBuildClaim` 增加 `job_id`。
- `application/document_ingestion.py`：`run_stage` 改为调用本模块的私有阶段处理器；修好被拼接破坏的
  `_parse` 定义（`raise AssertionError` 残片 + 非 async 定义）；五处 `attempt(...)` 调用点对齐。
- `infrastructure/ingestion_store.py`：删除重复出现的 `_replaced_key` 定义。

## 5. 有意不恢复（明确不还原清单）

`rag_platform/` 外层包、`composition/container.py`、`application/run_ingestion_job.py`、
`application/run_parse_job.py`、`application/graph_cleanup.py`、`application/vector_cleanup.py`、
`application/documents.py`、`application/cleanup.py`、`infrastructure/document_repository.py`、
`infrastructure/chunk_repository.py`、`infrastructure/conversation_repository.py`、`domain/ports.py` 的中央目录形态。
未添加任何 `rag_platform = …` 别名、转发模块或旧仓储包装。

## 6. 验证结果

### 6.1 本轮补充执行的检查项

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 残留旧路径 | `Select-String 'rag_platform\|composition\.container\|run_ingestion_job\|document_repository\|chunk_repository\|conversation_repository'` | **无输出** |
| `domain.ports` 引用 | `Select-String 'from domain\.ports import'` | 仅 2 处：`application/accounts.py`、`application/auth.py`（各取 `PasswordHasher`+`UserRepository`） |
| `domain/ports.py` 形态 | `Select-String '^class '` | 3 个协议、83 行——共享契约而非中央总线 |
| 必需文件存在 | 19 个关键路径逐一 `Test-Path` | 全部存在 |
| 旧运行时文件未恢复 | `composition/container.py` 等 5 个路径 | 均不存在 |
| 字节码编译 | `uv run python -m compileall -q backend/src` | exit 0 |
| 入口导入 | 13 个模块一次性 import | 通过 |
| 锁文件 | `uv sync --locked` / `uv lock --check` | 均 exit 0；136 个包，**无任何包版本变动** |
| 依赖声明审计 | `.probe/recover/check_declared_imports.py` | 仅剩 `botocore`（有意不声明，见下） |

### 6.2 依赖决策（按恢复文档的原则）

- `langgraph` / `langgraph-checkpoint-postgres`：保留，源代码直接导入（`langgraph.graph`、`langgraph.runtime`、
  `langgraph.checkpoint.postgres.aio`）。
- `apscheduler`：全仓库无任何引用（scheduler 仍是最小实现），**未恢复**。
- `langchain` / `langchain-openai`：全仓库无引用（provider 边界是普通 HTTP 适配器），**未恢复**。
- 审计新发现的“直接导入但未声明”项，按“当前源代码实际使用的依赖必须保留”补齐：
  - `langchain-core>=1.6,<2`——`agent_runtime/runner.py` 的 `RunnableConfig` 就是它的类型；
  - `numpy>=2.5,<3`——`infrastructure/lightrag_graph.py` 交给 LightRAG 的嵌入函数返回 `numpy.ndarray`；
  - `psycopg[binary]` → `psycopg[binary,pool]`——checkpointer 开的是 `AsyncConnectionPool`，而
    `langgraph-checkpoint-postgres` 只声明裸 `psycopg`（官方做法就是加 `pool` extra）。
  - `botocore` **有意不声明**：boto3 用 `==` 精确钉住 botocore，这里再写一个范围只会与 boto3 自己的钉版冲突；
    而 `botocore.config` / `botocore.exceptions` 是 boto3 官方文档自己教用户直接导入的，已在 `pyproject.toml`
    的 `boto3` 条目旁写明理由。
- `uv.lock` 重生成后逐行核对：只有根包的依赖声明增加（+9/-2 行），**没有包版本变化**，无无关 churn。

### 6.3 恢复文档 Gate

| Gate | 命令 | 结果 |
| --- | --- | --- |
| A 源完整性 | 全树 grep `rag_platform\|composition\.container\|run_ingestion_job\|*_repository\|graph_cleanup\|vector_cleanup` | **无输出**；`from domain.ports import` 只剩 `application/{accounts,auth}.py` 两处（`PasswordHasher`+`UserRepository`，各两个消费者）；无 transcript 标记（`MISSING LINE`、`more lines in file`） |
| B 静态检查 | `scripts/check.ps1` | **通过**：`uv sync --locked`、`ruff check`、`ruff format --check`、`pyright` 全绿（0 error / 0 warning） |
| C 导入与打包 | `uv run python -c "import api.main, api.agent_app, agent_runtime.graph, agent_runtime.runner, cli.main, worker.main, …"`；`uv build --wheel` | **通过**：全部入口可导入；wheel 含 9 个顶层包（agent_runtime/api/application/cli/composition/domain/infrastructure/scheduler/worker） |
| D 真容器探针 | 健康、鉴权、上传/parse、stage 链、重复投递与陈旧 revision 围栏、cleanup 租约、检索融合、SSE 取消、引用校验、图谱隔离 | **未执行**：`docker ps` 报 daemon 未运行 |
| E 最终验收 | `scripts/e2e-final.ps1` | **未执行**：同上 |

补充质量检查（本次额外跑的、超出 `check.ps1` 的项）：

- 20 个重建候选全部 `ast.parse` 通过；
- `ruff --select B018,RET503,PLW108,ARG002,F841,TRY300,PLR1714,SIM102,SIM103,B904,PIE790,PLR5501`：仅 5 处
  `ARG002`（协议要求但实现不用的 `mime_type`/`stage` 参数），无孤立表达式、无死代码；
- 重建文件内重复块检测：仅剩合法的 SQL/owner 校验惯用重复，无拼接重复；
- `docker compose -f infra/compose.yaml config -q` → exit 0（Compose 文件有效，不需要 daemon）；
- `uv run alembic heads` → 单一 head `0006_cleanup_intents`，`history` 为 0001→0006 线性链；
- `.probe/recover/check_orm_against_migrations.py` → 15 张映射表全部由迁移创建、列名一致；
- `.probe/recover/check_cleanup_row.py` → 手写的 `CleanupIntentRow` 与 `0006_cleanup_intents` 在 15 列、
  可空性、server default、2 个 check constraint 与 1 个索引上完全一致。

静态契约抽查（`docs/architecture/backend-recovery-after-flattening.md` Phase 4 清单）：

| 契约 | 证据 |
| --- | --- |
| 队列消息只带 stage / version / job | `application/dispatch.py:70` `dispatch_stage(*, stage, document_version_id, job_id)`；`infrastructure/job_queue.py` 的 `StageRunner` 同形 |
| 完成/失败写入被 claimed job 围栏 | `infrastructure/ingestion_store.py:954-955` `IngestionJobRow.id == job_id AND status == RUNNING` |
| cleanup 结算被 id + running + claimed attempt 围栏 | `infrastructure/cleanup_store.py:243-245` `id == intent_id AND status == RUNNING AND attempt == attempt`；租约重取在 109-135 |
| 产物键为 attempt 作用域 | `domain/parsing.py` `parsed_object_key(version_id, job_id)`、`domain/chunking.py` `chunks_object_key(version_id, job_id)`；`chunk_document_version` 校验 digest/size |
| `CancelledError` 重抛 | `agent_runtime/runner.py:171,326`、`application/retrieval.py:325,425`、`application/build_document_graph.py:115` |
| 检索是同一个操作 | `agent_runtime/graph.py:140` 与 `api/conversations.py:235` 都调 `RetrievalService.retrieve` |
| LangGraph 状态有界 | `agent_runtime/state.py` 的 `AgentState` 只有 `retrieval: RetrievalRecord \| None`，无 `records`/`merged_hits`/`fused_candidates`/`reranked_candidates` |
| 无 legacy checkpoint 迁移 | 全树只有 `agent_runtime/checkpointer.py` 的文档字符串提到 LangGraph 自有的 `checkpoint_migrations` 表 |
| 无 UI/UX 改动 | 本次会话写入仅限 `backend/src/**` 与新增报告；`frontend/`、`docs/ui-ux/` 未触碰 |

## 7. 残留风险与后续动作

1. **Gate D/E 未跑**：所有真容器行为（H1 围栏、cleanup 租约与幂等、检索融合、SSE 单终态、引用解析、图谱隔离）
   仍只有静态证据。当时计划文档的 Status 段落本来就写明
   “full acceptance run still outstanding”，本次恢复没有改变这一点，也**不能**宣称已改变。
2. **重建保真度**：`infrastructure/ingestion_store.py`（1181 行）来自“完整 read + 后续 edit”叠加，其中 5 条 edit
   未能命中（旧文本已被更早版本改动），这 5 处按调用方与文档契约手工对齐；`composition/resources.py` 与
   `application/document_ingestion.py` 同样有少量 edit 未命中，均已逐处核对。
3. **未验证的运行期事实**：`docs/research/probes/*` 中记录的探针结果均早于本次恢复，不能作为当前证据引用。
4. `.probe/recover/`（candidate 树、`tree-at-mid` 快照、`extract.mjs`/`install.mjs` 与四个一致性检查脚本
   `check_cleanup_row.py`、`check_orm_against_migrations.py`、`check_declared_imports.py`）为本次恢复的过程证据，
   `.probe/` 已 gitignore，未进入生产源码树；上一轮遗留的临时脚本 `scripts/recover-pi-read.ps1`
   已一并移入 `.probe/recover/`，`scripts/` 只剩正式检查/探针脚本。
