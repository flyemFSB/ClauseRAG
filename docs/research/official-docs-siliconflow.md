# 官方文档核对：SiliconFlow API（Official docs cross-check）

日期：2026-10-02 · 抓取方式：`Invoke-WebRequest`（PowerShell 7），原始 HTML/文本存于 `.probe\sf\`
（`.probe/` 已 gitignore）。本文件只记录**官方文档声明**；与**本机实测**的差异在每节末尾单列。

> 状态说明：首轮实测时账户欠费，所有推理端点都返回 402（见 §2/§3 的历史记录）；账户恢复后
> embeddings 与 rerank 已重测为 HTTP 200，结论已回填到 §2/§3 与 `probes/siliconflow-contract.md`。
> chat / SSE / 结构化输出 / function calling（§4–§7）**仍只有文档依据**，尚未重测（属 Phase 4/5 范围）。

## 来源页面（全部 HTTP 200 抓取）

| 主题 | URL |
|---|---|
| 创建嵌入请求 | <https://docs.siliconflow.cn/docs/api/embeddings-post> |
| 创建重排序请求 | <https://docs.siliconflow.cn/docs/api/rerank-post> |
| 获取用户模型列表 | <https://docs.siliconflow.cn/docs/api/models-get> |
| 创建对话请求（OpenAI） | <https://docs.siliconflow.cn/docs/api/chat-completions-post> |
| 流式输出 | <https://docs.siliconflow.cn/docs/userguide/capabilities/stream-mode> |
| JSON 模式 | <https://docs.siliconflow.cn/docs/userguide/guides/json-mode> |
| Function Calling | <https://docs.siliconflow.cn/docs/userguide/guides/function-calling> |
| Rate Limits | <https://docs.siliconflow.cn/docs/userguide/faqs/rate-limit-and-upgradation> |
| API 请求错误排查 | <https://docs.siliconflow.cn/docs/userguide/faqs/error-code> |

Base URL（文档示例）：`https://api.siliconflow.cn/v1`。鉴权：请求头 `Authorization: Bearer <API Key>`。
平台追踪：请求可带 `X-Trace-Id` / `traceparent`；响应头回 `x-siliconcloud-trace-id`。

---

## 1. `GET /v1/models`（获取用户模型列表）

官方原文要点：
- Query：`type` ∈ {`text`,`image`,`audio`,`video`}；`sub_type` ∈ {`chat`,`embedding`,`reranker`,`text-to-image`,`image-to-image`,`speech-to-text`,`text-to-video`}。
  > "模型子类型。您可以使用它来单独筛选模型，而无需设置 type。"
- 200 响应体（官方示例）：
  ```json
  { "object": "list", "data": [ { "id": "deepseek-ai/DeepSeek-V4-Flash", "object": "model", "created": 0, "owned_by": "" } ] }
  ```
- cURL 示例：`curl --request GET --url 'https://api.siliconflow.cn/v1/models?sub_type=chat' -H 'Authorization: Bearer YOUR_API_KEY'`

**本机实测**：HTTP 200，`object=list`，**97** 个模型；`sub_type=embedding`→8，`reranker`→6，`chat`→64；`type=text`→81。
条目形状与官方示例一致（`id/object/created/owned_by`）。`BAAI/bge-m3`、`BAAI/bge-reranker-v2-m3` 均在列。

---

## 2. `POST /v1/embeddings`（创建嵌入请求）

官方原文要点：
- `model` string **required**；`input` string | array **required**。
  > "输入文本必须以字符串或字符串数组的形式提供。要在单次请求中处理多个输入，请传递字符串数组。输入长度不得超过模型的最大上下文 token 限制，且不应为空字符串。"
- 各模型最大输入 token：
  > "BAAI/bge-large-zh-v1.5, BAAI/bge-large-en-v1.5, netease-youdao/bce-embedding-base_v1: 512"
  > "BAAI/bge-m3, Pro/BAAI/bge-m3: 8192"
  > "Qwen/Qwen3-Embedding-8B, Qwen/Qwen3-Embedding-4B, Qwen/Qwen3-Embedding-0.6B: 32768"
