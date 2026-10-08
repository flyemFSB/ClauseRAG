# RAGAS 评测接入实施方案

## 1. 结论

RAGAS 应作为 **LLM/embedding 质量指标引擎** 接入，而不是作为 ClauseRAG 的运行时、引用校验器或唯一评测框架。

完整评测拆成四层：

```text
A. 路由评测
   QueryIntent / QueryRoute 是否正确

B. 确定性 RAG 评测
   document isolation、召回、evidence 覆盖、坐标、citation、abstention、延迟

C. RAGAS 评测
   faithfulness、answer relevancy、无参考答案的 context precision

D. 发布门禁
   数据/语料/模型/代码版本一致性、错误率、指标阈值和可重复工件
```

RAGAS 不负责下列事实：

- CUAD evidence 是否能投影到当前 normalized Markdown 的真实行号；
- child chunk 是否覆盖该行区间；
- `[S1]` 是否指向本次请求的有效 child；
- citation 的 document/version/line 坐标是否由后端真实回表；
- evidence gate 是否应回答或弃答。

这些属于 ClauseRAG 的确定性协议，必须先执行并单独报告。

## 2. 当前代码与缺口

当前代码已经具备大部分运行时事实源：

| 现有位置 | 可复用事实 |
|---|---|
| `backend/src/application/retrieval/service.py` | 多路召回、回表、RRF、重排、evidence gate、最终 context |
| `backend/src/application/retrieval/models.py` | `RetrievalResult` 与 `RetrievalDiagnostics` |
| `backend/src/domain/retrieval.py` | channel hits、candidate、rerank、evidence 状态 |
| `backend/src/domain/citation.py` | source label、context block、citation marker 校验 |
| `backend/src/application/retrieval/citations.py` | 引用标记校验与 authoritative chunk 回表 |
| `backend/src/agent_runtime/graph.py` | understand → route → retrieve → generate/abstain → validate citations |
| `backend/src/agent_runtime/runner.py` | 实际回答完成、持久化、SSE 和 tracing |
| `scripts/build-goldenset.py` | CUAD goldenset、路由对照集、可重复抽样和构建报告 |
| `scripts/goldenset_to_ragas.py` | 当前只做静态列投影检查，不执行 RAGAS |

缺口有四个：

1. 业务 Agent 的最终状态目前只保留 `RetrievalRecord`，评测需要保留同一次运行的完整 `RetrievalResult.diagnostics`。
2. 只有 SSE 对话入口和 retrieval-debug 入口，没有“不写会话、不走 SSE、返回完整结构化 trace”的评测执行入口。
3. 当前 `RetrievalChannel` 和 `RetrievalService` 只接受 `knowledge_base_id`，CUAD 问题中的 `this contract` 没有合同名，必须增加显式文档范围。
4. RAGAS 未进入 `pyproject.toml`/`uv.lock`，现有投影脚本没有连接运行时 answer、contexts 和 citations。
5. `scripts/goldenset_to_ragas.py` 中列出的 `NonLLMContextPrecisionWithReference` / `NonLLMContextRecall` 是 legacy 指标名；0.4.3 collections API 不导出它们。它们可作为 pin 在 0.4.x 时的可选文本相似度对照（需 `rapidfuzz`），但不作为本方案的权威指标或升级兼容契约。

## 3. 知识库组织与 document scope

目标评测将 510 份合同摄取到同一个评测知识库中，不按 41 个 category 建知识库，也不为每份合同建立长期知识库。确定性档对 20,910 个“合同 × 条款类别”槽位运行；`category` 只用于金标分层和结果分组。当前仓库的 `corpus.json` 仍是 100 份快速档，不能据此宣称已覆盖全量。

但是一个知识库不能替代样本中的目标合同。CUAD 问题是类似：

```text
Highlight the parts (if any) of this contract related to "..."
```

问题本身没有包含 `document_key`。因此每次 CUAD 评测运行必须传递：

```text
evaluation document scope = one resolved document_version_id
```

这个 scope 只用于评测执行时的检索过滤，不写入 goldenset，也不改变用户问题文本。它必须贯穿所有通道：

```text
knowledge_base_id AND document_version_id IN scope
```

实现要求：

