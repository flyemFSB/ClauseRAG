# Design Doc: ClauseRAG — US Commercial Contract Review Agentic RAG Platform

| Metadata | Details |
| :--- | :--- |
| **Title** | ClauseRAG: Architecture, Retrieval Engine, and System Specification |
| **Author** | ClauseRAG Architecture Working Group |
| **Status** | **Approved / Living Architecture Document** |
| **Created** | 2026-10-02 |
| **Last Updated** | 2026-10-06 |
| **Document Type** | Google-Standard System Design Document |

---

## 1. Overview & Executive Summary

**ClauseRAG** 是一套专为涉美商业合同审查、法律条款检索与跨协议风险穿透分析打造的 **Agentic RAG（智能体检索增强生成）平台**。

系统以**「可追溯的记录」（The Traceable Record）**为创意北极星（Creative North Star）：每一句由大模型生成的审查建议或条款分析，均必须能够精确回溯至权威合同文档的具体版本、Markdown 标题/条款路径、行号区间和由后端严格校验的原文字片，彻底杜绝虚假幻觉对商业决策与法律合规带来的灾难性后果。

在系统工程层面，ClauseRAG 采用模块高内聚、依赖单向分层的领域驱动设计（DDD）：
1. **多源异构解析**：自适应路由 Office、HTML、TXT 及基于 PaddleOCR-VL 的扫描件版面解析；
2. **Parent-Child 分块树**：小块子切片负责精准命中与引用锚定，大块父切片负责保留完整商业合同条款上下文；
3. **双通道混合召回**：Qdrant 密集向量与 PostgreSQL `pg_trgm` 关键词匹配并行检索；
4. **应用层 RRF 与重排序**：解耦底层异构存储，由应用层执行倒数排名融合（RRF）与 BGE-Reranker-v2-m3 精排；
5. **动态证据门控（Evidence Gate）**：基于质量阈值划分证据等级（`sufficient` / `degraded` / `insufficient`），支持有界查询改写，证据不足时主动弃答；
6. **双工作区前端交互**：隔离商业合同审查问答与法务资产运维管理场景，集成代际栅栏（Generation Fence）杜绝过时异步请求竞态污染。

---

## 2. Context & Motivation

### 2.1 业务背景与合同审查痛点
涉美商业合同审查（如 Master Services Agreement、NDA、SaaS Agreements 等）对 RAG 系统的准确度与责任边界有着极其严苛的要求：
- **致命的幻觉风险**：通用 RAG 系统依赖概率匹配生成回答，模型常在缺乏充分合同证据时自行推演或编造未约定的权利义务，可能导致数百万美元的法律责任或商业谈判失利。
- **引用不可验证**：多数系统采用“生成后由模型自己标注来源”，模型经常胡乱生成虚构的参考条款或错位的段落序号。
- **异构文献版面复杂**：商业合同、附件工作说明书（SOW）与过往签署件多为扫描版 PDF，传统纯文本抽取丢失表格结构、上下级条款层级（Article/Section）与页码定位。
- **跨文档隐式关联缺失**：赔偿条款（Indemnification）、责任上限（Limitation of Liability）与保密义务常分布在主协议与补充附件中，单一向量匹配无法建立实体跨文档关联。

### 2.2 为什么构建 ClauseRAG
现有开源方案（如 LangChain 默认链路或简易知识库工具）往往将向量库、检索和提示词直接耦合在前端或单个单体函数中，缺乏明确的事务边界、超时熔断、幂等性重试以及证据判定机制。ClauseRAG 旨在确立企业级法务科技标准：**证据驱动生成、行级坐标溯源、有界状态机推理、真实容器验证**。

---

## 3. Goals & Non-Goals

