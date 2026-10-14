# 前后端交互协议与接口契约规范

## 前端工程基线

- **运行时环境**：Node.js 24 + pnpm 12。
- **工具链**：以 Vite+ CLI（`vp`）为核心命令接口（`vp dev`, `vp check`, `vp build`, `vp test`）。
- **组件栈**：React 19 + TypeScript 严格模式 + TanStack Router / TanStack Query + Base UI + `lucide-react`。
- **服务端状态管理**：全权由 TanStack Query 接管，严禁在全局状态树中双写缓存数据。

---

## 协议与数据传输规范

1. **统一路由前缀**：所有业务接口以 `/api/v1` 为基础路径。
2. **数据编码规范**：请求与响应体均采用 UTF-8 编码的 JSON 格式（`application/json`）；文件上传接口采用 `multipart/form-data`。
3. **时间戳规范**：所有时间戳均为 ISO-8601 UTC 格式，带 `Z` 后缀（如 `2026-10-02T08:35:19.232693Z`）。
4. **认证方式**：无。平台以展示为目的上线，不提供登录（ADR-0033）：没有登录页、没有会话 Cookie，前端请求不携带任何凭据，服务端也没有可校验的身份。
5. **安全与隔离设计**：
   - 全部资源都属于同一个平台主体（`PLATFORM_OWNER_ID`），因此平台内部没有跨用户的权限边界；可访问到这个地址的人可以读、改、删平台内的全部内容。
   - 不存在与不可读（包括标识符格式错误）**统一返回 404**（`{"detail": "<resource> <id> not available"}`），不会用 500 或 403 泄露资源是否存在。
6. **请求体大小限制**：超出 `MAX_UPLOAD_BYTES` 的请求直接在入口拦截并响应 `413 Payload Too Large`。

---

## 核心接口分类详述

### 1. 知识库管理接口 (Knowledge Bases)

| 方法 | 路径 | 请求体 | 成功响应 | 错误码 |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/knowledge-bases` | `{name, description?}` | `201` 知识库对象 | `422` |
| `GET` | `/knowledge-bases` | 无 | `200` 知识库列表（按创建时间倒序） | `422` |
| `GET` | `/knowledge-bases/{id}` | 无 | `200` 知识库详情 | `404` |
| `PATCH` | `/knowledge-bases/{id}` | `{name?, description?}` | `200` 更新后的知识库 | `404`, `422` |
| `DELETE`| `/knowledge-bases/{id}` | 无 | `204` 级联删除文档、切片及对象存储资产 | `404` |

### 3. 文档与流水线接口 (Documents, Versions & Jobs)

| 方法 | 路径 | 说明 | 成功响应 | 错误码 |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/knowledge-bases/{id}/documents` | Multipart 上传：`file`, 可选 `document_id` | `201` `{document, version, job}` | `400`（空文件）, `404`, `413`（超大）, `415`（不支持后缀）, `422`, `502` |
| `GET` | `/knowledge-bases/{id}/documents` | 获取知识库下文档列表 | `200` 文档概览列表（含最新版本状态） | `404` |
| `GET` | `/documents/{id}` | 文档详情及版本历史 | `200` 文档详情（版本由新到旧） | `404` |
| `DELETE`| `/documents/{id}` | 删除逻辑文档 | `204` 级联软删除并在后台异步清理实体 | `404` |
| `GET` | `/document-versions/{id}` | 文档单版本详情 | `200` 版本信息与解析制品摘要 | `404` |
| `GET` | `/document-versions/{id}/jobs` | 版本的作业历史 | `200` 摄取作业数组 | `404` |
| `GET` | `/ingestion-jobs/{id}` | 作业单条状态 | `200` 作业详情 | `404` |
| `POST` | `/document-versions/{id}/retry`| 触发重试 | `200` 追加生成的新作业实例 | `404`, `409` |

- **支持文件后缀**：`.pdf`, `.docx`, `.pptx`, `.xlsx`, `.txt`, `.md`, `.markdown`, `.html`, `.htm`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tif`, `.tiff`。
- 上传时若携带 `document_id`，则为该既有文档追加新版本（单调自增版本号）；不传则新建文档。

---

## 合同审查问答与流式接口 (Agent Runtime)

合同审查相关接口由独立的 Agent 运行时进程（端口 8001）承载：

### 1. 会话生命周期

| 方法 | 路径 | 请求体 | 成功响应 | 错误码 |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/knowledge-bases/{id}/conversations` | `{title?}` | `201` 会话对象（title 默认“新对话”） | `404`, `422` |
| `GET` | `/conversations` | 无 | `200` 会话列表（活跃时间倒序） | — |
| `GET` | `/conversations/{id}` | 无 | `200` 会话详情与完整消息历史（正序） | `404` |
| `PATCH` | `/conversations/{id}` | `{title}` | `200` 更新后的会话 | `404`, `422` |
| `DELETE`| `/conversations/{id}` | 无 | `204` 级联清理会话、消息与引用快照 | `404` |

### 2. 流式问答推流 (SSE Stream)

- **路径**：`POST /conversations/{id}/messages`
- **请求体**：`{"content": "请分析协议第8条的责任上限与免责除外情形"}`
- **响应头**：`Content-Type: text/event-stream; charset=utf-8`

#### 流式事件序列定义

| 事件类型 (`event`) | 载荷字段 (`data`) | 触发时机与语义 |
| :--- | :--- | :--- |
| `run_started` | `{schema_version, run_id, conversation_id, user_message_id, assistant_message_id}` | 首帧事件，在调用外部模型前触发 |
| `answer_delta` | `{schema_version, text}` | 回答文本增量片段 |
| `citation` | `{schema_version, citation_id, document_id, document_version_id, document_name, parent_id, child_id, heading_path, line_start, line_end, quote}` | 回答生成后，逐条推送经服务端校验通过的权威引用 |
| `run_completed` | `{schema_version, message_id, answer, citations, evidence_status, retrieval_rounds, intent, finish_reason, removed_citation_ids}` | 正常终态，携带最终完整答复与门控裁决状态 |
| `run_failed` | `{schema_version, message_id, error_class, message}` | 异常失败终态，携带明确的错误类型与诊断信息 |
| `run_cancelled` | `{schema_version, message_id, answer}` | 客户端主动取消或代际推进时的取消终态 |

---

## 检索诊断调试接口 (Retrieval Debug)

- **路径**：`POST /retrieval-debug/query`
- **请求体**：`{"knowledge_base_id": "...", "query": "违约赔偿责任限制"}`
- **响应**：单轮真实检索评测报告，不落库、不调用大模型生成答案：
  - `queries`：本轮实际执行的查询变体（已 trim、去空、按顺序去重；全部为空时回退到原问题）；
  - `channels`：Dense 与 Keyword 双通道各自召回候选、原始分值、延迟与通道健康状态（`ok`/`empty`/`failed`）；
  - `fused`：RRF 倒数排名融合得分及各通道排名快照；
  - `rerank`：BGE-Reranker-v2-m3 二次精排分数分布与打分耗时；
  - `evidence`：证据门控裁决结果（`sufficient`/`degraded`/`insufficient`）；`degraded` 表示重排不可用、证据质量无法核验，此时 `accepted` 恒为空且该轮直接弃答，不得当作可生成；
  - `context_sources`：组装输入提示词的切片列表、行号区间及真实原文。
