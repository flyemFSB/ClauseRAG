# ClauseRAG 架构与代码质量审查

> **历史审查说明（2026-10-12 更新）**：本报告记录的是 2026-10-06 当时代码库的审查基准（彼时采用 Qdrant、pg_trgm 与 Alembic 迁移）。
> 平台后续已完成技术演进：Dense 向量检索与 BM25 关键词检索已统一迁移至 ParadeDB（ADR-0034），Alembic 迁移已被 ORM 原生 schema-init 替代（ADR-0035）。
> 文中关于 Qdrant、pg_trgm 及历史迁移版本的讨论作为当时的基线记录保留。

**审查日期：** 2026-10-06  
**范围：** 当前工作树中的后端分层、摄取与队列状态、Alembic 历史、检索与引用、会话取消、前端缓存和模块内聚。  
**改动：** 本次只新增本报告，没有修改业务代码。工作树本身有大量未提交修改、删除及新增文件；下文指出“当前工作树”问题时不推断其由哪个提交或作者引入。

## 结论

整体架构**清楚但未达到生产级低耦合**。静态分层边界基本成立：`api → application → domain` 依赖方向检查通过；SQLAlchemy、Qdrant、S3、Taskiq、模型供应商均由基础设施适配；摄取任务有条件认领与有限重试；删除通过 PostgreSQL 清理意图和带租约的 worker 扫描实现了可靠的外部资源清理。Dense + Keyword + RRF 是目前代码的真实检索方案，移除 Graph 的方向与当前运行时代码一致。

主要缺口不是再添抽象层，而是几个模块之间的**运行时契约没有闭环**：数据库任务状态与 RabbitMQ 投递分别提交；某些阶段把任意异常记为可重试，但传输层只重投显式异常类型；worker 中断后的 `running` 任务没有回收；当前检索代码没有真正读取 ParentChunk；引用验证能校验 ID 归属，却不能保证结论必须带引用；取消/失败的部分回答还能进入后续提示历史。当前工作树还删除了历史 migration `0005`，使正好停在该 revision 的数据库无法由现有 Alembic 历史解析。

因此，当前实现适合继续迭代，但在**任务不丢、故障自动恢复、法律回答可追溯和迁移兼容**被真实验证前，不应仅凭静态检查通过宣称端到端可靠。

## 已验证

- `uv run ruff check backend/src`：通过。
- `uv run pyright backend/src`：0 errors、0 warnings、0 informations。
- `uv run python scripts/check-architecture.py`：通过，内部导入符合允许方向。
- `pnpm --dir frontend run check`：71 个文件格式通过；61 个文件无 lint/type errors。
- `pnpm --dir frontend run test`：4 个 test files、27 项测试通过。
- 当前 retrieval probe 已断言两条通道；`scripts/probes/retrieval.ps1` 仅概要仍称“三通道”。
- Alembic 当前 head 可解析为 `0011_drop_graph_channel`；直接查询已删除的 `0005_graph_build_runs` 得到 `CommandError: Can't locate revision identified by '0005_graph_build_runs'`。
- 未运行全量 E2E。当前机器的 Docker Desktop 不可用，且未配置 `RAG_DATABASE_URL`，不能验证真实 PostgreSQL 升级、RabbitMQ 重投、Qdrant/S3 清理故障路径。

## 高优先级发现

### F-01：数据库提交后的队列投递没有持久恢复通道（P1）

上传、手动解析重试和阶段推进会先持久化 `pending` job，再调用队列。`dispatch_committed_job()` 捕获 `JobDispatchError` 后只记日志并返回；`IngestionJobQueue._publish_appended_job()` 也捕获下一阶段投递失败并只记日志。worker 的周期扫描处理的是 cleanup intent，不会扫描并重发 `pending` ingestion job。于是 API/worker 在提交后、成功投递前遇到 RabbitMQ 故障时，数据库仍留有 `pending`，但没有消息驱动它；没有自动恢复或明确的运维重放入口。

证据：`backend/src/application/ingestion/dispatch.py:17-36`、`backend/src/application/knowledge/document_uploads.py:128-133`、`backend/src/application/knowledge/document_catalog.py:89-95`、`backend/src/infrastructure/queue/job_queue.py:145-158`、`backend/src/worker/main.py:47-55`。

**建议：** 给“已提交的 job 必须最终可投递”一个持久机制。优先在创建 job 的同一 PostgreSQL 事务写 outbox，由 worker/dispatcher 有界领取并重投；或者实现等价的 `pending` job reconciliation。保留至少一次投递语义，数据库条件认领负责幂等。不要以吞异常日志替代成功/失败状态。