### 3.1 Goals
- **G1（绝对引用权威性）**：所有回答引用必须由后端依据真实提取的存储制品核实，提供行号区间与原文字片；无效引用标记严禁静默入库或透传。
- **G2（双通道高质量召回）**：并行融合 Dense（语义）与 Keyword（术语字面）双通道，在应用层实现确定性 RRF 算法与二次精排。
- **G3（证据有界控制与主动弃答）**：建立证据门控节点；当召回证据不足以支撑法律审查结论时，系统必须明确标识并主动放弃生成，而非臆测。
- **G4（高内聚分层与单向依赖）**：严格贯彻 `api → application → domain` 分层，外部系统全部隔离在 `infrastructure`，由 `composition` 容器组装。
- **G5（生产级并发与容错）**：RabbitMQ 作为唯一异步任务队列；任务投递具备幂等去重；所有外部 I/O 均设置有界超时与错误分类；前端杜绝异步竞态。
- **G6（真实容器验证优先）**：以真实 Docker 容器环境端到端探针测试作为验收唯一依据，并在 `dist/verify/` 输出完整证据工件。

### 3.2 Non-Goals
- **NG1（第一期不包含公网爬虫）**：首发版本不提供任意 Web URL 的实时动态爬取，所有知识必须通过显式文档上传导入。
- **NG2（不采用无界自我循环 Agent）**：坚决禁止无终止条件的自我反思（Self-reflection）或死循环检索；LangGraph 执行图严格限制单次运行最多重试 2 轮。
- **NG3（不将 Redis 用作持久业务队列）**：任务传递与状态流转完全由 RabbitMQ 与 PostgreSQL 承担；Redis 当前不承担任何业务职责，也已从依赖、就绪探针与配置中移除。
- **NG4（不为前端编写脱离业务的浅层单测）**：前端重视核心流式规约与代际隔离的真实逻辑测试，不引入大面积无意义的 DOM 浅层快照。

---

## 4. Architectural Overview

### 4.1 系统上下文架构 (C4 Context Diagram)

```text
                                 ┌─────────────────────────────────┐
                                 │    企业法务 / 律师 / 审查人员   │
                                 └────────────────┬────────────────┘
                                                  │ HTTPS / WSS
                                                  ▼
                                 ┌─────────────────────────────────┐
                                 │     ClauseRAG 前端 Web 应用     │
                                 │  React 19 + TypeScript + Vite+  │
                                 └────────────────┬────────────────┘
                                                  │ REST API / SSE
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   ClauseRAG 后端核心系统                                        │
│                                                                                                 │
│   ┌────────────────────────┐      ┌─────────────────────────┐      ┌────────────────────────┐   │
│   │     FastAPI 接入层     │─────>│    Application 业务层   │─────>│       Domain 核心层    │   │
│   │  /auth, /documents,    │      │  - IngestionService     │      │  - 知识库与文档聚合    │   │
│   │  /conversations, SSE   │      │  - RetrievalService     │      │  - Parent-Child 切分树 │   │
│   └────────────────────────┘      │  - ChatExecutionService │      │  - 引用溯源与门控规则  │   │
│                                   └────────────┬────────────┘      └────────────────────────┘   │
│                                                │                                                │
│                                                ▼                                                │
│                                   ┌─────────────────────────┐                                   │
│                                   │  LangGraph 状态图运行时 │                                   │
│                                   │  (Bounded Agent Graph)  │                                   │
│                                   └────────────┬────────────┘                                   │
└────────────────────────────────────────────────┼────────────────────────────────────────────────┘
                                                 │ 异步分发
                                                 ▼
┌───────────────────────┐          ┌──────────────────────────┐          ┌────────────────────────┐
│  RabbitMQ 消息队列    │─────────>│  Taskiq Worker 后台集群  │─────────>│   外部存储与大模型     │
│  - 摄取调度           │          │  - PaddleOCR / AnyDoc    │          │   - SiliconFlow API    │
│  - 异步清理通道       │          │  - 分块生成与向量构建    │          │   - PostgreSQL 16      │
└───────────────────────┘          │  - 向量索引与检索       │          │   - Qdrant 向量库      │
                                   └──────────────────────────┘          │   - RustFS / S3 存储   │
                                                                         │   - Langfuse 观测平台  │
                                                                         └────────────────────────┘
```

### 4.2 物理进程边界与职责划分

