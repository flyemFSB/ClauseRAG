# 后端开发规范与工程准则

## 工具链标准

- **Python 版本**：强制采用 `>=3.12,<3.13`。
- **依赖管理**：以 `uv` 为唯一包管理器，提交并严格锁定 `uv.lock`。
- **静态质量门禁**：采用 Ruff（格式化、导入排序与 Lint 检查）与 Pyright（Strict 严格模式，保持 0 errors / 0 warnings）。
- **编码风格**：遵循 PEP 8 与 Pythonic 风格。

---

## 架构与分层边界

- **模型分层隔离**：API 契约模型（Pydantic Schemas）、领域实体模型（Domain Models）、持久化映射（ORM Models）、外部供应商载荷及 LangGraph 状态严格隔离，禁止跨层泄漏。
- **Domain 纯粹性**：领域层严禁引入 FastAPI、SQLAlchemy、pgvector、LangChain、RabbitMQ 等任何外部框架依赖。
- **薄 API 路由**：API 接口仅负责请求参数校验、鉴权、调用 Application 业务服务并序列化返回响应。
- **薄适配器**：Infrastructure 适配器遵循极简原则，优先使用依赖的原生 API。
- **命名规范**：严禁创建 `common`、`shared`、`utils`、`helpers`、`BaseManager` 等职责不清的垃圾文件。

---

## 并发控制与故障处理

- **有界超时**：所有外部网络 I/O（HTTP、RabbitMQ、S3）必须显式配置有界超时，严禁无限等待；数据库侧的 ANN 扩扫用 `HNSW_MAX_SCAN_TUPLES` 给出同样的上界。
- **保护取消链**：**绝对禁止吞没 `asyncio.CancelledError`**，保障请求中止时资源即时回收。
- **结构化并发**：优先使用 `asyncio.TaskGroup` 与 `asyncio.timeout`。
- **禁止共享 Session**：严禁跨并发协程或并行任务共享同一个 SQLAlchemy `AsyncSession`。
- **资源清理**：响应体、会话连接、分布式锁与 HTTP 客户端必须在 `finally` 块或生命周期钩子中显式释放。
- **显式降级**：服务降级必须具备清晰的领域状态表达，严禁将外部依赖异常静默吞没为空成功。

---

## 事务与异步任务

- **禁止事务跨网络调用**：严禁在未提交的数据库事务中调用外部网络接口（LLM API、OCR 或对象存储）。
- **消息确认时机**：RabbitMQ 消息仅在本地事务成功提交且外部副作用完成后才进行确认（Ack）。
- **任务轻量与幂等**：Worker 任务必须具备幂等性，消息体仅传递资源 ID，不传递大文本或文件内容。
- **唯一事实源**：PostgreSQL 是任务状态的唯一真相来源，RabbitMQ 仅作为异步传输信道。
- **删除优于兼容**：重构时直接硬删除废弃代码，严禁保留长期兼容适配层或无期限双写。

---

## RAG 检索与生成准则

- **Parent-Child 分工**：Child 切片用于检索匹配与引用锚定；Parent 切片用于组装回答上下文。
- **指标作用域**：通道得分、排名、RRF 融合及重排分数均为单次请求内的上下文数据，不作为静态切片元数据落库。
- **证据门控先行**：检索候选必须通过证据门控（Evidence Gate）质量裁决后，方可调用模型生成答复。
- **权威引用防伪**：大模型仅输出引用标记，由后端统一核验并解析行号区间与真实原文切片。
