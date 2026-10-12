# 系统分阶段实施与交付蓝图

## Phase 0：工程脚手架与运行时基线
- 规范化 `backend/`、`frontend/`、`infra/`、`docs/` 分层架构与目录树；
- 锁定 Python 3.12 与 Node 24 基础环境；
- 生成并权威锁定 `uv.lock` 与 `frontend/pnpm-lock.yaml`；
- 编排 `infra/compose.yaml` 本地中间件拓扑；
- 实现强类型配置校验、结构化日志与 `/health/*` 就绪探针。

---

## Phase 1：租户认证、知识库管理与对象存储上传
- 实现基于 Argon2id 的会话认证体系（HttpOnly Cookie）；
- 构建 `users`、`knowledge_bases`、`documents`、`document_versions` 与 `ingestion_jobs` 数据模型；
- 实现流式直传至 RustFS 对象存储与不可变指针记录；
- 交付文档与版本管理核心 REST 接口及前端接入契约。

---

## Phase 2：多源异构解析与 Markdown 规范化
- 实现基于扩展名与 MIME 类型的自适应解析路由器；
- 封装 AnyDoc、html-to-markdown 与 PaddleOCR-VL 版面分析适配器；
- 生产标准化不可变 Markdown 制品与页码/行号映射元数据；
- 建立确定性格式拦截与人工介入重试状态机。

---

## Phase 3：Parent-Child 两级分块与密集向量索引
- 实现感知 Markdown 标题树与段落边界的两级切分引擎；
- 建立 PostgreSQL `parent_chunks` 与 `child_chunks` 存储关系；
- 接入 SiliconFlow `BAAI/bge-m3` 向量嵌入生成（1024 维）；
- 构建 `child_chunk_embeddings` 表、pgvector HNSW cosine 索引与 pg_search BM25 索引，并实现版本向量核验与写入门控。

---

## Phase 4：Agentic RAG 检索与有界状态机推理
- 构建 LangGraph 有界 Agent 状态图（最多 2 轮改写重试）；
- 实现 pgvector Dense 密集向量与 pg_search BM25 关键词双通道并发检索；
- 应用层 RRF 倒数排名融合与 SiliconFlow `BAAI/bge-reranker-v2-m3` 精排；
- 接入动态证据门控（`sufficient` / `degraded` / `insufficient`）与主动弃答机制；
- 落地端到端引用强校验协议与 SSE 流式推流。

---

## Phase 5：全链路可观测性与追踪
- 集成 Langfuse v4 技术栈（复用底层 PG、Redis、RustFS 并独立 ClickHouse）；
- 实现 LLM 调用消耗、Prompt 模板、检索召回排名与门控决策的全链路追踪；
- 交付 `python -m cli observability-init` 自动化初始化命令。

---

## Phase 6：双工作区前端交付与运维工具链
- 实现合同审查工作区（审查岛屿、流式打字机、引用 Popover 与证据检视台）；
- 实现法务资产管理台（知识库概览、文档流水线监控、单轮检索诊断调试、系统设置）；
- 落地前端代际栅栏（Generation Fence），杜绝异步竞态；
- 交付运维 CLI（`schema-init` / `schema-reset` / `storage-init` / `reindex` 等）作为本地与部署的统一入口。

---

## Phase 7：真实容器全业务闭环终验
- 功能全部就绪后，一条命令完成构建、迁移、启动与健康等待：`docker compose -f infra/compose.yaml --profile app up -d --build --wait`；
- 在 nginx 单一入口上验证核心业务场景（`/health/ready`、`/api/v1/config`，加一次真实文档问答），验收结论以响应原文为准。