| 进程名称 | 启动入口 | 核心职责 | 线程/异步模型 |
| :--- | :--- | :--- | :--- |
| **API 服务** | `python -m api.main` | 承接客户端 HTTP 请求、轻量级元数据读写、SSE 长连接事件推流。 | Uvicorn AsyncIO |
| **Agent 运行时** | `python -m agent_runtime.main` | 托管 LangGraph 有界图执行引擎、意图分类、多通道并发检索触发、流式 Delta 产出。 | LangGraph Checkpointer + AsyncIO |
| **Worker 消费进程** | `python -m worker.main` | 消费 RabbitMQ 队列；运行重型计算（OCR 解析、分块聚类、Embedding 批处理、物理资源清理）。 | Taskiq Async Worker |
| **CLI 运维套件** | `python -m cli` | 运行数据库迁移排查、拓扑结构打印、环境探针诊断与数据备份导入。 | 同步/异步 CLI 管道 |
| **Web 前端** | `vp dev` / `vp preview` | 双工作区 UI、TanStack 缓存维护、代际栅栏防竞态、行内 Markdown 渲染与 Popover 溯源。 | Single-Page Application (SPA) |

---

## 5. Detailed System Design

### 5.1 文档解析与 Parent-Child 切分设计 (Ingestion Pipeline)

#### 解析路由策略 (Parser Router)
文档上传至 RustFS / S3 原生桶后，Worker 依据文件 MIME 与扩展名触发分发：
1. **AnyDoc 路由**：处理 Office 文档（DOCX/PPTX/XLSX），提取段落、层级标题、表格数据，转化为标准 GFM Markdown；
2. **纯文本/HTML 路由**：规范化字符集，移除冗余样式标签，提取正文结构；
3. **PaddleOCR-VL 视觉路由**：处理 PDF 与扫描图片。执行版面分析（Layout Analysis），将检测到的文本块、表格及标题组合成带标题层级的 Markdown 制品，持久化至对象存储 `parse_artifacts.markdown_object_key`。

#### Parent-Child 树状切分机制
传统固定长度滑动窗口会撕裂合同法律条款上下文。ClauseRAG 实施两级树状切分：
- **Child Chunks（子块）**：
  - 长度限制：256–512 tokens，重叠 32 tokens。
  - 用途：计算 BGE-M3 向量嵌入、录入 Qdrant 集合、构建 PostgreSQL `pg_trgm` 倒排索引用作**检索与条款引用锚点**。
  - 元数据记录：所属文档版本 ID、父块 ID、标题/条款路径（`heading_path`）、Markdown 绝对行号（`line_start`–`line_end`）。
- **Parent Chunks（父块）**：
  - 长度限制：1024–2048 tokens。
  - 用途：以 Markdown H2/H3 标题、Article/Section 条款边界为切割点，完整保留临近商业合同上下文，**专供回答生成上下文（Context Feeding）使用**。

```text
[Parent Chunk 1: Article 8 - Limitation of Liability (Tokens: 1250, Line: 1-68)]
   ├── [Child Chunk 1-1: 8.1 责任上限总额限制 (Tokens: 380, Line: 1-22)]  --> 写入 Qdrant & PG
   ├── [Child Chunk 1-2: 8.2 间接与附带损失免责 (Tokens: 410, Line: 20-45)] --> 写入 Qdrant & PG
   └── [Child Chunk 1-3: 8.3 重大过失与保密除外条款 (Tokens: 460, Line: 42-68)]   --> 写入 Qdrant & PG
```

---

### 5.2 双通道混合检索与应用层 RRF 融合 (Retrieval Engine)

为了兼顾语义理解与专有名词完全匹配，系统设计双通道并行召回架构：

```text
用户查询 (Query)
   │
   ├─► [Dense 通道]  ───► Qdrant 向量库 (BGE-M3, 1024维) ──────────► Top-30 子块候选
   │
   └─► [Keyword 通道] ──► PostgreSQL pg_trgm 字符倒排索引 ────────► Top-30 子块候选
                                                                         │
                                                                         ▼
                                                     [应用层 Reciprocal Rank Fusion (RRF)]
                                                                         │
                                                                         ▼
                                                     [SiliconFlow BGE-Reranker-v2-m3]
                                                                         │
                                                                         ▼
                                                          [Top-50 精排候选与分数评估]
```