### F-02：阶段失败分类与 Taskiq 重投条件不一致（P1）

`chunk`、`embed`、`index` 的通用 `except Exception` 分支把任意错误传给 `record_stage_failure(... retryable=True)`；在 `retry_available` 时数据库会将 job 重置为 `pending`，随后却重新抛出**原始异常**。Taskiq 只对 `_RETRYABLE_STAGE_ERRORS` 中列出的 `Transient*Error` 重投。比如 `ValueError`、未分类 SDK/数据库异常会使 job 已经回到 `pending`，但消息不会按同一策略重投；队列侧的注释也确认了未知异常会让 pending job 无消息可消费。解析阶段的通用异常分支采取了不同规则，这进一步说明重试决策没有单一一致的契约。

证据：`backend/src/application/ingestion/chunk.py:112-124`、`backend/src/application/ingestion/embed.py:100-112`、`backend/src/application/ingestion/index.py:91-103`、`backend/src/application/ingestion/failures.py:22-54`、`backend/src/infrastructure/queue/job_queue.py:37-47,206-224`。

**建议：** 让阶段在数据库终态决策和抛给 broker 的错误类别上保持一致：可重试的异常必须转换/抛出已注册的瞬态类型；未知异常应作为确定性失败落库，或进入明确的有限人工恢复状态。用真实队列 probe 覆盖每个阶段的瞬态、确定性和未知异常，断言 job 状态、attempt 数、消息重投次数和 DLQ 结果。

### F-03：worker 被杀后的 `running` job 不会被重新认领（P1）

`claim_job()` 只认领 `pending` 行；成功/失败结算也要求当前状态是 `running`。worker 在数据库认领后被强杀时，RabbitMQ 即使重新投递相同消息，数据库 claim 也会因 `running` 状态返回空；目前 ingestion 没有 lease/reaper 将过期运行任务重新排队。解析可以由用户手动 stale retry 另建 revision，但 chunk/embed/index 没有等价的通用自动恢复。清理流水线已实现 lease 和 attempt token，这个保证尚未覆盖 ingestion。

证据：`backend/src/infrastructure/ingestion/attempts.py:78-100,107-132`、`backend/src/infrastructure/db/stores/cleanup_store.py:66-91,215-227`、`backend/src/worker/main.py:47-55`、`backend/src/infrastructure/ingestion/revisions.py:72-109`。

**建议：** 为 ingestion job 增加有界 lease 回收，并用单次 attempt/claim token 围栏完成、失败和外部副作用。不能只重置同一行的 `running → pending`：旧 worker 若仍未退出，新的执行接管后旧执行可能看到相同 job ID 和 `running` 状态而结算成功。接受标准是 worker 在每阶段 claim 后被强杀、lease 到期后恢复，且旧 attempt 无法覆盖新 attempt 或推进两次。

### F-04：当前检索没有执行文档规定的 ParentChunk 上下文扩展（P1）

`SqlAlchemyChunkStore.load_records()` 只查询 `ChildChunkRow`；未读取或返回 `ParentChunkRow.content`。`select_context()` 按候选所属 parent 分组、排序，但 `CitationSource.content` 仍取 `candidate.record.content`，即命中的 child 文本。因此 `final_parent_limit` 限制的是 parent 分组数，并不代表生成上下文使用了 parent 内容。与项目合同“Child 负责召回/引用锚定、Parent 聚合完整标题与段落语义供生成上下文”不一致，可能让模型只看到命中的短 child 而缺少段落上下文。

证据：`backend/src/infrastructure/db/stores/chunk_store.py:84-139`、`backend/src/domain/citation.py:96-132`、`backend/src/application/retrieval/context.py:31-50`；目标约束见 `AGENTS.md` §3.4、`docs/architecture/retrieval-pipeline.md` §Parent expansion and budget。

**建议：** 检索操作按所选 parent 批量读取 parent 正文用于上下文，同时保留 child 的 line range 和 quote 作为引用锚点。需要将“生成上下文文本”和“权威 child citation”区分开，不能让 parent 文本成为引用原文。验收 probe 应断言上下文包含 parent 的 sibling 文义，而引用仍精确落在对应 child/行范围。

### F-05：Alembic 历史删除 `0005`，历史数据库状态存在不可解析窗口（P1，当前工作树）