- dense：Qdrant filter 同时约束 `knowledge_base_id` 和 `document_version_id`；
- keyword：PostgreSQL 查询增加 `document_version_id` 条件；
- hydrate：继续校验候选的 `document_version_id`、`knowledge_base_id` 和 `ready` 状态；
- scope 为空时保持生产行为，即检索整个知识库。

如果暂时没有 document scope，不能声称 410 条 CUAD 样本是在评测“每份目标合同”。临时按合同拆 510 个知识库可以做探针，但不应成为生产架构或最终基准。

## 4. 不变的 goldenset 契约

`evals/cuad/golden.jsonl` 每行保持：

```json
{
  "id": "cuad-000001",
  "document_key": "stable-contract-source-key",
  "category": "Anti-Assignment",
  "question": "...",
  "evidence": ["...", "..."]
}
```

`category` 不传给 RAG 路由，不参与知识库选择，也不当作预测标签。它只用于：

- 410 条完整链路/RAGAS 样本按 category 分层抽取；当前 410 条来自 100 合同快速档，全量档必须在 510 合同入库后重建这 410 条；
- 按条款主题分组报告 Recall、Evidence Recall、Citation Accuracy；
- 定位某一条款主题的失败模式。

goldenset 仍然不保存 parent/child ID、chunk 内容、分数或平台坐标。当前构建器的 `CORPUS_SIZE=100`，因此当前 410 条只来自覆盖性快速档。目标全量档将 corpus manifest 升为全部 510 份、重新摄取，并从 20,910 个槽位中按固定 seed 重建 410 条生成评测样本；全量 deterministic 阶段直接从原始 CUAD 标注派生全部槽位，不额外固化一份冗余 goldenset。运行 manifest 必须记录 corpus coverage，旧快速档分数不得与全量档混为同一基线。

## 5. Evidence projection

每个运行在评测前执行一次 evidence 投影，不修改 goldenset：

```text
golden evidence text
  → 找到该 document_key 对应的 ready document version
  → 读取该版本的 normalized Markdown artifact
  → 精确/规范化文本匹配
  → 生成真实 line span
  → 与 child 的 [line_start, line_end] 做区间相交
```

投影对象至少包含：

```text
projection_status: exact | normalized | ambiguous | redacted | unresolved
line_spans: [(line_start, line_end), ...]
covered_child_ids: 运行时派生
artifact_checksum
parser_name / parser_version
```

规则：

- `exact`/`normalized` 且唯一匹配才进入 evidence coverage；
- `ambiguous`、`redacted`、`unresolved` 不得直接计为召回失败，单独报告 projection failure rate；
- CUAD 的 `answer_start` 属于 CUAD 的原始 TXT 抽取，不是 ClauseRAG normalized Markdown 坐标；
- 表格分片可能在 `chunk.content` 中重复表头，而 line range 不包含这些重复表头；`content` containment 不能证明坐标覆盖；
- evidence 投影失败率超过配置阈值时，评测退出为 `inconclusive`，不产生误导性的 0 分。

## 6. 评测执行入口

不要通过生产 SSE 接口驱动评测：它需要认证、写会话、写消息、流式解析，并且 retrieval-debug 与最终回答会执行两次不同的运行。

新增一个应用层评测执行服务，建议位置：

```text
backend/src/application/evaluation/
  contracts.py       # EvaluationTrace、EvaluationContext、EvaluationCitation
  service.py         # 单样本无持久化执行
  projection.py      # evidence -> artifact line span -> child coverage
```

该服务复用现有 `RunContext` 中的：

- `QueryUnderstandingService`；
- `RetrievalService`；
- `AnswerService`；
- `CitationService`；
- `domain.query.route_for` 和 `domain.citation` 校验逻辑。

`ConversationAgent` 与评测服务应共同调用一个不带副作用的 Agent execution service；不要在评测脚本中重新复制 `graph.py` 的路由、重试和弃答规则。

单样本执行结果建议为：

```text
EvaluationTrace
  sample_id
  document_key / category
  question
  expected_intent
  actual_intent / route
  rewritten_queries
  retrieval_rounds
  terminal: answered | abstained | direct_response | clarification | failed
  raw_response
  response                         # citation validation 后实际给用户的文本
  evidence_status / evidence_reason
  channels[]                      # status、latency、rank、raw score
  fused[] / reranked[]            # 运行时诊断
  generator_contexts[]            # 实际送进回答模型的 source block
  ranked_candidate_contexts[]     # 重排后候选的文本，按 rank
  citations[]                     # citation id、document/version、line、quote
  removed_citation_ids
  latency_ms
  error_class / error_message
```