- `encoding_format` string，∈ {`float`,`base64`}，**Default "float"**。
- `dimensions` integer：
  > "输出嵌入向量的维度数。仅 Qwen/Qwen3 系列支持。"
  取值：8B → [64,128,256,512,768,1024,1536,2048,2560,4096]；4B → [64…2560]；0.6B → [64…1024]。
- 其他字段：`user`（追踪/限流）、`truncate` ∈ {`left`,`right`}（超长截断方向）。
- 另有 VL 变体（`Qwen/Qwen3-VL-Embedding-8B`），`input` 支持 `{"text":...}` / `{"image":...}` / 混合列表。
- 200 响应体（官方 schema）：
  ```json
  { "object": "list", "model": "string",
    "data": [ { "object": "embedding", "embedding": [0], "index": 0 } ],
    "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 } }
  ```
  即 `data[]` 元素仅含 `object`/`embedding`/`index` 三个键，**未列 `sparse`/`lexical` 字段**。
- 错误状态：400 401 403 404 429 503 504；400 错误体 schema：`{"code": 20012, "message": "string", "data": "string"}`。

**本机实测（2026-10-02，账户恢复后重跑）**：`POST /v1/embeddings` 返回 **HTTP 200**。
- `data[]` 长度 == `input` 条数（实测 2 条输入 → 2 条结果），`data[i].index` 为 0..n-1；
- `data[0]` 的全部键 = `embedding`、`index`、`object`（**没有** `sparse`/`lexical` 字段 → dense-only 成立）；
- `BAAI/bge-m3` 的 `embedding` 长度 = **1024**（官方文档未给这个数字，只能实测）；
- `usage` = `{prompt_tokens, completion_tokens, total_tokens}`（实测 `{28, 0, 28}`），与官方 schema 一致；
- 顶层键 = `object, data, model, usage`。

**文档缺口（如实记录，实测补足）**：embeddings 页**未给出** `input` 数组的条数上限，也**未给出**
`BAAI/bge-m3` 的输出维度。可推得的只是每条文本的 token 上限（BGE-M3 = 8192，见上）。因此
**批量条数上限：文档未给**；本项目不靠猜测，而是用配置 `RAG_EMBEDDING_BATCH_SIZE`（默认 16）
自己界定“一次 provider 请求带多少条文本”，并把这个选择连同理由写进 ADR-0019。
维度则由实测固定为 1024，写进 `RAG_EMBEDDING_DIMENSION` 与 ADR-0011。

---

## 3. `POST /v1/rerank`（创建重排序请求）

官方原文要点：
- `model` required（示例 `BAAI/bge-reranker-v2-m3`）；`query` string required，> "长度必须 ≥ 1"。
- `documents` string | array required，> "至少需要 1 个文档。"（支持纯字符串或 `{"text":...}`）。
- `instruction`：> "仅 Qwen/Qwen3-Reranker-8B、Qwen/Qwen3-Reranker-4B、Qwen/Qwen3-Reranker-0.6B 支持。"
- `top_n` integer：> "返回的最相关文档或索引数量。必须 ≥ 1。"（Range `1 <= value`）
- `return_documents` boolean：> "如果为 false，响应中不包含文档文本；如果为 true，则包含输入文档文本。默认值为 false。"
- `max_chunks_per_doc`：> "仅 BAAI/bge-reranker-v2-m3、Pro/BAAI/bge-reranker-v2-m3、netease-youdao/bce-reranker-base_v1 支持此字段。必须 ≥ 1，默认值为 1024。"
- `overlap_tokens`：> "必须在 0 到 80 之间。"（同上三模型支持）
- 200 响应体（官方示例）：
  ```json
  { "id": "rerank-20240115-abc123def456",
    "results": [ { "index": 1, "document": { "text": "深度学习是机器学习的子集..." }, "relevance_score": 0.85 } ],
    "meta": { "tokens": {"input_tokens":150,"output_tokens":10,"image_tokens":0},
              "billed_units": {"input_tokens":150,"output_tokens":10,"image_tokens":0,"search_units":1,"classifications":0} } }
  ```
  即 `results` 按相关性分数**排序**，元素含 `index`/`document`/`relevance_score`（示例分数 0.85）。