当前工作树删除 `backend/migrations/versions/0005_graph_build_runs.py`，将 `0006_cleanup_intents.down_revision` 改成 `0004_conversations`，再由 `0011` 删除 Graph 表和阶段值。新数据库和当前 head 的历史可解析；但数据库若正好 stamped 在 `0005_graph_build_runs`，当前 Alembic `ScriptDirectory` 找不到该 revision，因此不能从它正常升级。`0011` 的 downgrade 也只恢复 stage check 值，不恢复被删除的表或 job 数据；这是有损回滚，不应被误认为可逆迁移。

证据：`backend/migrations/versions/0006_cleanup_intents.py:24-26`、`backend/migrations/versions/0011_drop_graph_channel.py:40-63`；删除文件 `backend/migrations/versions/0005_graph_build_runs.py`。当前对该 revision 的查询已实际返回 `Can't locate revision`。

**建议：** 部署前盘点所有数据库的 `alembic_version`。对正好位于 `0005` 的数据库，选择并记录显式迁移路径（恢复历史 revision 并以新 head 删除，或经过备份验证的 history-squash/人工 stamp 流程）；不要静默要求运维手工重标。为 fresh、`0004`、`0005`、`0010` 各状态准备真实 PostgreSQL 升级探针及备份/回滚步骤。`0001_phase1_schema.py` 的工作树差异经核对只有说明文字删除，stage schema 值和 DDL 未变，不应把它误报为 schema 被重写。

### F-06：引用校验不保证回答的结论确实带有可追溯引用（P1）

`validate_answer()` 只枚举模型输出的 `[S#]`，检查每个 ID 是否属于本次 sources，并按配置拒绝/移除未知 ID。没有任何逻辑要求 grounded answer 至少引用一个 source，也没有对结论与引用证据的支持关系做校验；系统提示词中的“引用资料时应标记”不是后端不变量。因此答案可以通过证据门控、完全不输出引用，却仍被作为 completed 回答持久化。它满足“引用 ID 不虚构”，不满足“每句审查结论都有可查验依据”的产品目标。

证据：`backend/src/domain/citation.py:138-170`、`backend/src/application/retrieval/citations.py:51-116`、`backend/src/agent_runtime/graph.py:135-148`、`backend/src/application/agent/answer.py:20-40`。

**建议：** 明确当前可实现的保证边界：至少要求 grounded answer 中每个事实性句段有合法引用，或将无引用回答降为拒答/显式未验证状态；构建真实合同样例的端到端 probe 检查缺引用、无效 ID、引用到无关 child、删除中来源失效。语义蕴含无法由 ID 检查证明，必须作为独立评测指标和残余风险记录，不能以“引用已校验”暗示已证明结论正确。

### F-07：上传文档内容直接拼入 system prompt，缺少不可信数据边界（P1）

`stream_grounded()` 将检索上下文用 `.format(context=context)` 插入 system prompt；source content 来自用户上传的文档。提示规则只说“只依据资料”，没有告诉模型资料中的指令是被引用的数据、不是系统/开发指令，也没有协议层隔离。恶意合同附件可包含面向模型的指令文本，诱导偏离回答目标或泄露提示内容。这是提示注入风险，不是单靠引用 ID 校验可以阻止的。

证据：`backend/src/application/agent/answer.py:20-40,67-73`、`backend/src/domain/citation.py:72-84`。

**建议：** 将用户/文档文本明确按不可信数据边界组装，避免把其伪装成与策略同级的 system 指令；限制系统提示中可变段落的格式和职责。用真实 agent probe 上传包含“忽略上方指令”等内容的文档，验证拒绝执行该指令、仍能引用原文、不得泄露 system prompt。提示防护不能被描述为形式化安全边界。

## 中优先级发现

### F-08：失败或取消的部分回答会成为未来轮次的模型历史（P2）

runner 在取消和异常时把尚未经过 citation validation 的 `answer` 持久化为 `CANCELLED`/`FAILED`。历史 SQL 只排除 `STREAMING` 和空内容，没有限制为 `COMPLETED`，所以这些部分输出会被 `ConversationAgent` 后续轮次读出并拼入模型上下文；其中可能含未删掉的 `[S999]`、source block 或不完整/错误断言。前端的 generation fence 只能阻止旧请求改写新 UI，不能隔离 PostgreSQL 中已经保存的部分回答。

证据：`backend/src/agent_runtime/runner.py:151-156,281-289,306-323`、`backend/src/infrastructure/db/stores/conversation_store.py:122-143`、`backend/src/agent_runtime/graph.py:31-39`。

