# 数据流与领域模型契约

## 领域实体层级

```text
User（用户）
  └─ KnowledgeBase（知识库）
       └─ Document（逻辑文档）
            └─ DocumentVersion（文档物理版本）
                 ├─ ParseArtifact（解析 Markdown 制品）
                 ├─ ParentChunk（父切片，生成上下文）
                 │    └─ ChildChunk（子切片，检索与引用锚点）
                 └─ IngestionJob（摄取流水线作业）

Conversation（会话）
  └─ Message（消息）
       └─ AgentRun / Citation（推理运行状态 / 条款引用）
```

---

## 文档版本生命周期状态机

```text
uploaded（已上传）
  → parsing（解析中）
  → parsed（解析完成）
  → chunking（分块中）
  → embedding（向量化中）
  → indexing（索引构建中）
  → ready（就绪可检索）
```

异常与终态枚举：
- `parse_failed`（解析失败）
- `chunk_failed`（分块失败）
- `embedding_failed`（向量化失败）
- `index_failed`（索引构建失败）
- `manual_retry_required`（需人工介入重试，如确定性格式不支持）

---

## 存储制品路径布局（不可变规范）

```text
raw/{document_version_id}/original.{ext}
parsed/{document_version_id}/{job_id}/attempt-{n}/document.md
chunks/{document_version_id}/{job_id}/attempt-{n}/chunks.jsonl
```

- 对象存储中所有制品 Key 均具备**严格不可变性（Immutable）**，数据库事实行为唯一指针：`document_versions.source_object_key`、`parse_artifacts.markdown_object_key`。
- 派生制品携带认领任务的唯一标识（`job_id` 与 `attempt` 重试序号）。即使旧任务租约超时被接管，迟到的写入也绝不会覆盖新尝试生成的制品文件。
- 业务系统严禁由客户端或上层逻辑拼接拼装 Key，全部遵循数据库行指针反查。

---

## Parent-Child 双层切分模型

- **Parent Chunk（父切片）**：约 1024–2048 tokens，基于 Markdown 标题树（Article/Section）、段落或表格边界切分，保留完整的法律上下文与商业逻辑，专供生成提示词上下文填充。
- **Child Chunk（子切片）**：约 256–512 tokens（带 32 tokens 滑动重叠），作为向量嵌入与倒排索引的原子单元，作为检索召回与引用定位的唯一权威锚点。
- **职责分离**：Child 负责检索匹配与精准行号坐标定位；Parent 聚合后提供语义上下文输入大模型。

---

## 核心元数据规范

### DocumentVersion（文档版本）
`id`, `document_id`, `version_ordinal`, `status`, `mime_type`, `checksum`, `size_bytes`, `source_object_key`, `created_at`, `updated_at`

### ParseArtifact（解析制品）
`markdown_object_key`, `parser_name`, `parser_version`, `page_count`, `warnings`

### ParentChunk（父切片）
`parent_id`, `document_version_id`, `heading_path`, `ordinal`, `content`, `token_count`

### ChildChunk（子切片）
`child_id`, `parent_id`, `document_version_id`, `heading_path`, `block_type`, `ordinal`, `line_start`, `line_end`, `content`, `token_count`

> 向量库 Payload 中仅存储与过滤相关的核心元数据（如 `document_version_id`, `knowledge_base_id`），不重复冗余存储整篇正文或解析日志；详细原文统一回表 PostgreSQL 或对象存储解析。

---

## 引用提示词注入协议

模型在提问提示词中仅感知局部短标识（Request-local IDs）：

```text
[source:S1]
Document: Master_Services_Agreement.pdf
Heading: Article 8 > Limitation of Liability
Content: ...        (所属父切片聚合的上下文正文)
Passage: ...        (命中的子切片切片原文，对应行号区间)
[/source:S1]
```

- 大模型在生成回复时仅允许输出 `[S1]` 标记。
- 服务端校验节点严格核验该标识是否位于本次检索通过的证据候选集中，并由后端回表提取绝对行号（`line_start`–`line_end`）与真实原文（`quote`），杜绝模型编造。
- 同一父切片下命中多个子切片时，其段落上下文仅在首个 `[source:Sn]` 中输出一次，后续子块采用引用指向，避免提示词上下文预算无谓膨胀（ADR-0031）。

---

## 数据库事务与外部操作边界

1. **短事务原则**：创建文档版本及摄取作业行必须在单一短暂的 PostgreSQL 事务内完成。
2. **I/O 隔离**：外部文件上传（S3/RustFS）、外部模型调用（PaddleOCR、SiliconFlow）和向量操作（Qdrant）严格禁止包裹在数据库事务中。
3. **状态单向推进**：流水线每个阶段独立提交事务更新状态与制品指引；RabbitMQ 消息仅在本地事务完全提交后才予以确认（Ack）。

---

## 核心数据库模式表清单

- 资源归属：`knowledge_bases.owner_id`, `conversations.owner_id`（平台单主体，无账号表；ADR-0033）
- 知识库与文档：`knowledge_bases`, `documents`, `document_versions`, `parse_artifacts`
- 切片与制品：`parent_chunks`, `child_chunks`, `cleanup_intents`
- 任务流水线：`ingestion_jobs`
- 会话与审查：`conversations`, `messages`
- LangGraph 检查点表由库独立托管，不纳入业务 Alembic 迁移脚本。