`raw_response` 只用于 citation 检查，RAGAS 默认使用最终 `response`；所有内容型工件应放在受控的评测目录，不写普通业务日志。

评测执行可作为 `python -m cli evaluate-ragas`，RAGAS 依赖延迟导入；也可以先实现等价的独立命令，但不能绕过应用层服务。

## 7. RAGAS 样本投影

RAGAS 的 `SingleTurnSample` 只保存 RAGAS 认识的列；`sample_id`、category、坐标和运行元数据放在同 ID 的 ClauseRAG sidecar 中，不依赖 RAGAS 保留额外字段。

### 7.1 生成质量数据集

用于 `Faithfulness` 和 `AnswerRelevancy`：

```python
SingleTurnSample(
    user_input=trace.question,
    response=trace.response,
    retrieved_contexts=trace.generator_contexts,
    reference_contexts=gold.evidence,
)
```

`generator_contexts` 必须是实际传给 `AnswerService.stream_grounded` 的 source block 内容。不能把数据库中所有 child 内容、仅 citation quote 或另一次 retrieval-debug 的结果混进来。

### 7.2 检索排序数据集

用于 `ContextPrecisionWithoutReference`：

```python
SingleTurnSample(
    user_input=trace.question,
    response=trace.response,
    retrieved_contexts=trace.ranked_candidate_contexts[:N],
)
```

`N` 固定写入 manifest，例如 `N=8`，不要每次按结果数量变化。这个数据集测的是 RAGAS 对候选相关性的 LLM 判断；精确的 evidence span recall 和 document recall 仍以 ClauseRAG 自己的 line/ID 计算为准。

### 7.3 CUAD 没有 reference answer 的限制

当前 CUAD `evidence` 是证据片段，不是人工撰写的完整参考回答。因此首版：

| 指标 | 首版 | 原因 |
|---|---:|---|
| `Faithfulness` | 使用 | 只判断 response 是否由实际上下文支持 |
| `AnswerRelevancy` | 使用 | 判断回答是否响应问题，需要 LLM 和 embedding |
| `ContextPrecisionWithoutReference` | 可选 | 判断候选是否被回答使用，成本较高 |
| `ContextPrecisionWithReference` / `ContextRecall` | 不使用 | 现代 LLM collection 需要 `reference` 参考答案，evidence 不能冒充答案 |
| `NonLLMContextPrecisionWithReference` / `NonLLMContextRecall` | 非首选，可选兼容基线 | 仅 RAGAS 0.4.x legacy API 可用并需 `rapidfuzz`；比较文本相似度，不验证行坐标或 child anchor，不能作为主指标 |
| `AnswerCorrectness` / `FactualCorrectness` | 不使用 | 没有参考答案 |
| `[S1]` citation validity | 不交给 RAGAS | 必须使用 ClauseRAG authoritative 回表和坐标校验 |

未来若人工增加 `reference_answer`，放在单独的 `evals/cuad/answers.jsonl`，按 `id` 关联，不把自动生成答案伪装成 gold。届时再启用带 reference 的指标。

### 7.4 空 evidence 样本

`evidence == []` 的样本不送入需要非空 context/response 的 RAGAS 指标。它们执行确定性弃答评测：

```text
expected_abstain = true
actual_abstain = terminal == abstained
                  AND evidence_status == insufficient
                  AND no valid citation
```

RAGAS 对拒答文本给一个 relevancy 或 faithfulness 分数不能证明系统正确弃答，不能替代 abstention accuracy。

## 8. RAGAS 版本与依赖

RAGAS 官方当前可见稳定版本为 `0.4.3`，Python 要求 `>=3.9`。ClauseRAG 使用 Python 3.12，但必须把 RAGAS 精确锁进 `uv.lock`。

建议新增独立依赖组，不把评测库带入生产服务启动路径：

```toml
[dependency-groups]
eval = [
  "ragas==0.4.3",
  "openai>=1,<2",
]
```

`openai` 用于创建 OpenAI-compatible judge/embedding client；RAGAS 已声明若干传递依赖。只有选择 RAGAS 的 rapidfuzz 非 LLM 指标时才增加相应可选依赖；本方案的权威 deterministic 指标由 ClauseRAG 实现，不为一个字符串相似度额外扩大生产依赖。