#### 应用层 RRF 融合公式
不同底层数据库的原始分值不可比（Qdrant 为余弦相似度，PostgreSQL 为 trigram 匹配度）。应用层依据统一的倒数排名融合算法消除量纲差异：

$$\text{RRFScore}(d) = \sum_{c \in \{\text{dense}, \text{keyword}\}} \frac{w_c}{k + r_c(d)}$$

- 常数 $k = 60$（遵循经典信息检索实验最佳常数）；
- 默认通道权重：$w_{\text{dense}} = 1.0$, $w_{\text{keyword}} = 1.0$；
- $r_c(d)$ 为候选子块在对应通道中的排名序号（1-indexed）。

#### 交叉注意力重排序 (Reranking)
融合排序前 50 条候选子块送入 SiliconFlow 托管的 `BAAI/bge-reranker-v2-m3` 计算跨文本注意力得分 $\text{score} \in [0, 1]$，得出最终权威排序列表。

---

### 5.3 有界 Agent 图与证据门控 (Evidence Gating & Agent Graph)

系统状态机基于 LangGraph 明确建模，严禁不可预测的无界循环：

```text
       ┌───────────────┐
       │ load_context  │
       └───────┬───────┘
               ▼
      ┌─────────────────┐
      │ understand_query │
      └────────┬────────┘
               ▼
        [ route_query ]
        ├─► direct_response ───────► END (闲聊/非法律审查通用问题直接回答)
        ├─► ask_clarification ─────► END (意图不清主动反问)
        └─► plan_retrieval
                  │
                  ▼
             [ retrieve ] ◄────────────────────────┐
          (双通道召回+RRF+重排)                    │
                  │                                │
                  ▼                                │
          [ evaluate_gate ]                        │
                  ├─► sufficient ──► generate ──► validate_citations ──► END
                  │                                                        ▲
                  ├─► degraded ────► generate (带降级标识) ────────────────┤
                  │                                                        │
                  └─► insufficient                                         │
                         ├─ [未达轮次上限 2] ──► rewrite_query ────────────┘
                         └─ [达到轮次上限 2] ──► abstain_response ────────► END
```

#### 证据状态判定标准 (Gate Criteria)
- **`sufficient`**：Top 1 重排相关度得分 $\ge 0.2$（可配置）且累计 Top 候选包含充足的关键实体与上下文覆盖。
- **`degraded`**：某一非关键通道异常挂起或网络超时，但其余有效通道返回的证据足以覆盖核心问题。
- **`insufficient`**：所有通道召回候选重排分均低于阈值，或无任何候选返回。

#### 主动弃答策略 (Abstain)
当重试预算耗尽（`retrieval_rounds >= 2`）仍处于 `insufficient` 状态时，执行 `abstain_response` 节点：
- 生成标准说明：“根据当前知识库中的商业合同与附件，暂无确凿依据支持对该条款的准确解答。”
- 引导建议：“建议调整提问关键词或条款编号，或在管理控制台上传相关协议文件及补充协议。”
- **坚决不调用 LLM 强行生成答案**。

---

### 5.4 权威引用协议与防幻觉校验 (Citation Protocol)

#### 传输与流式事件契约 (SSE Contract)
客户端与服务端通过标准 Server-Sent Events 通信，单次会话流严格遵循单一终态约束：

```text
event: run_started     --> {"run_id": "...", "conversation_id": "..."}
event: answer_delta    --> {"text": "乙方对任何间接、附带或惩罚性损害赔偿"}
event: answer_delta    --> {"text": "均不承担任何赔偿责任 [S1]。"}
event: citation        --> {"citation_id": "S1", "document_name": "Master_Services_Agreement.pdf", "quote": "...", "line_start": 42}
event: run_completed   --> {"answer": "...", "citations": ["S1"], "evidence_status": "sufficient"}
```

