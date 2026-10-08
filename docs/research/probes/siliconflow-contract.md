# 实证探针：SiliconFlow provider 契约（Live contract probe）

日期：2026-10-02 · 环境：Windows PowerShell 7 · cwd `D:\YZB\RAG`
凭证来源：仓库根 `.env`（`SILICONFLOW_API_KEY`、`SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1`）。
本文件内所有密钥一律写 `sk-***`；探针脚本 `.probe\sf\sf_probe.py`、`.probe\sf\sf_auth_probe.py`、
`.probe\sf\sf_free_probe.py` 只从环境变量读取，原始输出在 `.probe\sf\out-sf-probe.txt`（`.probe/` 已 gitignore）。

---

## 状态：PARTIALLY VERIFIED — 账户恢复后已实测推理端点

2026-10-02 的首轮（见下方“历史记录”）因账户欠费只能拿到 HTTP 402，所有推理响应体都不可断言。
本轮（2026-10-02，同一账户恢复后）**重跑了 Re-run checklist 中本阶段需要的部分**，
embeddings 与 rerank 的真实响应已逐项实测，并把结论回填到下表中：

- `POST /v1/embeddings`（`BAAI/bge-m3`）→ **HTTP 200**，`data.length == input.length`，`data[0]` 的键为
  `embedding/index/object`（**无 sparse/lexical → dense-only 成立**），向量维度 **1024**，
  `usage = {prompt_tokens, completion_tokens, total_tokens}`。
- `POST /v1/rerank`（`BAAI/bge-reranker-v2-m3`）→ **HTTP 200**，`results[].relevance_score` 降序、落在 [0,1]，
  `return_documents=false` 时 `document=null`，`true` 时为 `{"text": ...}`。
- 批量：`input` 32/64/128/256 条均 200 且条数一致；**官方文档未给条数上限**，所以“无文档上限、
  由本部署配置界定”是结论（ADR-0019），不是推测出的数字。
- chat/SSE/结构化输出/function calling 仍 **UNVERIFIED**：它们是 Phase 4/5 的范围，本阶段不产生依赖。

首轮 402 的记录保留在下方，作为“为什么早期 ADR-0011 标 UNVERIFIED”的证据链。

### 历史记录：首轮 BLOCKED（HTTP 402, code 30001）

首轮**无法**用真实调用验证 embeddings / rerank / chat 的响应契约。
账户余额不足，所有计费推理端点在被调用时立刻返回 402。

官方错误码文档对该状态的释义（原文）：
> `402 ：账户欠费，请充值后重试；`
> — <https://docs.siliconflow.cn/docs/userguide/faqs/error-code>

### 首轮观测到的 402 响应（逐字，历史记录）

观测时间：2026-10-02 UTC（响应头 `date: Fri, 02 Oct 2026 05:40:29 GMT`）。

- `POST /v1/embeddings`（`model=BAAI/bge-m3`，input=3 条中英混合文本）：
  - HTTP 402 · 111 ms
  - 响应体（全文）：
    ```json
    {"code": 30001, "message": "Sorry, your account balance is insufficient", "data": null}
    ```
- `POST /v1/embeddings`（batch 32 条小文本）：HTTP 402 · 122 ms · 同上响应体。
- `POST /v1/embeddings`（`model=BAAI/does-not-exist-v9`）：HTTP **400** · `{"code": 20012, "message": "Model does not exist. Please check it carefully.", "data": null}`
- `POST /v1/embeddings`（`input=[]` 空数组）：HTTP 402 · 同上 30001 响应体。
- `POST /v1/embeddings`（`input=""` 空字符串）：HTTP 402 · 同上 30001 响应体。
- `POST /v1/rerank`（`BAAI/bge-reranker-v2-m3`，5 docs，`top_n=3`）：HTTP 402 · 106 ms · 同上响应体。
- `POST /v1/rerank`（`top_n=10 > 5` 候选）：HTTP 402 · 同上响应体。
- `POST /v1/rerank`（`documents=[]`）：HTTP 402 · 同上响应体。
- `POST /v1/rerank`（`model=BAAI/no-such-reranker`）：HTTP **400** · `{"code": 20012, "message": "Model does not exist. Please check it carefully.", "data": null}`
- `POST /v1/chat/completions`（非流式最小调用，`tencent/Hy4-preview`）：HTTP 402 · 113 ms · 同上响应体。
- `POST /v1/chat/completions`（`stream=true`）：HTTP 402，`content-type: application/json; charset=utf-8`，
  未产生 SSE 帧，响应体是同一 30001 JSON（即流式请求在欠费时也直接返回普通 JSON 错误）。