新增评测专用配置，不把评测 key 硬编码进业务配置或日志：

```text
EVAL_JUDGE_API_KEY
EVAL_JUDGE_BASE_URL
EVAL_JUDGE_MODEL
EVAL_EMBEDDING_MODEL
EVAL_MAX_CONCURRENCY=2
EVAL_TIMEOUT_SECONDS=120
EVAL_MAX_RETRIES=2
EVAL_CACHE_DIR=dist/eval-cache
RAGAS_DO_NOT_TRACK=true       # 按组织隐私策略决定
```

SiliconFlow 的 OpenAI-compatible endpoint 可以作为首个 provider，但必须先执行结构化输出 smoke test，因为 RAGAS 0.4.3 的 collections 指标依赖 Instructor/Pydantic structured output。

模型适配方向：

```python
from openai import AsyncOpenAI
from ragas.cache import DiskCacheBackend
from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory

client = AsyncOpenAI(
    api_key=eval_key,
    base_url=eval_base_url,
    timeout=eval_timeout,
    max_retries=eval_max_retries,
)
cache = DiskCacheBackend(cache_dir)
judge = llm_factory(eval_judge_model, provider="openai", client=client, cache=cache)
embeddings = embedding_factory(
    "openai",
    model=eval_embedding_model,
    client=client,
    cache=cache,
)
```

不得让每个 metric 自己创建 client。运行时只允许一个受控 client、一个缓存目录和一个并发门。

## 9. 指标执行策略

RAGAS 0.4.x 正在从 `evaluate()`/legacy metrics 向 `@experiment`/collections 迁移，且官方迁移文档明确要求从 `ragas.metrics.collections` 使用现代指标。首版不依赖 deprecated `ragas.metrics`、`single_turn_ascore()` 或把 `evaluate()` 当作项目的持久化层。

直接调用现代 metric 的 `ascore`，并由 ClauseRAG 控制并发、重试、样本 ID 和失败状态：

```python
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecisionWithoutReference,
    Faithfulness,
)

metrics = [
    Faithfulness(llm=judge),
    AnswerRelevancy(llm=judge, embeddings=embeddings, strictness=1),
    ContextPrecisionWithoutReference(llm=judge),
]
```

执行约束：

- 用 `asyncio.Semaphore(EVAL_MAX_CONCURRENCY)` 包住样本级调用；
- 先以 `strictness=1` 做基线，发布评测再升为 3；
- 只重试超时、429、5xx 等瞬时错误，4xx 鉴权/参数错误直接失败；
- 单行失败写 `status=error`、`error_class`，不把错误行静默当 0 分；
- 对 metrics 需要的空输入先做本地 skip；
- 运行一次前先用一个 dummy row 验证所有 metric 的 required columns 和 provider structured output；
- 固定模型、prompt 版本、temperature、embedding model、RAGAS 版本和 seed；
- 第一次运行填充 DiskCache，后续同一 manifest 的重跑从缓存读取；
- RAGAS 的 `reason` 若版本提供则保存，但不把 judge reason 当作 citation 事实。

成本控制采用分层运行：

```text
20,910 条：doc scope 下运行 retrieval-only，统计 evidence projection、Recall@K、Evidence Recall、evidence gate；跳过意图 LLM、查询改写、answer generation 和 RAGAS judge，但单独记 embedding/rerank 请求成本
410 条：完整理解/路由/检索/回答链，确定性校验真实 emitted citations，再运行首版 RAGAS
空 evidence：不调用 RAGAS judge，单独计算弃答正确性
ContextPrecisionWithoutReference：可按预算开启的独立成本档位
```

`Faithfulness` 会拆回答声明并再做支持判断，`AnswerRelevancy` 默认会生成多个问题；二者不是零成本。每个 run 记录实际请求数、token 数、缓存命中和错误数，不能只用样本数估算成本。

## 10. 确定性指标

每条 trace 计算并保存：

```text
route_accuracy
query_understanding_degraded
retrieval_rounds
channel_status / channel_latency_ms
candidate_count

document_recall@k
child_recall@k
evidence_span_recall@k
evidence_projection_status
ranked_context_precision

abstention_accuracy
answer_when_evidence_present
citation_marker_validity
citation_document_version_validity
citation_line_range_validity
citation_quote_authority
citation_evidence_coverage

end_to_end_latency_ms
retrieval_latency_ms
answer_latency_ms
```

