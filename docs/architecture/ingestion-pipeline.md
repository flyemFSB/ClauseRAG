# 异步文档摄取流水线架构规范

## 流水线处理阶段 (Pipeline Stages)

文档上传后的处理链条严格按如下阶段推进：

```text
upload（上传完成）
  → parse（解析抽取与 Markdown 规范化）
  → chunk（Parent-Child 两级分块）
  → embed（批量向量化嵌入）
  → index（写入 pgvector 向量表与 pg_search BM25 索引）
  → ready（就绪态）
```

---

## 解析路由策略 (Parser Routing)

流水线根据文件扩展名与 MIME 类型自动路由至专用解析适配器：

| 文件扩展名 | 解析引擎路由 | 说明 |
| :--- | :--- | :--- |
| `.pdf` | `anydoc` 结构化提取；若识别到扫描页则降级路由至 PaddleOCR-VL | 支持混合版面自适应调度 |
| `.docx`, `.pptx`, `.xlsx` | `anydoc` 适配器 | 提取段落、层级标题与表格结构，转化为 GFM Markdown |
| `.html`, `.htm` | `html-to-markdown` 适配器 | 清洗无效样式标签并规范化输出 |
| `.txt`, `.md`, `.markdown` | UTF-8 原生解码并规范化 | 移除 UTF-8 BOM 头，其余编码直接报错拦截 |
| `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tif`, `.tiff` | PaddleOCR-VL 版面分析 | 提取 OCR 文本、识别表格并生成结构化 Markdown |
| 其余格式 | 显式拦截并置为 `manual_retry_required` | 避免未测试格式引发隐性故障 |

---

## 异步任务调度与容错设计 (ADR-0030)

1. **作业行为唯一事实源**：PostgreSQL 中的 `ingestion_jobs` 行是任务交付与状态流转的单一真相来源；RabbitMQ 仅充当轻量级“唤醒信号（Wake-up Hint）”，平台不依赖 RabbitMQ 消息做持久化重试。
2. **幂等认领与租约接管**：
   - 任务认领携带递增的 `attempt` 版本；
   - 若 Worker 进程因宕机超出 `JOB_STALE_AFTER_SECONDS` 租约期，后台调度器 `IngestionDispatch.reconcile()` 将安全收回租约并重新投递，已超时的僵尸任务写入被代际栅栏拦截。
3. **分类有界重试**：
   - 仅对可识别的瞬态异常（网络超时、429 限流、502/503 服务抖动）执行重试；
   - 重试采用带抖动的线性退避：$\min(\text{delay} \times \text{attempt}, \text{max\_delay})$，严格受控于 `JOB_MAX_ATTEMPTS`；
   - 格式损坏、非法参数等确定性错误直接置为终态（`manual_retry_required` 或对应阶段失败），严禁死循环重试。

---

## 向量化与集合索引 (Embedding & Indexing)

1. **向量嵌入服务**：通过 SiliconFlow 调用 `BAAI/bge-m3` 模型，生成 1024 维密集向量。系统显式限定批处理大小（`EMBEDDING_BATCH_SIZE`，默认 16），避免触发外部网关超时。
2. **向量表就地隔离**：
   - 业务切片统一录入 `child_chunk_embeddings`（一行对应一个子块，`vector(1024)` + HNSW cosine 索引）；
   - 表上只存 `child_id`、`knowledge_base_id`、`embedding_model` 与 `embedding`：正文、标题路径与行号一律回权威表读，不在这里再存一份；
   - `knowledge_base_id` 由 `child_chunks -> document_versions -> documents` 当场推导写入，不接受调用者传入的关联；子块删除时级联删除对应行，不需要跨存储对账。
3. **写入门控**：嵌入向量写入与作业状态写入扔在同一数据库，因此向量写入的 `INSERT ... SELECT` 里直接校验 `job_id`、`attempt`、`stage`、`status` 与租约是否仍属于本次尝试；不属于则匹配零行，写入成为空操作，由既有状态机照旧回报 SUPERSEDED/VANISHED。

---

## 交付与就绪门禁 (Verification Gates)

只有当解析产物、切片数据、BM25 关键词索引与 pgvector 向量全部持久化落库后，文档版本才标记为 `ready`：
- 解析阶段生成的 Markdown 制品及元数据（页数、行数、警告信息）持久化至 `parse_artifacts` 表与对象存储；
- 失败时严格记录 `error_class` 与错误摘要，支持控制台一键手动重试。