**建议：** 明确失败/取消回答是否属于会话记忆。建议后续模型历史只包含已完成且适合再利用的轮次；若产品要保留部分输出供 UI 查看，将展示记录与 prompt history 区分。probe 覆盖在生成中途、引用校验前、引用校验后分别取消，再发起新提问并断言历史输入内容。

### F-09：上下文 token 预算低估实际发送内容（P2）

预算仅累加 child `record.token_count`，而模型实际收到的 context 还包含 source block、文档名、标题路径、分隔标签；此外检索预算并未把对话历史、system prompt 和当前问题纳入同一模型上下文预算。故 `max_context_tokens` 不是实际 prompt token 上限，长标题/多来源/较长历史时会超过预期窗口。

证据：`backend/src/domain/citation.py:72-84,96-132`、`backend/src/application/retrieval/context.py:39-50`、`backend/src/application/agent/answer.py:20-40,67-73`。

**建议：** 将实际渲染后的上下文计入预算，另为 system/history/question 留出模型窗口余量；探针用长标题、多 parent 与最大历史组合验证最终 prompt token 上限。无需先引入预算框架，先把可测量的 prompt 输入总量定义清楚。

### F-10：知识库 mutation hooks 未维护 TanStack Query 缓存（P2）

创建、更新、删除知识库的 hooks 只调用 `useMutation`，没有 `queryClient` 写缓存或失效 `['knowledge-bases']`。`KnowledgeBaseOverview` 只对当前文档查询手动 `refetch()`；创建时把新 ID 设为选中，但列表数据仍旧，删除或重命名也可能让其它视图/缓存继续显示旧值。文档上传/删除也采用组件级手动 `refetch()`，其他已挂载的查询不一定同步。

证据：`frontend/src/features/knowledge-bases/api.ts:64-122`、`frontend/src/features/documents/api.ts:347-370`、`frontend/src/features/knowledge-bases/KnowledgeBaseOverview.tsx:230-261,295-307`。

**建议：** 在 feature 的 mutation 边界统一更新/失效受影响 query key，包括列表、对应知识库文档目录和被删除资源详情；UI 继续把 Query cache 作为服务端事实源。增加针对创建、重命名、删除和文档 mutation 的现有前端测试，不在页面事件处理器散落补丁式刷新。

### F-11：未使用的 Redis 仍是 readiness 必需依赖（P2）

目前业务代码未发现 Redis 消费者，但 `open_health()` 将 `RedisProbe` 作为强制 readiness probe；`HealthService` 把任一 probe 失败都变成整体 unavailable。Redis 无业务用途时，其停机仍可导致服务 readiness 503。

证据：`backend/src/composition/shared/health.py:20-31`、`backend/src/application/shared/health.py:35-64`、`backend/src/api/health.py:42-57`。Redis 的运行时使用搜索未发现消费者；配置与探针仍存在。

**建议：** 若 Redis 没有近期确定的业务职责，删除 Redis 配置、服务依赖和 readiness 探针；若确实需要，就明确 cache/lock/rate-limit 的所有者和可降级合同后再保留。不要让“预留用途”成为部署硬依赖。

### F-12：两个前端代码文件违反项目 500 行上限，且职责明显聚集（P2）

当前工作树 `KnowledgeBaseOverview.tsx` 为 1,365 行，混合知识库选择/CRUD、文档目录、过滤、批量重试/删除、上传 queue、确认框和多个 dialogs；`RetrievalDebugPage.tsx` 为 617 行，混合查询输入、诊断投影和各报告面板。项目 `AGENTS.md` 要求单个代码文件不超过 500 行（架构文档与生成代码除外），这是明确规范违例，而不只是风格建议。

证据：`frontend/src/features/knowledge-bases/KnowledgeBaseOverview.tsx:1-1365`、`frontend/src/features/retrieval-debug/RetrievalDebugPage.tsx:1-617`；规范见 `AGENTS.md` §2.2。

**建议：** 按用户任务和变化原因拆分：knowledge-base management、document table/bulk actions、upload queue/dialog；retrieval-debug query form、channel report、fusion/rerank/evidence panels。让数据获取与 mutation 留在既有 feature API hooks，避免把文件拆成只转发 props 的薄壳。每一阶段保持界面行为和已有 27 项测试。

### F-13：死代码和阶段枚举制造了并不存在的能力（P2/P3）