定义必须固定：

- `document_recall@k`：目标 document version 是否出现在 top-k candidate；
- `evidence_span_recall@k`：可投影的每个 gold line span 是否与 top-k child line range 相交；
- `citation_marker_validity`：raw response 中出现的每个 `[S<n>]` 是否属于本次有效 sources；
- `citation_line_range_validity`：回表 citation 的 line range 是否仍对应当前 artifact 和 child；
- `citation_quote_authority`：quote 是否由后端从当前 child/artifact 生成，而不是直接信任模型文本；
- `abstention_accuracy`：expected evidence-empty/insufficient 与实际 terminal/evidence status 的一致性。

RAGAS 分数不覆盖这些定义，报告中不能把 `faithfulness` 改名为 `citation_accuracy`。

## 11. 工件与可追溯性

每次评测生成一个不可变目录：

```text
dist/verify/ragas/<run_id>/
  manifest.json
  traces.jsonl
  deterministic.jsonl
  ragas-scores.jsonl
  summary.json
  by-category.json
  errors.jsonl
  SHA256SUMS
```

`manifest.json` 至少包含：

```text
run_id
created_at
code_revision
goldenset_sha256
categories_sha256
corpus_sha256
source_dataset_sha256
knowledge_base_id
resolved_document_versions and artifact checksums
parser/chunker versions
chat/rerank/embedding model names
judge/embedding model names
ragas_version
python_version
metric list
metric configuration
concurrency/retry/timeout/seed
```

`traces.jsonl` 可以保存评测语料所需的 context/citation 内容，但必须限制在受控目录；普通日志只保存 sample_id、hash、状态、耗时和错误类别。任何 API key、session token、密码和生产租户数据不得进入工件。

汇总统计同时给出：

- overall macro mean；
- 按 `category` 分组的均值和样本数；
- evidence-present/evidence-empty 分层；
- route 分层；
- metric error/skip/inconclusive 数量；
- 95% bootstrap 区间（固定 seed）；
- 与基线 run 的差值。

`category` 只出现在 sidecar/分组报告，不进入 RAGAS judge prompt，也不代表分类准确率。

## 12. CLI 与运行顺序

建议提供以下命令，所有命令都写 manifest 并使用同一个 run directory：

```powershell
uv run --group eval python -m cli evaluate-ragas `
  --dataset evals/cuad/golden.jsonl `
  --knowledge-base-id <evaluation-kb> `
  --mode trace `
  --limit 410

uv run --group eval python -m cli evaluate-ragas `
  --run-dir dist/verify/ragas/<run_id> `
  --mode deterministic

uv run --group eval python -m cli evaluate-ragas `
  --run-dir dist/verify/ragas/<run_id> `
  --mode ragas `
  --metrics faithfulness,answer_relevancy