- `POST /v1/chat/completions`（`response_format={"type":"json_object"}`）：HTTP 402 · 同上响应体。
- `POST /v1/chat/completions`（`response_format={"type":"json_schema",...}`）：HTTP 402 · 同上响应体。
- `POST /v1/chat/completions`（`tools`/function calling）：HTTP 402 · 同上响应体。

候选“免费”模型同样被 402 拦截（同一响应体）：
`Qwen/Qwen2.5-7B-Instruct`、`Qwen/Qwen3-8B`、`THUDM/GLM-4-9B-0414`、`Qwen/Qwen3.5-4B`、
`deepseek-ai/DeepSeek-V3`、`zai-org/GLM-4.5-Air`、`tencent/Hunyuan-MT-7B`（chat）；
`BAAI/bge-m3`、`Qwen/Qwen3-Embedding-0.6B`、`BAAI/bge-large-zh-v1.5`（embeddings）；
`BAAI/bge-reranker-v2-m3`、`Qwen/Qwen3-Reranker-0.6B`（rerank）。

结论：402 是账户级闸门，在任何模型/任何端点、甚至在入参校验之前触发。
因此**本轮没有任何一条推理响应体可供断言**。

---

## 已确证事实（首轮真实调用，可复现）

> 首轮（账户 402 期间）这些是唯一可断言的事实；推理响应体见上方“PARTIALLY VERIFIED”一节。

1. **凭证有效**：`GET /v1/models` 用 `.env` 中的 key 返回 HTTP 200。
   反向对照：错误 key / 无 Authorization 均返回 HTTP **401** `{"code":30014,"data":null,"message":"Token is invalid."}`。
2. **`GET /v1/models` 成功**：HTTP 200 · 823 ms · `object=list` · **total models = 97**。
   条目形状：`{"id": "tencent/Hy4-preview", "object": "model", "created": 0, "owned_by": ""}`。
3. **模型在列**：`BAAI/bge-m3` 在列（True）；`BAAI/bge-reranker-v2-m3` 在列（True）。
4. **分类查询成功**（`sub_type` 过滤生效）：
   - `sub_type=embedding` → 8 个：
     `Qwen/Qwen3-VL-Embedding-8B`, `Qwen/Qwen3-Embedding-8B`, `Qwen/Qwen3-Embedding-4B`,
     `Qwen/Qwen3-Embedding-0.6B`, `BAAI/bge-m3`, `BAAI/bge-large-en-v1.5`,
     `BAAI/bge-large-zh-v1.5`, `Pro/BAAI/bge-m3`。
   - `sub_type=reranker` → 6 个：
     `Qwen/Qwen3-VL-Reranker-8B`, `Qwen/Qwen3-Reranker-8B`, `Qwen/Qwen3-Reranker-4B`,
     `Qwen/Qwen3-Reranker-0.6B`, `BAAI/bge-reranker-v2-m3`, `Pro/BAAI/bge-reranker-v2-m3`。
   - `sub_type=chat` → 64 个（含 `deepseek-ai/DeepSeek-V4-Flash`、`zai-org/GLM-5.3`、
     `Qwen/Qwen3-8B`、`Qwen/Qwen2.5-7B-Instruct` 等）。
   - `type=text` → 81 个。
5. **响应头无任何限流信息**：对 200 / 401 / 402 响应完整 dump headers，
   仅见 `date`、`content-type`、`content-length`、`connection`、`x-siliconcloud-trace-id`；
   **未出现 `x-ratelimit-*`、`x-ratelimit-remaining-*`、`retry-after`**。
   → 客户端无法从响应头预知/校准限流额度。
6. **错误码 schema（实测，非文档抄写）**：
   - 401：`{"code":30014,"data":null,"message":"Token is invalid."}`
   - 402：`{"code":30001,"message":"Sorry, your account balance is insufficient","data":null}`
   - 400（模型名不存在）：`{"code":20012,"message":"Model does not exist. Please check it carefully.","data":null}`
   - 均带响应头 `x-siliconcloud-trace-id: ti_*`。