当前 backend、frontend 和 scripts/probes 源码引用搜索确认：`DocumentCatalog._discard_upload()` 只有定义；`domain.knowledge.DeletedDocument` 只有定义；`ChannelStatus.UNAVAILABLE` 只被未调用的 `ChannelResult.unavailable()` factory 自身赋值，没有生产调用方；`WorkerRuntime.chat` 在 worker runtime 中仅被构造/关闭，不参与 worker 工作。`IngestionStage.NORMALIZE` 仍在领域枚举和 migration check constraint，但 `ALL_INGESTION_STAGES`、`run_stage()` 和 CLI 可执行 stage 均没有 normalize handler。

证据：`backend/src/application/knowledge/document_catalog.py:183-204`、`backend/src/domain/knowledge.py:32-39,158-163`、`backend/src/domain/retrieval.py:27-35,86-95`、`backend/src/composition/worker/runtime.py:35-67`、`backend/src/composition/worker/ingestion.py:25-32`。

**建议：** 删除已证实死代码/未用资源。对 `NORMALIZE` 做明确决策：若规范化永久属于 parse 的内部步骤，从领域枚举与新 schema 可接受值移除，并提供兼容 migration；若它是独立阶段，则补齐持久 job、claim、运行与 UI 合同。不要保留仅用于“以后可能会有”的状态值。

### F-14：活跃架构文档仍描述 Graph/三通道（P2）

当前实现与 `ADR-0029` 都确认只有 Dense + Keyword；retrieval probe 也断言 `channels.Count -eq 2`。但 `DESIGN.md` 仍把 Graph 写成目标通道，`docs/architecture/data-flow.md` 仍列 `GraphBuildRun`，`frontend-contract.md` 仍列 graph 字段与 0.8 权重，检索 probe synopsis 仍称三通道，knowledge-base 页面说明仍写“三通道检索配置”。这会导致后续实现/验收重新沿着已撤销设计开发。历史 ADR 中的旧决定可保留，但必须由 withdrawn 状态和新 ADR 明确覆盖；不应让活跃规范保持旧值。

证据：`DESIGN.md:48,174,202,367`、`docs/architecture/data-flow.md:14`、`docs/architecture/frontend-contract.md:105,238-247`、`scripts/probes/retrieval.ps1:3,371-372`、`frontend/src/features/knowledge-bases/KnowledgeBaseOverview.tsx:398`、`docs/adr/README.md:1231-1268`。

**建议：** 以 ADR-0029 为唯一当前决策源，更新活跃架构图、wire contract、开发指南和 UI 文案；保留历史 ADR 正文作为决策历史，但在顶部标注 superseded/withdrawn，不要做全仓机械删除 `graph` 字符串。

## 架构评价

| 维度 | 评价 | 依据 |
|---|---|---|
| 分层与导入方向 | 良好 | 架构检查通过；domain 模块未见 FastAPI/ORM/供应商依赖泄漏。 |
| 外部系统隔离 | 良好 | PostgreSQL、Qdrant、S3、HTTP providers、Taskiq 分别有适配器；外部 I/O 大多有超时和错误分类。 |
| 应用用例内聚 | 中上 | `RetrievalService.retrieve()` 维持完整检索用例，`DocumentCatalog`/`DocumentIngestion` 等有明确业务入口。 |
| 摄取可靠性 | 不足 | 传输与数据库状态缺 outbox/reconciliation；重试类型不一致；crash recovery 缺失。 |
| RAG 契约 | 不足 | Parent 未参与上下文；引用 ID 校验不等于引用完整性/论据支持；提示注入边界不足。 |
| 持久化内聚 | 可接受但需守边界 | `SqlAlchemyIngestionStore` 429 行，集中管理摄取生命周期多个阶段；低于 500 行上限，且共享条件写入是不变量。不要按阶段机械拆文件；优先把 delivery/recovery 的独立生命周期做清楚。 |
| 前端职责 | 需重构 | 两个文件超过硬性行数上限；Query mutation 缓存更新分散且不完整。 |
| 清理与删除 | 较好 | 业务删除与 cleanup intent 同事务提交；清理具备 lease、attempt token、幂等外部删除和有限重试。真实容器失败路径仍应持续探针验证。 |

## 分阶段整改计划

### Phase 0：迁移与上线状态盘点

1. 列出现有数据库的 `alembic_version`，确认是否存在 `0005_graph_build_runs` 或其它历史分支状态。
2. 为 fresh、`0004`、`0005`、`0010` 数据库各执行升级探针；为 `0011` 的删除数据行为保存明确备份与回滚说明。
3. 解决历史 revision 缺失后再合并/部署 Graph 删除迁移。