#### 服务端引用防伪校验
1. **生成约束**：Prompt 规定大模型仅能插入 `[S1]`, `[S2]` 形式的标记，且标记必须指向本次召回上下文所赋予的标识。
2. **有效性核验（`validate_citations`）**：
   - 遍历生成文本中出现的所有 `[Sn]`；
   - 对比本次检索门控通过的子块映射表；
   - 若发现不存在的引用 ID，根据系统安全策略执行剥离（`strip`）并在终态报告，或直接拒绝（`reject`）；绝不接受模型编造的引用。
3. **真实坐标绑定**：引用中的 `quote` 字段直接取自存储在对象存储里的真实切片文字，而非模型复述内容。

---

### 5.5 存储架构与数据所有权模型 (Data Architecture)

系统明确划分各类数据的**单一权威事实源（Single Source of Truth）**：

| 数据类别 | 权威事实源 | 存储模型与技术细节 | 生命周期与同步机制 |
| :--- | :--- | :--- | :--- |
| **主体与资源归属** | PostgreSQL | `knowledge_bases.owner_id`、`conversations.owner_id`；平台以展示为目的上线，无账号表（ADR-0033）。 | 关系型持久化，事务保证。 |
| **知识库与文档版本** | PostgreSQL | `knowledge_bases`, `documents`, `document_versions`。 | 软状态追踪；文档版本采用自增单调修订号。 |
| **原始文件与中间制品** | RustFS / S3 | `raw_files/`, `parse_artifacts/` 桶内不可变对象。 | 文件上传后只读写入；删除文档时生成异步清理意图。 |
| **切片索引树** | PostgreSQL | `parent_chunks`, `child_chunks` 表；记录标题路径与行号。 | 关系型存储，支撑级联溯源与 `pg_trgm` 关键词匹配。 |
| **业务向量集合** | Qdrant | Collection: `rag_child_chunks`（1024 维余弦向量）。 | 由 Worker 批量向量化后插入；携带 `document_version_id` Payload。 |
| **父子块与向量** | Qdrant + PG | 子块向量存于 Qdrant，坐标与正文存于 PostgreSQL。 | 向量检索与权威行号校验各自使用最合适的存储。 |
| **会话与检查点** | PostgreSQL | `conversations`, `messages`, LangGraph checkpoint 表。 | 保证故障恢复与跨轮次记忆回溯。 |
| **异步任务状态** | PostgreSQL | `ingestion_jobs`（含 `not_before`、`lease_expires_at`、`dispatched_at`）。 | 作业行是投递与重试的唯一契约；RabbitMQ 只负责唤醒。 |

---

### 5.6 异步任务流水线与幂等设计 (Task Pipeline)

摄取流程包含耗时的 OCR 解析，全量解耦至 Taskiq + RabbitMQ 异步流水线：

```text
[上传文档] ──► 创建 Job 记录 (状态: pending, 写入 PG)
                  │
                  ▼
              [派发至 RabbitMQ: taskiq.tasks]
                  │
                  ▼
              [Worker 消费认领] ──► 更新 Job 为 running
                  │
                  ├─► 执行 Parse 阶段 ──► 成功写入制品，派发 Chunk 任务
                  ├─► 执行 Chunk 阶段 ──► 成功写入切片，派发 Index 任务
                  ├─► 执行 Index 阶段 ──► 成功构建向量索引，更新 Version 为 ready
                  │
                  └─► 发生瞬态异常 (如 API 503) ──► 作业行置回 pending + not_before，由 Worker 对账重投
```

#### 幂等投递与去重保障
- 同一文档版本的同一阶段任务，Worker 认领时首先比对数据库中该版本的最新状态与已完成修订号。若当前任务已被更新的版本覆盖或已处于完成态，立即发送 `ingestion.delivery_skipped` 事件并确认（Ack）消息，杜绝重复写入。
- **清理意图（Cleanup Intents）**：删除文档或知识库时，主事务仅原子删除 PostgreSQL 事实行并向 `cleanup_intents` 插入待清理标记；对象存储删除与向量删除由 Worker 异步重试消费，保证删除操作永不因外部云服务暂时抖动而回滚。

---

### 5.7 前端双工作区架构与视觉设计系统 (Frontend Architecture & Design System)