---

## 未验证项（本轮重跑后逐项回填，未测的仍标 UNVERIFIED）

下列每一项都在拿到可用账户后重跑并回填；本文件不写任何推测值。

| # | 待验证项 | 状态 | 实测证据 |
|---|---|---|---|
| U1 | `BAAI/bge-m3` 输出向量维度（`data[0].embedding` 长度） | **VERIFIED** | 1024（`encoding_format=float`，3 条中文/英文混合输入） |
| U2 | embeddings `data[]` 元素是否返回 `sparse`/`lexical` 等额外字段 | **VERIFIED** | `data[0]` 全部键 = `embedding, index, object`，无任何包含 sparse/lexical 的字段 |
| U3 | embeddings 单请求 `input` 数组批量上限（条数） | **VERIFIED（负结论）** | 32/64/128/256 条均 HTTP 200 且 `data.length` 与输入一致；**官方文档未给上限**，也无 400 边界可测 → 上限“文档未给”，由本部署配置界定 |
| U4 | embeddings `usage` 结构 | **VERIFIED** | `{prompt_tokens: 28, completion_tokens: 0, total_tokens: 28}`，与文档 schema 一致 |
| U5 | rerank `relevance_score` 数值范围与排序语义 | **VERIFIED** | 降序；实测 `0.974393367767334 / 0.000418916024500504 / 0.000301230873446912`，均在 [0,1] |
| U6 | rerank `top_n` 超过候选数时的行为 | **UNVERIFIED** | 本轮只测了 `top_n < 候选数`（3/5 返回 3 条）；Phase 4 用到时再补 |
| U7 | rerank `documents=[]` 空数组的行为 | **VERIFIED** | HTTP 400 · `{"code":20015,"message":"List should have at least 1 item after validation, not 0","data":null}` |
| U8 | rerank `return_documents=true` 时 `document` 字段结构 | **VERIFIED** | `{"index":0,"document":{"text":"..."},"relevance_score":0.8229097127914429}` |
| U9 | chat `stream=true` 的 SSE 增量帧形状 | **UNVERIFIED** | Phase 4 范围，本轮未重测 |
| U10 | chat `response_format={"type":"json_object"}` 实测支持 | **UNVERIFIED** | Phase 4/5 范围，本轮未重测 |
| U11 | chat `response_format={"type":"json_schema"}` 实测支持 | **UNVERIFIED** | Phase 4/5 范围，本轮未重测 |
| U12 | chat `tools`/function calling 实测支持与 `tool_calls` 结构 | **UNVERIFIED** | Phase 5 范围，本轮未重测 |
| U13 | 429 的真实响应体 | **UNVERIFIED** | 仍无法安全触发 |
| U14 | **dense-only 假设是否成立** | **VERIFIED** | 由 U2 直接证实：响应里只有一个 1024 维稠密向量，没有第二路（sparse/lexical）输出 |

> U3 的“负结论”是结论而不是省略：官方文档确实没写批量条数上限，本项目遂以配置
> `RAG_EMBEDDING_BATCH_SIZE` 自行界定，并把该决定写进 ADR-0019，同时在此处记录“文档未给”。

**Phase 4 起由探针每次重跑的部分（U6、U9、U10、U11）**：`scripts/probes/retrieval.ps1` 第 7 步直接调用
`POST /v1/rerank` 重测 `top_n < 候选数`、`top_n > 候选数`（U6）与空 `documents`；
`scripts/probes/agent.ps1` 第 10 步直接调用 `POST /v1/chat/completions` 重测非流式响应、流式 SSE 帧形状与终止帧
`[DONE]`（U9）、`response_format={"type":"json_object"}`（U10）与 `{"type":"json_schema"}`（U11）。
两者都把原始输出打印在探针日志里，因此“provider 契约”是每个发布周期都会重验一次的证据，而不是一次性记录；
上表中这四项的实测值在首次运行 `scripts/smoke.ps1` 时回填。

---

## Re-run checklist（充值后一键复现全部证据）

