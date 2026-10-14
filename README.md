# ClauseRAG — 生产级商务合同审查与法务知识检索 Agentic RAG 平台

<div align="center">

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-FF9900?logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-HNSW-4169E1?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![ParadeDB](https://img.shields.io/badge/ParadeDB-pg__search%20BM25-1D4ED8)](https://www.paradedb.com/)
[![Redis](https://img.shields.io/badge/Redis-8.x-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-4.x-FF6600?logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite+](https://img.shields.io/badge/Vite%2B-vp-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Ruff](https://img.shields.io/badge/Ruff-Checked-261230?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![Pyright](https://img.shields.io/badge/Pyright-Strict%200%20errors-blue)](https://github.com/microsoft/pyright)

<p align="center">
  <b>核心理念：「可追溯的记录」（The Traceable Record）—— 言必有据，行必有踪。</b>
</p>

<p align="center">
  专为高可信商务合同审查、合规尽调与法务知识检索打造的端到端 Agentic RAG 平台。<br/>
  每一句审查结论均严格锚定权威合同条款的版本、章节、物理行号与后端强校验原文，杜绝模型幻觉。
</p>

[业务定位](#-业务定位与设计哲学) •
[功能特性](#-功能特性) •
[系统拓扑](#-系统拓扑与架构) •
[核心技术机制](#-核心技术机制) •
[技术栈选型](#-技术栈选型矩阵) •
[快速开始](#-快速开始) •
[质量门禁](#-工程质量门禁与验证) •
[项目结构](#-项目目录结构) •
[免责声明](#-免责声明)

</div>

---

## 🎯 业务定位与设计哲学

### 为什么选择 ClauseRAG？
在复杂的商业活动中，商业合同（如主服务协议 MSA、保密协议 NDA、SaaS 许可、采购供应协议、战略合作协议、雇佣协议等）是企业权利与义务的基石。通用问答 RAG 平台面对法律与商业合同审查时存在三大致命痛点：
1. **幻觉难以溯源**：模型生成的审查建议看似言之凿凿，实际无法精确对应到合同具体版本、条款层级与起止物理行号；
2. **术语检索失真**：通用向量检索擅长模糊意图，但对合同特有编号、定义词条款（Definitions）、交叉引用（Cross-references）缺乏精确字面匹配能力；
3. **证据不足强行作答**：缺乏置信度门控机制，在证据召回不充分或不相干时编造合规结论，带来极高商业风险与法务隐患。

**ClauseRAG** 围绕**高确定性、强证据约束与防伪追溯**展开设计：
- **通用商事协议支持**：支持各类企业商事合同与法律协议文档的解析、分块索引与审查，从结构化条款到非结构化扫描件全链路覆盖；
- **真实基准评测保证**：内置基于业界公开权威商事合同基准（CUAD，Contract Understanding Atticus Dataset）构建的黄金评测集（Goldenset），确立可复现的多类别合同审查与引用定位评估基线；
- **Parent-Child 树状双层分块**：Child 块负责精确检索与行级锚定，Parent 块负责富语义提示词拼接；
- **Dense + Keyword 双通道与 RRF 融合**：PostgreSQL 18 内原生 pgvector HNSW 密集向量与 ParadeDB `pg_search` BM25 词项检索互补，同库同事务，由应用层执行确定性倒数排名融合（RRF）与交叉重排；
- **动态证据门控（Evidence Gate）**：基于重排质量判定证据充分度，支持有界查询重写；证据不足时主动弃答（Abstain）；
- **三层引用防伪协议（Citation Protocol）**：提示词防伪隔离、服务端证据集闭环校验、对象存储权威物理行号映射；
- **工业级双工作区体验**：无缝切换“沉浸式合同审查工作区”与“SaaS 级法务资产与流水线控制台”。

---

## 🌟 功能特性

- **多格式合同解析与 OCR**：
  - 支持 `.pdf`、`.docx`、`.pptx`、`.xlsx`、`.html`、`.txt`、`.md` 及主流图像格式；
  - 自动路由：Office/PDF 文档走 AnyDoc 结构化抽取，扫描件与图像无缝升级至 PaddleOCR-VL 进行版面分析与文字识别。
- **混合检索与深度重排**：
  - **Dense 向量通道**：SiliconFlow `BAAI/bge-m3`（1024 维密集向量）+ PostgreSQL 18 `child_chunk_embeddings` 的 pgvector HNSW cosine 索引；
  - **Keyword 关键词通道**：ParadeDB `pg_search` BM25 索引，保障合同定义、法条编号、大写专有名词与 CJK 短词的精确召回；
  - **应用层 RRF 融合**：Reciprocal Rank Fusion（$k=60$）统一无量纲融合双通道候选集；
  - **Cross-Encoder 交叉注意力重排**：SiliconFlow `BAAI/bge-reranker-v2-m3` 深度计算语义相关性。
- **有界图状态机与证据门控**：
  - 基于 LangGraph 构建有界 Agent 图状态机，严控循环上限（最多 2 轮检索重写）；
  - 证据状态划分为 `sufficient`（充分）、`degraded`（降级）、`insufficient`（不足）；
  - 证据不足时触发主动弃答流程，返回标准说明并提示补全文档，坚决不瞎猜。
- **端到端可追溯引用**：
  - 模型生成阶段输出局部标记（如 `[S1]`）；
  - 后端实时校验引用合法性，剔除虚构标记，解析并回查数据库与对象存储；
  - 前端提供浮动 Popover 溯源气泡与侧边栏权威证据原文比对面板（精确展示行号、段落与文档版本）。
- **企业级缓存与限流防护**：
  - 集成 Redis 8 承载 API 速率限制（429 Too Many Requests），防止高频突发流量打垮模型与数据库服务；
  - 跨进程分布式互斥锁保障长周期关键任务幂等性；
  - 单轮检索诊断调试结果支持 TTL 智能缓存。
- **双工作区工业级前端**：
  - **合同审查工作区 (`/chat`)**：极简审查工作台、流式打字机渲染、多轮对话记忆、代际栅栏（Generation Fence）阻断旧响应写回；
  - **资产控制台 (`/admin/*`)**：知识库概览、文档物理版本演进、摄取流水线任务看板（认领、租约与重试状态机监控）、单轮检索诊断调试（Retrieval Debug）及系统配置面板。

---

## 🏗️ 系统拓扑与架构

系统严格遵循领域驱动设计（DDD）与洋葱架构（Clean Architecture）规范，依赖方向单向向内：  
$$\text{api} \longrightarrow \text{application} \longrightarrow \text{domain}$$  
由 `infrastructure` 实现外部适配器，由 `composition` 负责各进程的依赖注入装配。

```text
                               ┌────────────────────────────────────────────────────────┐
                               │             前端应用 (React 19 + Vite+)                │
                               │        合同审查工作区  |  法务资产管理控制台            │
                               └───────────────────────────┬────────────────────────────┘
                                                           │ HTTP / SSE (反向代理)
                                                           ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          FastAPI 服务进程 (API & Agent Runtime)                                   │
│                                                                                                                   │
│   ┌───────────────────────────┐      ┌───────────────────────────────┐      ┌─────────────────────────────────┐   │
│   │       REST 接口路由       │ ───> │     Application 业务用例层    │ ───> │        Domain 核心领域层        │   │
│   │  /api/v1/knowledge-bases  │      │  - DocumentIngestion (摄取)   │      │  - 知识库与文档版本实体         │   │
│   │  /api/v1/conversations    │      │  - RetrievalService (检索)    │      │  - Parent-Child 分块树模型      │   │
│   │  /api/v1/retrieval-debug  │      │  - ChatService (会话审查)     │      │  - 引用防伪与证据门控协议       │   │
│   │  /api/v1/config           │      │  - CitationService (溯源)     │      │  - 摄取状态机与租约契约         │   │
│   └───────────────────────────┘      └───────────────┬───────────────┘      └─────────────────────────────────┘   │
│                                                      │                                                            │
│                                                      ▼                                                            │
│                                      ┌───────────────────────────────┐                                            │
│                                      │    LangGraph Agent Runtime    │                                            │
│                                      │     有界循环图 (最多 2 轮改写)  │                                            │
│                                      └───────────────┬───────────────┘                                            │
└──────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┘
                                                       │ 投递异步任务 (以作业行为单一交付契约)
                                                       ▼
┌────────────────────────────┐          ┌──────────────────────────────┐          ┌─────────────────────────────────┐
│     RabbitMQ 业务队列       │ ───────> │    Taskiq Worker 异步消费     │ ───────> │      外部存储与大模型提供方     │
│     - taskiq (任务分发)    │          │    - 异构文档解析 (Parse)    │          │  - SiliconFlow (LLM / Embed)    │
│     - taskiq.dead_letter   │          │    - 确定性分块规划 (Chunk)  │          │  - ParadeDB (PostgreSQL 18)     │
│                            │          │    - 密集向量计算 (Embed)    │          │    事实 / 倒排 / pgvector HNSW  │
│                            │          │    - 向量核验就绪 (Index)    │          │  - Redis 8 (限流 / 锁 / 缓存)   │
└────────────────────────────┘          └──────────────────────────────┘          │  - RustFS / S3 (对象存储)       │
                                                                                  │  - Langfuse v4 (链路可观测性)   │
                                                                                  └─────────────────────────────────┘
```

---

## 🔬 核心技术机制

### 1. 异构文档解析与 Parent-Child 切分树
- **格式自适应路由**：针对 Office 文档（DOCX/PPTX/XLSX）调用 AnyDoc 解析；纯文本与 HTML 经规范化后输出；PDF 扫描件或图像自动路由至 PaddleOCR-VL 进行版面分析与文字识别，输出带有页码与标题层级的标准 Markdown。
- **分层协同切分**：
  - **Child Chunk（检索子块）**：256–512 tokens，滑动窗口保留 32 tokens 重叠，负责向量嵌入计算与倒排索引，作为引用锚点；
  - **Parent Chunk（语义父块）**：1024–2048 tokens，基于 Markdown 标题树（Heading Path）与段落边界聚合成完整语义上下文，负责大模型提问拼装。

### 2. 双通道混合召回与 RRF 融合
- **双路并发检索**：API 服务并发向 pgvector（Dense 密集向量，BGE-M3，HNSW cosine）与 pg_search（Keyword BM25）发起检索，两者同处一个数据库但各自独立会话，单路设置硬性超时保护。
- **应用层 RRF 融合**：由应用层执行无量纲的倒数排名融合算法（Reciprocal Rank Fusion，常数 $k=60$）：
  $$\text{RRF}(d) = \sum_{c \in \{\text{dense}, \text{keyword}\}} \frac{w_c}{k + r_c(d)}$$
- **交叉注意力重排**：截取 RRF 融合前 50 条候选子块送入 BGE-Reranker-v2-m3，按交叉注意力得分过滤并重新排序。

### 3. 证据门控（Evidence Gate）与有界图状态机
- **门控决策分级**：
  - `sufficient`：重排最高得分达到阈值且召回密度充分，直接进入生成节点；
  - `degraded`：部分通道超时或异常，但剩余通道满足最低基线，携带降级标记作答；
  - `insufficient`：证据不足。若改写预算（默认最多 2 轮）未耗尽，进入 Query Rewrite 节点尝试改写提问并重新检索；若预算用尽，**主动弃答（Abstain）**。

### 4. 三层引用防伪协议（Citation Protocol）
- **L1 提示词清洗**：剔除候选正文中自带的伪造标记（如文档自带的 `[S1]`），杜绝提示词投毒；
- **L2 证据集强校验**：大模型流式输出 `[S1]` 引用标记，服务端在生成后核验标记是否严格属于本轮通过门控的候选子块；非法标记按策略剥离或直接拒绝；
- **L3 权威坐标映射**：将校验通过的标记回表解析出数据库主键、对象存储中的 Markdown 物理行号（`line_start`–`line_end`）、所属段落与权威原文切片。

---

## 🛠️ 技术栈选型矩阵

| 层次 / 领域 | 核心技术选型 | 关键依据与工程考量 |
| :--- | :--- | :--- |
| **基础环境** | Python 3.12 (`>=3.12,<3.13`) | 锁定 Python 3.12 稳定版本，以 `uv.lock` 为绝对依赖权威，秒级依赖解析与环境同步。 |
| **API 服务** | FastAPI + Pydantic v2 | 高性能异步 ASGI 框架，强类型请求/响应校验，OpenAPI 规范自动生成。 |
| **Agent 状态机** | LangGraph 1.x + LangChain 1.x | 显式构建有界循环图，支持 Checkpoint 状态暂存、事件流式分发与单步执行追踪。 |
| **关系持久化** | ParadeDB (PostgreSQL 18) + SQLAlchemy 2.0 Async | 系统唯一的事实真相来源（Single Source of Truth）；向量、关键词索引与业务事实同库同事务。 |
| **向量检索** | pgvector 原生 HNSW cosine | `child_chunk_embeddings.embedding vector(1024)` 上的 HNSW 索引，随 WAL 复制与 PITR 一起备份；启动即受 readiness 核对。 |
| **关键词检索** | ParadeDB `pg_search` BM25 | 真正的相关性模型而非子串扫描；默认 `unicode_words` 分词器按 CJK 单字切分，中英混排合同与定义词均能命中。 |
| **缓存与限流** | Redis 8 (redis:8-alpine) | 承载 API 速率限制、分布式互斥锁与单轮检索调试缓存；严禁将 Redis 用作业务消息队列。 |
| **异步队列** | RabbitMQ + Taskiq | RabbitMQ 作为平台**唯一的业务异步消息队列**；Taskiq 提供异步消费与重试。 |
| **对象存储** | RustFS / AWS S3 兼容协议 | 高效存储原始合同文件、解析后的标准 Markdown 制品及 JSONL 分块元数据。 |
| **全链路观测** | Langfuse v4 + ClickHouse + structlog | 追踪 LLM 调用链、Token 消耗、检索延迟与证据门控决策；脱敏敏感数据。 |
| **前端架构** | React 19 + TypeScript 5 + Vite+ (`vp`) | 特性优先（Feature-First）模块划分；TanStack Query 接管异步状态；Tailwind CSS 单源样式设计。 |

---

## 🚀 快速开始

### 📋 环境准备

确保本机已安装以下基础工具：
- **Docker** 与 **Docker Compose** (v2.20+)
- **Python 3.12** 与 **uv** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js 24** 与 **pnpm 12**
- **Vite+ CLI (`vp`)** (`pnpm add -g @vitejs/vite-plus`)

---

### 方案 A：全栈容器化一键部署（推荐验收路径）

执行一条命令，自动完成镜像构建、从模型建立 schema、服务就绪等待：

```bash
# 启动全栈（基础设施 + 一次性 schema-init + API + Agent + Worker + Web 前端）并等待就绪
docker compose --profile app up -d --build --wait

# 验证各依赖与服务健康状态
curl -fsS http://localhost:5173/health/ready
curl -fsS http://localhost:5173/api/v1/config
```

在浏览器打开 `http://localhost:5173` 即可立即进入工作台开始合同审查。  
如需停止并清理容器：
```bash
docker compose --profile app down
```

---

### 方案 B：本地敏捷开发循环（Dev Loop）

在本地开发、断点调试与界面热更新时，推荐使用“**依赖跑在容器，进程跑在宿主机**”模式：

```bash
# 1. 复制并配置环境变量
cp .env.example .env
# 编辑 .env 配置 SILICONFLOW_API_KEY 与 PADDLEOCR_API_KEY

# 2. 拉起基础容器依赖，然后建表、初始化存储桶
docker compose up -d --wait
uv run python -m cli schema-init
uv run python -m cli storage-init

# 3. 三个后端进程与前端各起一个终端（改了代码直接重启对应进程）
uv run python -m api.main            # 业务 API       http://127.0.0.1:8000
uv run python -m agent_runtime.main  # Agent 运行时    http://127.0.0.1:8001
uv run python -m worker.main         # 摄取流水线 Worker
pnpm --dir frontend run dev          # 前端 dev server http://localhost:5173
```

改了 ORM 模型之后要重建表结构（破坏性：先删表再建，现有数据全部丢失）：

```bash
uv run python -m cli schema-reset
```

> **跨平台契约**：仓库严格遵循平台中立性，不提供特定操作系统脚本（`.ps1`/`.bat`），本地与部署环境统一使用 Docker Compose 与标准 Python 命令。

---

## 🛡️ 工程质量门禁与验证

本项目恪守严谨的软件工程标准，所有改动必须通过静态检查与运行时验收两道门禁：

### 1. 静态代码与类型检查（每次提交前必过）

```bash
# 后端与评测集全量静态门禁（依赖锁定同步 + Ruff 代码检查 + Ruff 格式化 + Pyright strict 模式 0 错误 + 入口检查 + 单向架构依赖核验 + 评测集复现）
uv sync --locked --group eval
uv run ruff check backend/src
uv run ruff format --check backend/src
uv run pyright backend/src
uv run python -c "import api.main, agent_runtime.main, worker.main, cli.main"
uv run python scripts/check-architecture.py
uv run python scripts/build-goldenset.py --verify

# 前端代码格式化、Linter 与类型检查
pnpm --dir frontend run check

# 前端逻辑单元测试（包含代际栅栏、SSE 协议解析、API 映射等）
pnpm --dir frontend run test
```

### 2. 架构单向依赖硬性约束

系统通过 `scripts/check-architecture.py` 在 CI 中进行 AST 静态解析，强制阻断跨层违规导入：
- `domain` 绝对独立，禁止依赖任何框架与外部库；
- `application` 仅依赖 `domain`；
- `api` / `agent_runtime` / `worker` 仅通过用例层操作业务，严禁越层导入 `infrastructure.db`；
- 禁止创建 `utils`、`helpers`、`common` 等无明确职责边界的垃圾模块名。

---

## 📂 项目目录结构

```text
├── backend/
│   └── src/
│       ├── api/               # FastAPI REST 路由接入层、HTTP 异常映射、限流与配置契约
│       ├── application/       # 业务用例服务层 (Ingestion, Retrieval, Chat, Citations, RateLimit)
│       ├── domain/            # 纯业务领域模型 (Document, Chunk, Citation, Knowledge)
│       ├── infrastructure/    # 外部协议适配器 (PostgreSQL/pgvector, Redis, RabbitMQ, S3, SiliconFlow)
│       ├── composition/       # 依赖注入容器装配工厂与运行时编排
│       ├── agent_runtime/     # LangGraph 审查 Agent 有界图状态机与流式引擎
│       ├── worker/            # Taskiq 异步摄取流水线任务消费者与调度器
│       └── cli/               # 平台运维管理命令行工具集 (schema-init, storage-init, reindex, cleanup)
├── frontend/
│   ├── src/
│   │   ├── app/               # React 应用入口与全局 Providers 配置
│   │   ├── components/        # 原子 UI 控件 (Icons, Status, Dialogs)
│   │   ├── features/          # 特性业务模块 (Feature-First)
│   │   │   ├── chat/          # 合同审查核心面板、流式输出、引用气泡、证据原文检视
│   │   │   ├── documents/     # 知识库文档列表、物理版本追溯与上传流水线
│   │   │   ├── ingestion-jobs/# 摄取流水线任务看板与状态机监控
│   │   │   ├── knowledge-bases# 知识库目录与文档管理
│   │   │   ├── retrieval-debug# 检索单步诊断控制台 (Dense/Keyword/RRF/Rerank/Gate)
│   │   │   ├── settings/      # 运行时服务配置速查与系统配置面板
│   │   │   └── shell/         # 双工作区外壳 (ChatShell / ConsoleShell) 与路由调度
│   │   ├── lib/               # 核心协议库 (代际栅栏 generation, sse 解析, api 客户端)
│   │   └── routes/            # 路由定义与懒加载代码拆分
│   └── nginx.conf             # 生产级网关路由与动静态反向代理配置
├── docs/                      # 核心架构规范、数据流图、引用防伪协议与 ADR 归档
│   ├── adr/                   # 架构决策记录 (Architecture Decision Records)
│   └── architecture/          # 系统拓扑、召回流水线、引用协议设计文档
├── docker-compose.yml         # 中间件与全栈应用容器编排（仓库根自动发现，无需 -f）
├── scripts/                   # 门禁脚本、架构检查工具、黄金评测集构建工具
├── DESIGN.md                  # Google 标准规范系统设计白皮书 (Design Doc)
├── AGENTS.md                  # AI 智能体开发工程契约与最高行动准则
└── pyproject.toml / uv.lock   # Python 依赖清单与哈希锁定
```

---

## 📜 关键架构与设计文档

- **系统技术设计白皮书**：查阅 [DESIGN.md](DESIGN.md)（遵循 Google Design Doc 标准编撰）。
- **智能体开发工程契约**：查阅 [AGENTS.md](AGENTS.md)（定义核心架构十二大铁律）。
- **架构决策记录**：查阅 [docs/adr/](docs/adr/)。
- **引用防伪协议规范**：查阅 [docs/architecture/citation-protocol.md](docs/architecture/citation-protocol.md)。
- **检索与融合流水线**：查阅 [docs/architecture/retrieval-pipeline.md](docs/architecture/retrieval-pipeline.md)。

---

## ⚖️ 免责声明

ClauseRAG 旨在为商务合同审查人员、企业法务与执业律师提供高确定性的合同条款检索、语义对比与条款分析辅助工具。  
本系统所输出的审查结论与回答**不构成正式的法律意见或执业律师代理意见**。具体商业合同签署、条款修改与法律争议决策应由具备相应司法管辖区执业资格的专业律师最终审定。

---

<div align="center">
  <sub>ClauseRAG 团队精心打造 • 秉持「可追溯的记录」核心工程标准</sub>
</div>
