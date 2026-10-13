# AGENTS.md — ClauseRAG 智能体开发指南与工程契约

> 本文件是所有在当前代码库中工作的 AI Agent（智能体编码助手）的**最高行动指令与工程契约**。  
> 在阅读项目、理解需求、方案设计、代码编写与测试验证全流程中，**必须无条件严格遵守本指南中的所有原则与约束**。

---

## 1. 核心使命与架构背景

你正在为 **ClauseRAG** 开发核心系统代码。ClauseRAG 是一套面向高可信美国商业合同审查与法务知识检索的生产级 Agentic RAG 平台。系统的核心创意北极星是**「可追溯的记录」（The Traceable Record）**——每一句审查结论与回答必须拥有可查验的权威合同条款坐标（文档、版本、行号、页码与后端校验的原文）。

在修改或新增任何代码前，请确保已查阅：
- `README.md`：项目全景、系统拓扑与快速开始。
- `DESIGN.md`：Google 标准架构设计白皮书与详细子系统规范。
- `docs/architecture/system-overview.md`：系统架构分层与依赖方向。
- `docs/architecture/retrieval-pipeline.md`：三通道召回、RRF 与重排流水线。
- `docs/architecture/citation-protocol.md`：端到端引用防伪协议。

---

## 2. 核心开发规范（十二大不可违抗铁律）

在编写、重构或审查代码时，以下十二条准则具有最高优先级：

### 1. 架构与领域优先
计划阶段应以理想架构为目标，明确业务目标、领域边界、模块职责、依赖方向和数据流，形成符合领域规律、面向长期维护且可持续演进的设计后再进入编码；不得以短期实现便利牺牲整体设计。设计必须完整，实现应当克制：不做推测性抽象，抽象延迟到第二个真实用例出现时才引入，单一场景直接实现。

### 2. 追求优雅的代码模块
模块应高内聚、低耦合，通过精简且稳定的接口封装内部复杂度，使职责、命名、依赖和扩展方式清晰自然；业务代码按单一职责拆分，单个代码文件不得超过 500 行（架构设计文档与工具自动生成的迁移/类型代码不受此限），接近上限时应优先重构模块边界。

### 3. 保持边界与数据流清晰
协议模型、领域模型、持久化模型和视图模型不得相互泄漏；数据必须在边界处完成校验和独立转换，避免跨层共享可变状态。

### 4. 安全与隔离默认开启
所有功能均按多租户、多用户场景设计，明确认证、授权和数据隔离边界；遵循最小权限原则，任何外部输入均视为不可信，敏感信息不得进入代码、日志或响应。

### 5. 面向并发与故障设计
后端应主动考虑幂等性、竞态、事务边界、超时、取消、重试、背压和资源释放；不得通过无边界重试、吞错或隐式共享状态掩盖问题。

### 6. 保障完整前端体验
前端应控制渲染成本、异步状态和并发请求，保持清晰的 UI 结构；用户流程必须覆盖加载、空状态、错误、重试、反馈和可访问性。

### 7. 复用稳定的业务语义
优先复用已有模块和能力，但不要仅因代码外形相似而过早抽象；确需重复时，必须注释说明其独立演进或暂不抽象的原因。新增依赖前先核查项目已有依赖（后端 `pyproject.toml` 与前端 `web/package.json`）能否满足需求，不得臆断已有库缺少功能——先查阅文档和类型定义；确需引入时优先成熟且维护良好的库，不重复实现通用功能。

### 8. 为未来维护者保留上下文
代码、注释、测试和架构文档是跨越时间的协作媒介。非显然的设计决策、兼容约束、已知缺陷和临时方案，必须记录原因、影响范围、潜在风险及移除条件；技术债务应关联可追踪任务，涉及难逆转、非显然且有实质权衡的关键架构决策必须归档至 `docs/adr/`，禁止留下缺少工单号或 Issue 绑定的裸 `TODO`（格式强制为 `TODO(#ticket):`）。

### 9. 确保变更可验证、可观测、可回滚
每项改动都应行为可测试、运行状态可观测、故障可定位，并兼顾向后兼容和回滚路径；错误与日志必须保留诊断上下文，但不得泄露敏感信息。