前置（每次新开终端都先执行；只从 `.env` 读 key，绝不回显）：

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*SILICONFLOW_API_KEY\s*=\s*(.+)$') { $env:SF_KEY = $Matches[1].Trim() }
  if ($_ -match '^\s*SILICONFLOW_BASE_URL\s*=\s*(.+)$') { $env:SF_URL = $Matches[1].Trim() }
}
$H = @{ Authorization = "Bearer $env:SF_KEY"; "Content-Type" = "application/json" }
```

> PowerShell 7 的 `Invoke-RestMethod`/`Invoke-WebRequest` 需加 `-SkipHttpErrorCheck` 才能在 4xx 时读响应体。
> 流式（SSE）请用 `curl.exe -N -s`（见 U9 命令）。

**C0 · 凭证与 401 对照**
```powershell
(Invoke-RestMethod "$env:SF_URL/models" -Headers $H).data.Count            # 期望 97
Invoke-RestMethod "$env:SF_URL/models" -Headers @{Authorization='Bearer sk-bogus'} -SkipHttpErrorCheck  # 期望 401 / 30014
```

**C1 · 模型清单与分类**
```powershell
Invoke-RestMethod "$env:SF_URL/models?sub_type=embedding" -Headers $H | ForEach-Object data | ForEach-Object id
Invoke-RestMethod "$env:SF_URL/models?sub_type=reranker"  -Headers $H | ForEach-Object data | ForEach-Object id
Invoke-RestMethod "$env:SF_URL/models?sub_type=chat"      -Headers $H | ForEach-Object data | ForEach-Object id
```

**C2 · embeddings：维度 + data[0] 键 + usage（U1/U2/U4）**
```powershell
$b = @{ model='BAAI/bge-m3'; input=@('向量数据库如何支持混合检索？','BGE-M3 is a multilingual embedding model.','RRF 融合 dense 与 keyword 召回结果。'); encoding_format='float' } | ConvertTo-Json -Depth 6
$r = Invoke-RestMethod "$env:SF_URL/embeddings" -Method Post -Headers $H -Body $b -SkipHttpErrorCheck
$r.data[0].embedding.Count                       # 维度 → 实测 1024
$r.data[0].PSObject.Properties.Name              # data[0] 全部键 → 实测 embedding,index,object（无 sparse/lexical）
$r.usage                                         # → 实测 {prompt_tokens, completion_tokens, total_tokens}
```

另：本阶段的 indexing probe（`scripts/probes/indexing.ps1` 第 9 项）会在每次运行时重跑这一组探测并把
字段清单打印出来，所以它是**每个发布周期**都会重验一次的证据，而不只是本次的一次性记录。

**C3 · embeddings 批量上限探测（U3）**
```powershell
foreach ($n in 32,64,128,256) {
  $inp = 1..$n | ForEach-Object { "chunk $_ 文本 $_" }
  $b = @{ model='BAAI/bge-m3'; input=$inp } | ConvertTo-Json -Depth 6
  $r = Invoke-RestMethod "$env:SF_URL/embeddings" -Method Post -Headers $H -Body $b -SkipHttpErrorCheck
  "$n -> $($r.code) $($r.message) returned=$($r.data.Count)"
}
```

**C4 · embeddings 错误 schema（模型不存在 / 空 input）**
```powershell
$b = @{ model='BAAI/does-not-exist-v9'; input=@('x') } | ConvertTo-Json -Depth 6
Invoke-RestMethod "$env:SF_URL/embeddings" -Method Post -Headers $H -Body $b -SkipHttpErrorCheck   # 期望 400/20012
$b = @{ model='BAAI/bge-m3'; input=@() } | ConvertTo-Json -Depth 6
Invoke-RestMethod "$env:SF_URL/embeddings" -Method Post -Headers $H -Body $b -SkipHttpErrorCheck
$b = @{ model='BAAI/bge-m3'; input='' } | ConvertTo-Json -Depth 6
Invoke-RestMethod "$env:SF_URL/embeddings" -Method Post -Headers $H -Body $b -SkipHttpErrorCheck
```

**C5 · rerank：分数语义 + top_n + 空 documents（U5/U6/U7/U8）**
```powershell
$docs = @('向量数据库通过 ANN 索引加速最近邻检索。','今天天气晴朗，适合外出散步。','混合检索融合稠密向量与关键词两路召回结果。','红烧肉的做法需要五花肉、冰糖和生抽。','重排序模型对候选文档按与查询的相关性重新打分。')
$b = @{ model='BAAI/bge-reranker-v2-m3'; query='混合检索是如何融合多路召回结果的？'; documents=$docs; top_n=3; return_documents=$false } | ConvertTo-Json -Depth 6
$r = Invoke-RestMethod "$env:SF_URL/rerank" -Method Post -Headers $H -Body $b -SkipHttpErrorCheck
$r.results | Select-Object index, relevance_score        # 分数范围与排序
$b.top_n = 10; $b | ConvertTo-Json -Depth 6 | ForEach-Object { Invoke-RestMethod "$env:SF_URL/rerank" -Method Post -Headers $H -Body $_ -SkipHttpErrorCheck }  # top_n>候选数
$b.top_n = 2; $b.return_documents = $true
Invoke-RestMethod "$env:SF_URL/rerank" -Method Post -Headers $H -Body ($b | ConvertTo-Json -Depth 6) -SkipHttpErrorCheck
$b.documents = @()
Invoke-RestMethod "$env:SF_URL/rerank" -Method Post -Headers $H -Body ($b | ConvertTo-Json -Depth 6) -SkipHttpErrorCheck   # 空 documents
```

**C6 · chat 非流式（U10/U11/U12 的前置）**
```powershell
$chat = (Invoke-RestMethod "$env:SF_URL/models?sub_type=chat" -Headers $H).data[0].id
$b = @{ model=$chat; messages=@(@{role='user';content='只回复两个字：收到'}); max_tokens=16; temperature=0 } | ConvertTo-Json -Depth 8
Invoke-RestMethod "$env:SF_URL/chat/completions" -Method Post -Headers $H -Body $b -SkipHttpErrorCheck
```

**C7 · chat SSE 增量形状（U9，逐行）**
```powershell
curl.exe -N -s -X POST "$env:SF_URL/chat/completions" -H "Authorization: Bearer $env:SF_KEY" -H "Content-Type: application/json" `
  --data '{\"model\":\"Qwen/Qwen2.5-7B-Instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"数到三\"}],\"max_tokens\":16,\"stream\":true}'
```