- 错误状态：400 401 403 404 429 503 504；400 schema 同 `{"code":20012,...}`。

**本机实测（2026-10-02，账户恢复后重跑）**：`POST /v1/rerank` 返回 **HTTP 200**。
- `results[]` 元素键 = `index`、`document`、`relevance_score`，按 `relevance_score` **降序**排列；
- 实测分数（`query=混合检索是如何融合多路召回结果的？`，5 个候选，`top_n=3`）：
  `0.974393367767334`（索引 2，最相关的那条）、`0.000418916024500504`、`0.000301230873446912`；
  即分数落在 **[0, 1]**，且**并非**均匀分布——不相关的候选接近 0；
- `return_documents=false` 时 `document` 为 `null`，与官方说明一致；
- `top_n=3 < 5` 候选 → 返回 3 条。

**文档缺口**：未明确 `relevance_score` 的值域（是否 [0,1]）与 `top_n` 大于候选数时的确切行为；
实测支持“值域 [0,1]、降序”，`top_n > 候选数` 仍未测（Phase 4 用到时再补）。

---

## 4. `POST /v1/chat/completions`（创建对话请求，OpenAI 兼容）

官方原文要点：
- `model` required；`messages` array required；`stream` boolean（SSE，> "流式传输通常以 `data: [DONE]` 结束"）。
- 采样/生成参数：`max_tokens`、`temperature`(≤2)、`top_p`(≤1)、`top_k`(≤100)、`frequency_penalty`(-2..2)、`n`、`stop`(最多 4 个)。
- 推理相关：`enable_thinking`、`thinking_budget`(128..32768)、`reasoning_effort` ∈ {`high`,`max`}。
- **`response_format`**：Text | JSON schema | JSON object。
  > "设置为 `{ "type": "json_schema", "json_schema": {...} }` 可启用结构化输出（Structured Outputs），确保模型匹配你提供的 JSON schema。"
  > "设置为 `{ "type": "json_object" }` 可启用较早的 JSON 模式，确保模型生成的消息是有效的 JSON。对于支持 json_schema 的模型，建议优先使用 json_schema。"
  > "请注意，如果没有系统或用户消息指示模型生成 JSON，模型将不会生成 JSON。"（json_object 分支）
- **`tools`** array：
  > "模型可能调用的工具列表。目前仅支持函数作为工具。… 最多支持 128 个函数。"
- 200 响应体（官方示例）：
  ```json
  { "id": "019bdaa55225ef854b320e9b838f77ce", "object": "chat.completion", "created": 1768899826,
    "model": "deepseek-ai/DeepSeek-V4-Flash",
    "choices": [ { "index": 0, "message": { "role": "assistant", "content": "你好！...", "reasoning_content": "..." }, "finish_reason": "stop" } ],
    "usage": { "prompt_tokens": 15, "completion_tokens": 1540, "total_tokens": 1555,
               "completion_tokens_details": {"reasoning_tokens":1190},
               "prompt_tokens_details": {"cached_tokens":0},
               "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 15 },
    "system_fingerprint": "" }
  ```
- 错误状态：400 401 403 404 429 503 504。

**本机实测**：`POST /v1/chat/completions`（非流式、流式、json_object、json_schema、tools）全部返回 **HTTP 402**（账户欠费）。
SSE 帧形状、结构化输出与 function calling 的实测支持均 **UNVERIFIED**。