#### 双工作区划分与代际栅栏
- **合同审查（`/chat`）**：单屏浮动岛（Island），最大化对话交互区域，支持大屏常驻侧栏与小屏自适应抽屉。
- **资产控制台（`/admin/*`）**：220px 标准侧栏 SaaS 布局，提供看板、文档流水线状态监控、检索调试与系统指标配置。
- **代际栅栏（Generation Fence）**：前端网络层为每次并发调用生成代次编号。切换知识库或输入新问题时，通过 `abandonRound()` 推进版本号并触发 `AbortController.abort()`，保证迟到或异常的 HTTP/SSE 响应被物理丢弃，无法写入当前 React 状态。

#### 完整设计系统契约 (Design System Tokens)
系统全面继承既定的工程化视觉规范：
- **设计北极星**：中性灰阶、系统原生字体、1px 发丝线、无多余装饰，如同严谨客观的商业合同与法务审查文书。
- **调色板系统**：
  - 画布底色：`#FFFFFF`（浅色）/ `#1A1D24`（深色）；
  - 次级表面：`#F5F5F7`（浅色）/ `#21242C`（深色）；
  - 核心正文：`#1D1D1F`（浅色，对比度 16.8:1）/ `#E6E6E6`（深色）；
  - 法务专业蓝：`#1677FF`（基础），`#0958D9`（高对比主色），`#E6F4FF`（软底色）；
  - 语义状态：成功 `#52C41A`、告警 `#FAAD14`、错误 `#FF4D4F`，均配对专用文本 Ink 色。
- **排版与无障碍**：
  - 数字与度量一律采用等宽数字（`font-variant-numeric: tabular-nums`），保障跨行竖向对比可读性；
  - 严格遵循 WCAG AA 标准，所有交互控件边界对比度 $\ge 3:1$，正文对比度 $\ge 4.5:1$。

---

## 6. Cross-Cutting Concerns

### 6.1 安全性与数据边界 (Security & Privacy)
- **无登录的单主体部署**：平台以展示为目的上线，不提供登录与会话 Cookie（ADR-0033）。知识库、文档与会话仍绑定 `owner_id`，但全部请求都是同一个平台主体，因此平台内部没有跨用户的权限边界。
- **资源不存在统一 404**：
  - 查询不存在（或标识符格式不对）的资源时统一返回 `404 Not Found`，而非 `403 Forbidden` 或 `500`，不会通过状态码泄露资源是否存在；
- **敏感数据防泄露**：
  - 所有结构化日志在输出前对用户真实姓名、密码哈希、完整文档内容及 API Key 进行脱敏或完全剔除；
  - 生产日志仅记录 UUID 标识符与关键耗时指标。

### 6.2 可靠性、并发与容错 (Reliability & Concurrency)
- **显式超时边界**：所有对外部 API（SiliconFlow、Qdrant、RabbitMQ、S3）的调用必须显式设置超时（HTTP 默认 10s，检索通道 30s，重型解析 900s），严禁无限阻塞。
- **保护异步取消链**：Python 异步任务严禁吞没 `asyncio.CancelledError`，确保当客户端主动断开连接时，后方的线程与计算资源能够被操作系统即时回收。
- **禁止跨协程共享 AsyncSession**：每个异步任务/请求独立获取 SQLAlchemy `AsyncSession` 上下文，彻底杜绝连接状态污染与死锁。
- **有界重试与抖动退避**：后台任务仅对明确分类的网络抖动或提供商 503 进行有限重试（最多 3 次），重试间隔引入随机抖动（Jitter），防止惊群效应（Thundering Herd）。