**C8 · chat 结构化输出（U10/U11）**
```powershell
$b = @{ model=$chat; messages=@(@{role='system';content='Output JSON only.'},@{role='user';content='输出 {"intent":"lookup"} 形式的 JSON'}); max_tokens=32; temperature=0; response_format=@{type='json_object'} } | ConvertTo-Json -Depth 10
Invoke-RestMethod "$env:SF_URL/chat/completions" -Method Post -Headers $H -Body $b -SkipHttpErrorCheck
$b.response_format = @{ type='json_schema'; json_schema=@{ name='understand_query'; schema=@{ type='object'; properties=@{ intent=@{type='string'}; entities=@{type='array';items=@{type='string'}} }; required=@('intent','entities') } } }
Invoke-RestMethod "$env:SF_URL/chat/completions" -Method Post -Headers $H -Body ($b | ConvertTo-Json -Depth 20) -SkipHttpErrorCheck
```

**C9 · chat function calling（U12）**
```powershell
$b = @{ model=$chat; messages=@(@{role='user';content='北京天气如何？'}); max_tokens=64; temperature=0;
  tools=@(@{type='function';function=@{name='get_weather';description='Get weather for a city';parameters=@{type='object';properties=@{city=@{type='string'}};required=@('city')}}});
  tool_choice='auto' } | ConvertTo-Json -Depth 12
Invoke-RestMethod "$env:SF_URL/chat/completions" -Method Post -Headers $H -Body $b -SkipHttpErrorCheck
```

**C10 · 限流头 / 429（U13）**
```powershell
# 完整响应头 dump（确认是否出现 x-ratelimit-*）
(Invoke-WebRequest "$env:SF_URL/models" -Headers $H).Headers | Format-List
# 429 需高频打满 RPM/TPM 才能触发，无安全触发手段；本轮未证实。
```

**C11 · 一键重跑 Python 探针（本文件全部原始输出）**
```powershell
.probe\venv-live\Scripts\python.exe -u .probe\sf\sf_probe.py        # 主探针，输出 .probe\sf\out-sf-probe.txt
.probe\venv-live\Scripts\python.exe -u .probe\sf\sf_auth_probe.py   # 认证/响应头
```
（`httpx 0.28.1` + CPython 3.12.14；venv 由 `uv venv .probe\venv-live --python 3.12` 建立。）