```

执行顺序必须是：

1. `scripts/build-goldenset.py --verify`；
2. 确认 `corpus.json` 中所有目标版本已经 parse/chunk/embed/index ready；
3. 做 artifact checksum 和 document_key 唯一性检查；
4. 用 document scope 跑 trace；
5. 先跑 deterministic 指标；
6. 只有 projection、scope、trace、citation 的前置检查通过后才调用 RAGAS；
7. 生成汇总、checksum 和验证报告。

不要每次改变 chunker、prompt、模型后覆盖旧 run；必须产生新的 run_id 和 manifest。

## 13. 实施分期

### P0：契约与 smoke

- 锁定 `ragas==0.4.3` 到 `uv.lock`；
- 增加 eval dependency/config；
- 实现一个 dummy row 的 `llm_factory`、`embedding_factory`、collections metric smoke；
- 修正 `goldenset_to_ragas.py` 为投影校验器，而不是宣称已经执行 RAGAS。

验收：无业务服务启动时也能导入 evaluator；真实 OpenAI-compatible endpoint 能返回结构化 metric result。

### P1：无副作用 Agent trace

- 提取共享的 Agent execution service；
- 增加 `EvaluationTrace`；
- 保留同一次 `RetrievalResult` 的 diagnostics、generator context 和 citation raw/final answer；
- 增加 document scope 并贯穿 dense/keyword/graph；
- graph 不支持 scope 时显式 unavailable，不准静默事后过滤。

验收：一条样本只执行一次理解/召回/回答链，trace 能重建回答实际看到的上下文。

### P2：全量 deterministic evaluator

- 先将目标语料升为 510 份合同并完成摄取、版本与 artifact checksum 校验；
- 从 CUAD 原始标注派生 20,910 个槽位，不另存冗余 goldenset；
- 实现 artifact evidence projection；
- 实现 document/child/span/evidence-gate/latency 指标；
- 用 document scope 运行 retrieval-only：跳过意图 LLM、查询改写、回答生成和 LLM judge；记录 embedding/rerank/provider 请求及成本；
- emitted citation marker 和权威 citation 回表校验只对 410 条完整链路样本报告；
- 输出 coverage 明确的 deterministic 工件和 category 报告。

验收：projection unresolved 与 cross-document hit 不会被算作普通召回失败；没有模型生成的样本不报告 citation-marker accuracy；空 evidence 的 evidence-gate 结果不被误标为 citation 事实。

### P3：RAGAS evaluator

- 建立两个 RAGAS projection dataset；
- 首版运行 Faithfulness、AnswerRelevancy；
- ContextPrecisionWithoutReference 作为单独成本档位；
- 保存每个 `MetricResult.value/reason/status`；
- 启用磁盘缓存和有界并发；
- 对 provider error、NaN、skip、cache hit 分开统计。

验收：重复同一 manifest 的运行不重复调用已缓存的 judge 请求；更换模型或 prompt 会产生新的缓存身份。

### P4：最终门禁

执行仓库要求的静态检查，并增加真实容器评测 probe：

```powershell
uv run ruff check backend/src
uv run pyright backend/src
uv run python scripts/check-architecture.py
uv run --group eval python -m cli evaluate-ragas --mode smoke
docker compose -f infra/compose.yaml --profile app up -d --build --wait
```

一次完整的运行时验收就是最后那条命令：构建镜像、跑迁移、起四个服务并等它们 healthy，随后在 nginx 单一入口上核对 `/health/ready` 与 `/api/v1/config`。平台不再有探针脚本套件与 `dist/verify/` 报告：验收结论以真实响应与一次真实问答为准。

## 14. 风险与明确不做的事

- 不把 `category` 建成意图树或 RAGAS 分类标签；
- 不把 41 类拆成 41 个知识库；
- 不在 goldenset 固化 child/parent ID；
- 不用 CUAD `answer_start` 当平台 line coordinate；
- 不把 evidence spans 拼成伪造的 `reference answer`；
- 不用 RAGAS 的文本相似度替代 authoritative citation validation；
- 不把一次 production SSE 调用和一次 retrieval-debug 调用拼成“同一 trace”；
- 不让 RAGAS 默认 16 workers、10 retries 直接冲击 SiliconFlow；
- 不把 judge cache、合同正文或运行时 citation 内容写入普通应用日志；
- 不在没有 document scope 的情况下声称完成了“this contract”级别的 CUAD 评测。

## 15. 官方依据

- [RAGAS PyPI](https://pypi.org/project/ragas/)
- [RAGAS v0.4.3 release](https://github.com/vibrantlabsai/ragas/releases/tag/v0.4.3)
- [Evaluate a simple RAG system](https://docs.ragas.io/en/stable/getstarted/rag_eval/)
- [`evaluate()` reference](https://docs.ragas.io/en/stable/references/evaluate/)
- [Evaluation schema](https://docs.ragas.io/en/stable/references/evaluation_schema/)
- [Available metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)
- [Context Precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/)
- [Context Recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/)
- [Faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)
- [Response Relevancy](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/)
- [v0.3 to v0.4 migration](https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04/)
- [Model customization](https://docs.ragas.io/en/stable/howtos/customizations/customize_models/)
- [Caching](https://docs.ragas.io/en/stable/howtos/customizations/_caching/)
- [RunConfig](https://docs.ragas.io/en/stable/references/run_config/)
- [ClauseRAG 官方 RAGAS 调研摘要](../research/ragas-official-research.md)
- [RAGAS 0.4.3 源码核对说明](../research/official-docs-ragas.md)

---

## 16. 实施记录

### P0 已完成（本机真实 endpoint 验证）

| 交付物 | 说明 |
|---|---|
| `pyproject.toml` `[dependency-groups] eval` | `ragas==0.4.3` + `openai` + `langchain-community>=0.3.31,<0.4` |
| `backend/src/infrastructure/config/settings.py` | `EVAL_*` 配置块（10 项），未配置专用 judge 凭据时回落到 SiliconFlow |
| `backend/src/infrastructure/evaluation/specs.py` | 指标列契约（不 import ragas）：`V1_METRICS`、`UNAVAILABLE_METRICS`、`missing_columns` |
| `backend/src/infrastructure/evaluation/engine.py` | 唯一的 judge/embedding client、DiskCache、并发门、`smoke()` |
| `backend/src/cli/commands/evaluate.py` | `python -m cli evaluate-ragas --mode smoke`（引擎延迟导入） |
| `scripts/goldenset_to_ragas.py` | 改为投影**校验器**（读 `specs.py`，不复制指标表，不执行 RAGAS） |
| ~~`scripts/probes/ragas.ps1`~~ | 当时的探针；已随交付删除，冒烟改由 `python -m cli evaluate-ragas --mode smoke` 直接执行 |

执行结果：`faithfulness` / `answer_relevancy` / `context_precision_without_reference` 在
`Qwen/Qwen2.5-7B-Instruct @ https://api.siliconflow.cn/v1` 上均返回结构化分数（合计约 20s），
`await metric.ascore(...)` 的列签名与 §7 一致。服务进程不加载 ragas：
`import api.main, agent_runtime.main, worker.main, cli.main` 后 `ragas`/`openai` 均不在 `sys.modules`。