**文档缺口**：chat 页未列出“哪些模型支持 `json_schema` / `tools`”（JSON 模式页只泛称“除 VL 外主要语言模型均已支持 JSON 模式”，function calling 页指向“模型广场”）。

---

## 5. 流式输出（SSE）

官方原文要点（<https://docs.siliconflow.cn/docs/userguide/capabilities/stream-mode>）：
- 请求体 `stream: true`；用 `requests` 时**还需** `requests.post(..., stream=True)`，否则不会按流式返回。
- 客户端逐行解析：> "`chunk.decode('utf-8').replace('data: ', '')` … if `chunk_str != "[DONE]"` … `chunk_data['choices'][0].get('delta', {})`"，
  取 `delta.content` 与 `delta.reasoning_content`。
- curl 需 `-N`（`--no-buffer`）避免缓冲。

**本机实测**：`stream=true` 在欠费时返回 HTTP 402 的普通 JSON（非 SSE），**未产生任何 `data:` 帧**。SSE 帧真实形状 **UNVERIFIED**。

---

## 6. JSON 模式 / 结构化输出

官方原文要点（<https://docs.siliconflow.cn/docs/userguide/guides/json-mode>）：
- 用法：请求加 `response_format={ "type" : "json_object" }`。
- 支持范围：> "现在，硅基流动的大模型 API 平台 SiliconFlow … 除了 VL 模型外，其他主要语言模型均已支持 JSON 模式。"
- 风险提示：> "你的应用必须检测并处理可能导致模型输出不完整 JSON 对象的边缘案例。" / "请合理设置 max_tokens，防止 JSON 字符串被中断。"
- `json_schema`（Structured Outputs）在 chat-completions 页描述，> "对于支持 json_schema 的模型，建议优先使用 json_schema。"

**本机实测**：json_object / json_schema 调用均返回 **HTTP 402**。实测支持情况 **UNVERIFIED**。

---

## 7. Function Calling

官方原文要点（<https://docs.siliconflow.cn/docs/userguide/guides/function-calling>）：
- REST 请求体加 `"tools": [ { "type":"function", "function": { "name":..., "description":..., "parameters": {...} } } ]`。
- > "该功能和 OpenAI 兼容，在使用 OpenAI 的库时，对应的请求参数中添加 tools=[对应的 tools]"。
- 响应侧读取：`response.choices[0].message.tool_calls[0].function.name` / `.arguments` / `.id`，回填 `{"role":"tool","content":...,"tool_call_id":...}`。
- 支持模型：> "可以通过模型广场查看当前支持 tools 的模型。"

**本机实测**：tools 调用返回 **HTTP 402**。实测支持与 `tool_calls` 结构 **UNVERIFIED**。

---

## 8. 错误码表（官方原文 + 实测对照）

官方原文（<https://docs.siliconflow.cn/docs/userguide/faqs/error-code>）：
> `400 ：参数不正确，请参考报错信息（message）修正不合法的请求参数；`
> `401 ：API Key 没有正确设置；`
> `402 ：账户欠费，请充值后重试；`
> `403 ：权限不够，最常见的原因是该模型需要实名认证，其他情况参考报错信息（message）；`
> `429 ：触发了 rate limits；参考报错信息（message）判断触发的是 RPM /RPD / TPM / TPD / IPM / IPD 中的具体哪一种`
> `504 / 503 ：… 对于对话和文本转语音请求，可以尝试使用流式输出（"stream" : true）…`
> `500 ：服务发生了未知的错误，可以联系相关人员进行排查`

API 手册给出的错误体样例：
- 400：`{ "code": 20012, "message": "string", "data": "string" }`
- 401：`"Invalid token"`
- 403：`"Forbidden"`
- 404：`"404 page not found"`
- 429：`{ "message": "Request was rejected due to rate limiting. If you want more, please contact contact@siliconflow.cn. Details:TPM limit reached.", "data": "string" }`
- 503：`{ "code": 50505, "message": "Model service overloaded. Please try again later.", "data": "string" }`
- 504：`"string"`