### 10. 删除优于兼容
内部路径重构时直接删除过时实现，禁止新增兼容层、deprecated shim 或长期兼容双写；对外契约（`/api/*` 等稳定接口）按协议契约单独评估。严禁为了迁就旧实现而保留长期双写；因数据库平滑迁移或滚动发布所必需的临时迁移双写，必须在代码处注明移除条件（格式为 `ponytail: migration until M<X>` 并挂载清理工单），到期必须硬删除。

### 11. 运行时验收是唯一业务测试机制
永远不要在编写代码后补写浅层单元测试冒充验证，也不要用静态检查通过代替"系统真的跑起来了"：业务正确性的唯一证据是容器路径（`docker compose --profile app up -d --build --wait`）以及 nginx 入口上的真实响应与一次真实问答。前端已有 4 个 `*.test.ts` 属纯逻辑测试，继续维护，但不为了覆盖率新增测试。

### 12. 第一性原理与原生优先
始终基于第一性原理展开独立思考与批判性推演，直击业务与技术本质，不盲从惯性经验或表象报告；编码实现前，必须深入调研所涉技术栈的最新官方文档与推荐实践，查明框架设计哲学与原生解法；实现时全面贯彻 Ponytail（高效极简开发）阶梯——遵循标准库、平台原生机制、已有依赖内建能力的递进顺序，最大限度采用依赖原生 API 与内置能力，严禁重复造轮子或过度封装，以最短、最克制、最鲁棒的路径达成最简最佳实践（最优质的代码是无需编写的代码）。

---

## 3. 技术栈硬性执行规范

### 3.1 后端技术规范 (Python & Backend)
- **语言与版本**：强制使用 Python 3.12 (`>=3.12,<3.13`)，依赖管理以 `uv.lock` 为绝对权威。
- **类型系统与规范**：遵循 PEP 8 与 Pythonic 风格，全量代码必须通过 `ruff check`、`ruff format` 以及 Strict 模式下的 `pyright`（**0 errors, 0 warnings**）。
- **异步安全与会话管理**：
  - 严禁跨并发任务共享同一个 SQLAlchemy `AsyncSession`；
  - 严格保护取消链，**绝对禁止吞没 `asyncio.CancelledError`**；
  - 所有外部 I/O（HTTP 请求、模型服务、消息分发、S3 操作）必须设置**显式有界超时**，禁止无限等待；
  - 重试必须有限度，且仅针对已分类的瞬态失败（如网络超时、503 临时不可用），禁止对确定性业务错误（如 400、422）重试。
- **状态与消息队列**：
  - PostgreSQL 是系统唯一的事实真相来源（Single Source of Truth）；
  - RabbitMQ 是平台**唯一的业务异步队列**；Taskiq 承担消费与执行；
  - Redis 仅用于临时缓存、分布式锁与速率限制，**严禁作为队列使用**。

### 3.2 架构分层与依赖方向 (Layering & Imports)
- **严格依赖顺序**：
  $$\text{api} \longrightarrow \text{application} \longrightarrow \text{domain}$$
- `domain` 严禁导入 FastAPI、SQLAlchemy、pgvector、ParadeDB、LangChain、RabbitMQ 或 S3 等任何外部依赖；
- `infrastructure` 实现 `application` 与 `domain` 定义的端口协议；
- `worker` 仅能通过调用 `application` 层的用例服务来执行业务逻辑，严禁在 Worker 中复制或重写领域规则；
- `composition` 负责各进程具体实例的依赖注入组装；
- **禁止垃圾模块名**：禁止创建名为 `utils`、`helpers`、`common`、`misc`、`manager` 等无清晰边界的垃圾文件；架构脚本 `scripts/check-architecture.py` 会在 CI 中硬性检查并拦截。

### 3.3 前端技术规范 (Frontend & UI)
- **环境标准**：基于 Vite+ `vp` CLI、React 19、Node 24、pnpm 12。
- **架构范式**：按特性划分目录（Feature-First）；服务端异步状态全权交由 **TanStack Query** 接管，禁止将服务端状态与本地状态手动双写同步。
- **状态完整性**：所有涉及异步数据的视图必须完备处理：
  1. `loading`（骨架屏/加载指示器）
  2. `empty`（精炼友好的空状态说明）
  3. `error`（明确错误归因与可执行的恢复动作）
  4. `retry`（重试能力）
  5. `cancellation`（请求中止感知与清理）