### 6.3 可观测性与运行状态 (Observability)
- **结构化日志**：structlog JSON，带请求/任务/追踪标识，不含密钥、签名地址与文档原文。
- **健康探针**：`/health/live`（存活）与 `/health/ready`（逐依赖并发探测 + 超时 + 每项延迟，任一不可用返回 503）。
- **生效配置**：`GET /api/v1/config` 报出本进程实际读到的配置（含被环境变量覆盖后的值；密钥项只报是否已配置），前端两张配置页直接读它，不再抄手册。
- **链路追踪**：Langfuse（可选）记录单次运行与摄取 attempt 的 span 树；密钥缺失时整条链路自动退化为 no-op，观测性不是业务链路的前置条件。
- **已知缺口**：没有 `/metrics` 与告警。健康检查只能回答"此刻能不能用"，回答不了错误率、延迟分位与队列积压趋势。补法：应用侧用 `prometheus-client` 暴露 `/metrics`（counter/gauge/histogram），Prometheus 按间隔拉取，Grafana 出面板，Alertmanager 对错误率、p95 延迟、`pending` 任务积压与模型调用失败率告警。
## 7. Alternatives Considered & Trade-offs

### 7.1 为什么采用应用层 RRF，而非单数据库混合搜索？
- **考量方案**：直接使用单个数据库（如 PostgreSQL pgvector + pg_trgm，或 Qdrant 内置 hybrid search）。
- **决策理由**：涉美商业合同审查场景下，通用向量数据库的文本语义匹配能力无法完全覆盖法律术语的精确同义检索。将 Qdrant（密集向量高吞吐）与 PostgreSQL（元数据与精确匹配）分离，并通过应用层 RRF 融合，可以保持各组件的纯粹性，允许独立水平扩展与独立升级，避免单点技术栈绑定。

### 7.2 为什么使用 RabbitMQ，坚决不使用 Redis 作为队列？
- **考量方案**：使用 Redis List / Streams 作为后台任务队列。
- **决策理由**：Redis 是基于内存的缓存存储，在机器宕机或内存压力下容易发生数据淘汰（Eviction）或持久化丢包。RabbitMQ 具备完备的死信队列（DLX）、消息持久化确认（Message Acknowledgement）、排他消费与背压（Prefetch）机制，能够确切保证文档摄取任务“不丢失、不重复执行”。

### 7.3 为什么用真实容器验收，而不是大面积 Mock 单元测试？
Mock 单测能证明"我按自己理解的方式调用了依赖"，证明不了"PostgreSQL 真的接受了这条约束、Qdrant 真的把这条向量检索出来、RabbitMQ 真的把这条消息送达了"。本平台的业务不变量恰恰长在那些边界上：复合外键、行号坐标、门控阈值、租约认领、引用回表。

因此验证集中在容器路径上：镜像构建 → 一次性迁移 → 四个服务 healthy → nginx 单一入口上的真实响应 → 一次真实问答。代价是需要真实外部服务与更长的反馈周期；收益是"检查通过"与"上线能用"之间的距离更短。平台不保留探针脚本套件，避免留下一套只在自己机器上通过的测试资产。
## 8. Testing & Verification Strategy
两层：静态门禁（Ruff / format / Pyright strict / 架构方向 / goldenset 可复现性）保证代码自洽；运行时验收（`docker compose -f infra/compose.yaml --profile app up -d --build --wait` + `/health/ready` + `/api/v1/config` + 一次真实问答）保证系统可用。完整命令与各自能证明什么，见 `docs/development/testing-strategy.md`。没有第三层，也没有探针脚本。
## 9. Rollout, Migration & Deprecation Strategy

- **数据库迁移**：使用 Alembic 进行结构化模式管理。迁移脚本必须前向与后向兼容；
- **临时兼容与双写标记**：严禁无理由保留长期双写。若因数据平滑迁移必须存在临时双写，代码处必须注明：
  ```python
  # ponytail: migration until M<version> (#TICKET-ID)
  ```
  一旦迁移周期结束，必须执行硬删除，严禁残留 deprecated shim；
- **删除优于兼容**：系统内部重构时，旧路径必须直接删除，不在内部维护兼容适配层。

---

## 10. Open Questions & Future Work

1. **表格结构化跨页抽取优化**：超长跨页复杂商务费率表与付款里程碑表格的语义跨页粘合仍需在后续版本中探索更高级的版面拓扑缝合算法。
2. **合同红线对比（Redline Diffing）扩展**：预留对合同新旧修订版本的并排条款差异（Redline Diff）模型与可视化能力接入端口。