**门禁：** 所有已知数据库状态可升级到同一 head；无法自动迁移的状态有验证过、可重复、能审计的运维步骤；不依赖“应该没有数据库 stamped 在 0005”。

### Phase 1：摄取任务至少一次且可恢复

1. 给已提交 job 增加持久投递/重放机制（优先 transactional outbox）。
2. 统一阶段异常分类与 Taskiq retry whitelist，未知异常不得出现“数据库 pending、消息终止”的分裂状态。
3. 增加 ingestion lease 回收与 attempt fencing；每次恢复都证明旧 worker 无法覆盖新 attempt。
4. 在 `backend/src/infrastructure/ingestion/store.py` 保持事务短小，将 job claim/recovery 生命周期与 stage-specific artifact commit 的职责按实际变化边界评估，不按文件对称拆解。

**门禁：** 用真实 PostgreSQL + RabbitMQ 探针覆盖“提交后 broker 不可用、消息已发布但 worker 被杀、DB claim 后进程被杀、瞬态/确定性/未分类异常、重复投递、下一阶段发布失败”。每个场景断言数据库终态、消息与 DLQ；没有永久 `pending`/`running` 遗留。

### Phase 2：恢复 Parent-Child 与引用可信边界

1. retrieval hydration 在一次批量数据库操作中读取选中 parent 内容和 child 权威锚点。
2. 分离 prompt context 与 citation source：parent 文本用于生成，child quote/line range 用于引用回查。
3. 将实际渲染 prompt 纳入 token 预算，并为 history、question、system instructions 留出额度。
4. 为用户上传文本建立明确的不可信数据处理合同。
5. 把“合法引用 ID”“每个事实结论有引用”“引用证据支持结论”分成不同可验证指标；语义支持使用评测，不将 ID 校验包装成蕴含证明。

**门禁：** 真实合同 probe 覆盖 parent sibling 上下文、child 行号/原文精确一致、无引用回答、未知 ID、引用源被删除、长上下文截断和恶意 prompt 文本；Dense+Keyword 与 RRF 行为保持稳定。

### Phase 3：对话历史与前端服务端状态

1. 把 completed 的对话记忆与 canceled/failed 的展示记录分开，验证后续轮次只使用批准状态的消息。
2. 对生成途中、引用校验中和最终持久化前取消分别执行 agent probe；检查部分输出是否可以被下一轮复用。
3. 在 feature mutation hooks 中更新/失效 knowledge-base/document 相关 Query keys，移除页面级补偿性 refetch。
4. 按知识库管理、文档批量操作、上传队列、检索诊断面板拆解超过 500 行的组件。

**门禁：** 前端 `vp check` 与 tests 通过；新增测试覆盖 mutation 后多视图缓存一致性、切换知识库、重试/删除后状态刷新、卸载/重提问代际隔离；后端 agent probe 确认取消语义。

### Phase 4：删除假状态、同步规范与收口

1. 删除确认未使用的 `_discard_upload`、`DeletedDocument`、`UNAVAILABLE` factory 和 worker 中未使用的 chat client。
2. 决定 `NORMALIZE` 阶段是正式能力还是 parse 内部步骤，并更新 schema/domain/API/UI。
3. 移除未使用 Redis readiness 依赖，或先给 Redis 一个被业务明确拥有、带降级合同的职责。
4. 更新活跃文档中的 Graph/三通道描述，历史 ADR 保留并清晰标注失效状态。

**门禁：** 生产代码搜索无未引用删除候选；架构检查、静态检查、迁移 probe、retrieval/agent/queue/cleanup 专项容器 probes 通过；最终系统闭环后再执行一次 `scripts/e2e-final.ps1` 并在 `dist/verify/` 产出正式工件。

## 当前残余风险与归因边界

- 本报告不把未提交变更归因给特定功能分支：`git status --short` 显示大量用户修改、删除及未跟踪文件，且没有干净基线可比较。
- `0005` 缺失、Graph 下线及活跃文档漂移属于当前工作树可直接复现/检查的事实；上线风险是否触发取决于真实数据库 revision 与部署历史。
- Taskiq 重试默认/异常匹配语义已从当前 `.venv` 安装源码检查；真实 RabbitMQ DLQ 与进程终止时序未在本轮容器中验证。
- 前端静态和 27 项测试通过，不等于 mutation 缓存一致性、宽屏/移动端交互或浏览器取消行为已经端到端验收。
- 本轮没有运行任何全量 E2E，也没有修改/补写浅层单元测试；执行策略符合项目的开发期验证约束。