### 执行中发现的偏差（修正本文档）

1. **ragas 0.4.3 无法直接 import**。它声明裸 `langchain-community`，解析到已 sunset 的 0.4.2，而
   `ragas/llms/base.py` 顶层 `from langchain_community.chat_models.vertexai import ChatVertexAI`，
   0.4.0 已删掉该模块 → `import ragas` 直接 ImportError。0.4.3 是 PyPI 上的最新版本，没有上游修复，
   因此 eval 组钉住 `langchain-community>=0.3.31,<0.4`（最后一个既带有该模块、又允许
   `langchain-core` 2.x 的版本）。**移除条件**已写在 `pyproject.toml` 里。
2. **`NonLLMContextPrecisionWithReference` / `NonLLMContextRecall` 不是公开 API**。0.4.3 只把它们
   导出为私有名 `_NonLLMContextPrecisionWithReference` / `_NonLLMContextRecall`。§7.3 与调研摘要把
   它们列为「可选兼容基线」不成立，已改为不可用指标并在 `specs.UNAVAILABLE_METRICS` 中记录原因。
3. **首版三个指标都不读 `reference_contexts`**：`Faithfulness` 读 `retrieved_contexts`，
   `AnswerRelevancy` 只读 `user_input` + `response`。§7.1 的 `reference_contexts=gold.evidence`
   应在 sidecar 中保留给确定性层（evidence coverage / span recall），不要指望 RAGAS 用它。
4. **smoke 需要完整 `Settings`**。`load_settings()` 要求数据库/队列/对象存储配置，评测命令与其它
   运维子命令一样需要同一套 env（探针用 `Set-ProbeEnvironmentDefaults` 注入），不是只要
   `EVAL_*`。
5. **`scripts/check.ps1` 现在 sync eval 组**。`infrastructure/evaluation` 属于 `backend/src`，
   不装 eval 组时 Pyright strict 会因缺少 ragas 类型报 45 个 Unknown 错误（实测）。生产部署仍然
   `uv sync --locked --no-group eval`，因为没有任何服务启动路径导入评测包。

### Judge 质量观察（P3 前必须处理）

`Qwen/Qwen2.5-7B-Instruct` 能让三个指标全部返回分数，结构化输出可用，但在自洽的 smoke 行上
`faithfulness` 在 1.0 与 0.5 之间波动（两次真实运行）。smoke 只证明「能返回分数」，不证明 judge 可信：
真实评测前应通过 `EVAL_JUDGE_MODEL` 指定更强的 judge，并用同一行重复打分测其稳定性。

### 尚未开始

P1（无副作用 Agent trace、document scope 贯穿双通道）、P2（evidence 投影、20,910 槽位确定性评测评）、
P3（RAGAS 批量评测）、P4（最终门禁）。`--mode trace|deterministic|ragas` 目前显式返回 2 而不是静默降级。
