# 系统总体架构设计规范

## 目标与边界

本规范定义 ClauseRAG 的生产级架构边界、依赖方向、数据归属、摄取与检索流水线、运行时装配及核心不变量。

系统支持 PDF、DOCX、PPTX、XLSX、TXT、HTML、扫描图像与 Markdown 格式解析；具备文档版本管理、RustFS/S3 不变制品存储、AnyDoc/html-to-markdown/PaddleOCR-VL 自动路由、Parent-Child 切分树、SiliconFlow BGE-M3 密集向量检索（pgvector HNSW）、pg_search BM25 关键词检索、BGE-Reranker-v2-m3 重排、LangGraph 有界 Agent 图推理、端到端权威引用校验与 SSE 流式输出。

---

## 运行时拓扑 (Runtime Topology)

```text
React 19 前端 (Vite+ / vp)
        │ HTTP / SSE
        ▼
FastAPI + LangGraph Agent 运行时 (端口 8001: 会话、流式推流、检索诊断)
FastAPI 业务 API 服务 (端口 8000: 认证、知识库、文档管理、作业监控)
        │
        ├── ParadeDB (PostgreSQL 18)：业务数据、版本、切片、任务状态、会话与检查点；
        │   pgvector HNSW 向量索引 (`child_chunk_embeddings`) 与 pg_search BM25 索引 (`child_chunks`)
        ├── RustFS / S3：原始文档与不可变解析制品 (Markdown / Chunks)
        └── Langfuse：端到端可观测性跟踪

RabbitMQ 消息队列 (唯一业务队列: taskiq.tasks) ──► Taskiq 后台 Worker 集群
```

---

## 依赖单向性规范 (Dependency Direction)

严格遵循整洁架构依赖原则，依赖单向向内：

```text
api ────────────────► application ────────────────► domain
worker ─────────────► application
infrastructure ─────► application 端口协议与 domain 模型
composition ────────► 具体实例依赖注入与进程装配
```

- **`domain` 纯粹性**：严禁导入 FastAPI、SQLAlchemy、pgvector、LangChain、RabbitMQ、S3 等任何外部基础设施依赖。
- **业务内聚**：`application` 按业务领域划分（`identity/`, `knowledge/`, `ingestion/`, `retrieval/`, `conversations/`, `cleanup/`, `agent/`）。
- **外部隔离**：`infrastructure` 按外部系统组织（`db/`, `providers/`, `storage/`, `queue/`, `parsing/`, `config/`）。
- **硬性约束**：严禁创建 `utils`、`helpers`、`common`、`misc`、`manager` 等模糊命名的垃圾模块，CI 中通过 `scripts/check-architecture.py` 自动化拦截。

---

## 核心领域高内聚模块 (Deep Module Interfaces)

### 1. DocumentCatalog（文档资产管理）
统一收敛文档上传、校验、哈希、版本递增、元数据持久化及删除意图调度：
```python
class DocumentCatalog:
    async def upload(
        self, *, owner_id: UUID, knowledge_base_id: UUID,
        document_id: UUID | None, filename: str, content: BinaryIO,
    ) -> DocumentUpload: ...

    async def get_document(self, *, owner_id: UUID, document_id: UUID) -> DocumentDetail: ...
    async def list_documents(self, *, owner_id: UUID, knowledge_base_id: UUID) -> Sequence[DocumentSummary]: ...
    async def delete_document(self, *, owner_id: UUID, document_id: UUID) -> None: ...
    async def retry_parse(self, *, owner_id: UUID, document_version_id: UUID) -> ParseRetry: ...
```

### 2. DocumentIngestion（流水线调度执行）
统一封装任务认领、阶段分发、超时控制、故障分类与下一阶段推进：
```python
class DocumentIngestion:
    async def run_stage(
        self, *, stage: IngestionStage, document_version_id: UUID, job_id: UUID,
    ) -> IngestionResult: ...
```
各阶段（`_parse`, `_chunk`, `_embed`, `_index`）均为内部受保护函数，不暴露多余抽象。

### 3. RetrievalService（一体化检索服务）
对外提供单一检索入口，收敛双通道并发、RRF 融合、重排、门控裁决与上下文组装：
```python
class RetrievalService:
    async def retrieve(
        self, *, knowledge_base_id: UUID, query: str, rewritten_queries: Sequence[str] = (),
    ) -> RetrievalResult: ...
```

### 4. ConversationAgent（对话执行）
封装 LangGraph 状态机流式执行，向上层 HTTP 暴露统一事件流：
```python
class ConversationAgent:
    async def run(
        self, *, conversation_id: UUID, user_id: UUID, question: str,
    ) -> AsyncIterator[AgentEvent]: ...
```

---

## 进程装配与生命周期 (Process Composition)

各进程按需组装自身依赖，杜绝全局通用容器：
- `composition/api/runtime.py`：构建业务 API 运行时（数据库池、对象存储、认证、健康探针）；
- `composition/agent/runtime.py`：构建 Agent 运行时（检索协作器、LLM 客户端、检查点池、链路追踪）；
- `composition/worker/runtime.py`：构建后台 Worker（解析器、向量化客户端、pgvector 索引适配器、RabbitMQ 消费者、租约调度器）；
- `composition/cli/runtime.py`：构建 CLI 工具链。

---

## 数据所有权与系统不变量 (Data Invariants)

1. **唯一事实源**：PostgreSQL 是所有业务数据、版本、切片、任务和会话事实的唯一来源。
2. **消息体瘦身**：RabbitMQ 消息仅传递资源 ID，严禁传递文件内容、Markdown 或切片明细。
3. **条件认领与租约栅栏**：任务通过条件数据库写认领（基于状态与尝试次数代际隔离），超时租约被回收后迟到的旧任务无法提交结果。
4. **事务与网络 I/O 隔离**：外部 HTTP 与 S3 调用严格禁止包裹在数据库事务中；向量写入与业务事实现已同库，它们的约束是相反的那一条：近似检索、租户过滤与引用回表必须各自独立会话，不共享事务与可变会话。
5. **有限重试与取消保护**：重试仅针对已分类的瞬态失败；严禁吞没 `asyncio.CancelledError`。
6. **双通道融合与双层切分**：
   - Dense 与 Keyword 双通道由应用层 RRF 融合；
   - Child 切片承担向量检索与行号锚定；Parent 切片提供生成提示词上下文。
7. **权威引用校验**：服务端逐条核验模型输出的引用标记，依据存储制品解析绝对行号与原文片段，模型无权伪造引用。