**本机实测**（与文档一致/差异）：
- 401 → 实测 `{"code":30014,"data":null,"message":"Token is invalid."}`（文档样例只写 `"Invalid token"`，实测是结构化 JSON，**补充信息**）。
- 402 → 实测 `{"code":30001,"message":"Sorry, your account balance is insufficient","data":null}`（文档只说“账户欠费”，**未给 code 30001**）。
- 400（模型名不存在）→ 实测 `{"code":20012,"message":"Model does not exist. Please check it carefully.","data":null}`，与文档 20012 schema 一致。
- 429 → **未证实**（无法安全触发）。

---

## 9. Rate Limits

官方原文要点（<https://docs.siliconflow.cn/docs/userguide/faqs/rate-limit-and-upgradation>）：
- 指标七种：RPM、RPH、RPD、TPM、TPD、IPM、IPD。
- 类别配额（当前指标）：
  | 类别 | 指标 | 数值 |
  |---|---|---|
  | 语言模型 (Chat) | RPM、TPM | RPM=1000-10000, TPM=50000-5000000 |
  | 向量模型 (Embedding) | RPM、TPM | RPM 2000-10000, TPM 500000-10000000 |
  | 重排序模型 (Reranker) | RPM、TPM | RPM 2000, TPM 500000 |
  | 图像生成模型 (Image) | IPM、IPD | IPM 2, IPD 400 |
- > "Rate Limit 是在用户账户级别定义的，而不是密钥（API key）维度。" 且 "每个模型单独设置 Rate Limits"。
- 免费模型：实名认证后可用，Rate Limits 固定；收费模型按用量级别 L0–L5 分层（按上月/当月消费金额）。
- 超限报错：
  > `HTTP/1.1 429 Too Many Requests` / `Content Type: application/json` / `Request was rejected due to rate limiting. If you want more, please contact contact@siliconflow.cn`
- 建议：指数退避重试、客户端限流、错峰。

**本机实测**：200/401/402 响应头**均无** `x-ratelimit-*` / `retry-after`；
仅见 `date`、`content-type`、`content-length`、`connection`、`x-siliconcloud-trace-id`。
→ 平台**未通过响应头暴露**剩余配额（文档也未承诺响应头带限流信息）。429 真实响应体 **UNVERIFIED**。

---

## 10. 差异汇总（官方文档 vs 本机实测）

| 项 | 官方文档 | 本机实测 | 判定 |
|---|---|---|---|
| 402 语义 | “账户欠费，请充值后重试” | `{"code":30001,"message":"Sorry, your account balance is insufficient","data":null}` | 一致，实测补出 code 30001 |
| 401 体 | 样例仅 `"Invalid token"` | `{"code":30014,"data":null,"message":"Token is invalid."}` | 实测更完整（结构化） |
| 400 体 | `{"code":20012,...}` | 模型不存在即 20012 | 一致 |
| bge-m3 维度 | 文档**未给** | 无法测（402） | 缺口 + UNVERIFIED |
| embeddings 批量条数上限 | 文档**未给** | 无法测（402） | 缺口 + UNVERIFIED |
| data[] 是否含 sparse/lexical | 文档 schema 只列 object/embedding/index | 无法测（402） | 缺口 + UNVERIFIED |
| rerank 分数值域/排序 | 示例 0.85、称“按相关性排序” | 无法测（402） | UNVERIFIED |
| 429 响应体 | 文档给了样例 | 无法安全触发 | UNVERIFIED |
| 响应头限流信息 | 文档未承诺 | 实测无 `x-ratelimit-*` | 实测确认“不提供” |

> 全部 UNVERIFIED 项的确切复跑命令见
> [`docs/research/probes/siliconflow-contract.md`](./probes/siliconflow-contract.md) 的 “Re-run checklist”。