- **并发与竞态防护**：网络请求层强制使用**代际栅栏（Generation Fence）**；当用户重新提问、切换检索范围或离开页面时，必须中止在途请求并推进代次，杜绝过时响应写回新状态。
- **视觉契约**：严格遵循 `DESIGN.md` 中定义的视觉规范（中性灰阶、等宽数字 `tabular-nums`、对比度 $\ge 4.5:1$、Popover 权威溯源交互）。

### 3.4 RAG 检索与生成核心规范 (RAG Correctness)
- **存储就地隔离**：业务切片向量存于 PostgreSQL `child_chunk_embeddings` 表（pgvector 原生 `vector` 列 + HNSW cosine 索引），与业务事实同库同事务；不得把向量写回任何独立向量服务，也不得与派生索引/观测数据共用同一张表。
- **双通道与 RRF 融合**：由应用层显式执行 Reciprocal Rank Fusion（$k=60$），统一对齐 pgvector（Dense）与 pg_search BM25（Keyword）候选结果；两类分数量纲不可比，只融合名次，不得直接相加。
- **Parent-Child 双层锚定**：
  - Child Chunks 仅用于检索匹配与 Citation 坐标锚定；
  - Parent Chunks 聚合完整标题与段落语义，仅用于拼装大模型生成的回答上下文。
- **权威引用校验**：后端必须校验大模型输出的每一个引用标记（如 `[S1]`），严格对照本次门控通过的候选切片，解析权威对象存储中的真实行号区间与原文，严禁透传虚构引用。
- **写入门控在数据库内比对**：向量写入必须与状态写入在同一事实源上比对 job、attempt 与租约；不得只在收尾状态写入时检查（事后检查挡不住一个租约已过期、却比新尝试更早提交向量的旧任务）。

---

## 4. 交付验证与工作流要求

1. **验证只有两个层次，没有第三层**：静态门禁回答"代码是否自洽"，容器路径回答"系统是否真的跑起来"。后者是唯一的运行时证据：平台不再有探针脚本套件（已于本次交付删除），任何"跑通了"的说法都必须指向下面第 2 或第 3 条的实际输出。
2. **静态门禁（每次改动后必须 100% 通过）**：
   ```bash
   uv sync --locked --group eval   # 依赖锁定同步
   uv run ruff check backend/src
   uv run ruff format --check backend/src
   uv run pyright backend/src      # Strict 模式
   uv run python -c "import api.main, agent_runtime.main, worker.main, cli.main"
   uv run python scripts/check-architecture.py
   uv run python scripts/build-goldenset.py --verify
   pnpm --dir frontend run check
   pnpm --dir frontend run test
   ```
3. **运行时验收（全栈唯一入口）**：
   ```bash
   docker compose --profile app up -d --build --wait
   ```
   它一次性做完：构建后端/前端镜像、跑一次性 `schema-init` 从模型建模、起 API/agent/worker/web 四个服务
   并等它们 healthy；随后通过 nginx 单一入口核对真实行为：
   ```bash
   curl -fsS http://localhost:5173/health/ready      # 逐依赖就绪（503 表示依赖不可用）
   curl -fsS http://localhost:5173/api/v1/config     # 本进程实际生效的配置
   ```
   验收结论以这些响应的原文为准；需要人看的检查（引用是否指向真实条款、SSE 是否逐帧到达）在浏览器里用真实文档做一遍，不允许用“静态检查通过”替代。
4. **本地开发循环**（改代码看效果，不重建镜像）：容器只跑依赖，三个进程与前端跑在宿主上。
   ```bash
   docker compose up -d --wait            # 只起基础设施
   uv run python -m cli schema-init                             # 首次或改了模型后
   uv run python -m cli storage-init
   uv run python -m api.main & uv run python -m agent_runtime.main & uv run python -m worker.main &
   pnpm --dir frontend run dev
   ```
   改了模型结构时用 `uv run python -m cli schema-reset`（破坏性：先删表再建表，现有数据会全部丢失）。
5. **禁止 Windows 专用资产**：最终部署目标是 Debian 服务器，仓库不保留 `.ps1`/`.bat`/`.cmd` 之类的
   平台绑定脚本；自动化要么进 `docker compose`，要么是可移植的 Python/Shell。
6. **Git 提交信息规范**：遵循 Conventional Commits（`feat:`, `fix:`, `refactor:`, `test:`, `docs:`），提交说明必须详实陈述改动原因、设计考虑与验证结果。
