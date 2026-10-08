# Goldenset 构建方案

## 目标

Goldenset 用于验证 ClauseRAG 的完整合同检索链路：

```text
问题 → 路由 → 查询 → 双通道召回 → 融合/重排 → evidence gate → child 引用锚定 → parent 上下文 → 回答/弃答
```

Goldenset 只保存稳定的人工标注事实，不保存当前解析器、chunker 或检索实现产生的 ID 和分数。

## 数据规模

CUAD 原始数据包含 20,910 条“合同 × 条款类别”槽位（41 个类别 × 510 份合同）。目标评测分为两档：

- 全量确定性档：目标覆盖全部 510 份合同、20,910 个槽位；只运行文档隔离、evidence 投影与覆盖、召回排序、引用坐标、弃答和延迟等确定性检查，不调用 LLM judge。
- 分层生成档：从全量槽位按 category 分层抽取 10 条，目标 `41 × 10 = 410` 条；执行完整生成链和有界的 RAGAS 指标。
- 当前仓库产物仍是过渡快速档：`evals/cuad/corpus.json` 只有 100 份覆盖性合同，`golden.jsonl` 的 410 条也由这 100 份合同抽出；它最多支撑 4,100 个槽位的确定性检查，不能代表上述 20,910 个槽位全量结果。
- 100 份子集是按覆盖度挑选（先贪心保住罕见条款类别，再随机补齐），不是总体代表性随机样本；`Source Code Escrow` 在 510 份里只有 13 份带 evidence、`Price Restrictions` 15 份、`Unlimited/All-You-Can-Eat-License` 17 份，随机抽 100 份会在 200 次里 199 次打掉 1–7 个类别的 evidence 侧，贪心部分实际只需要 52 份。
- 全量档上线后，将 corpus manifest 升为全部 510 份并重新摄取，再从完整槽位重建 410 条分层样本；固定 seed、输入 checksum 和输出 checksum 随构建报告保存。无需另存第二份 20,910 行 goldenset，评测器可从已校验的 CUAD 原始标注流式派生确定性样本。

## Goldenset 单条格式

文件：`evals/cuad/golden.jsonl`

每行只包含 5 个字段：

```json
{
  "id": "cuad-000001",
  "document_key": "ZEBRATECHNOLOGIESCORP_04_16_2014-EX-10.1-INTELLECTUAL PROPERTY AGREEMENT",
  "category": "Anti-Assignment",
  "question": "Highlight the parts (if any) of this contract related to \"Anti-Assignment\" that should be reviewed by a lawyer. Details: Is consent or notice required of a party if the contract is assigned to a third party?",
  "evidence": [
    "If Purchaser or a Purchaser Assignee assigns or transfers...",
    "Neither party may assign (whether by operation of law or otherwise)..."
  ]
}
```

字段含义：

| 字段 | 含义 |
|---|---|
| `id` | 评测样本的稳定唯一标识。与合同文件名和 chunk ID 无关。按 `(category 顺序, document_key)` 顺序编号，改变种子或抽样逻辑会重新编号，历史结果不可跨重建比较。 |
| `document_key` | 合同源文件的稳定业务键。当前固定语料可使用规范化文件名去掉扩展名后的值；必须唯一对应一个合同版本。 |
| `category` | 该样本对应的 CUAD 条款类别，必须存在于 `categories.json`。`question` 已由模板包含类别名，但显式保存使校验、评测与人工复核都不依赖问题模板这一隐式契约。 |
| `question` | 实际发送给 RAG 系统的问题。保留实际输入，避免模板变化导致历史评测输入隐式变化。 |
| `evidence` | 人工标注的正确证据文本数组，按 CUAD 标注数组的原始顺序保存（该顺序不是文档顺序，投射到行区间时须重新按行号排序）。空数组表示该合同没有该类别的证据，系统应主动弃答。 |

不保存以下字段：

```text
parent_id, child_id, document_version_id,
line_start, line_end, heading_path, block_type,
token_count, chunk_content, retrieval_score,
rerank_score, query_rewrite, citation_id, answer
```

特别是：goldenset 不保存 parent chunk ID 或 child chunk ID。评测运行时按 evidence 与当前 normalized Markdown 的匹配结果，将 evidence 投影到实际 child；parent 只用于生成上下文扩展。

## 类别与路由意图

41 个 category 是合同条款主题，不是 41 种路由意图。类别描述和问题模板放在：

```text
evals/cuad/categories.json
```

路由意图只保留 3 种：

| 路由意图 | 含义 |
|---|---|
| `retrieval` | 需要检索合同或知识库内容。410 条 CUAD 抽样样本均属于此类。 |
| `direct_response` | 不需要检索合同内容即可回答，例如问候或系统功能问题。 |
| `ask_clarification` | 问题信息不足，无法确定合同、条款或审查范围。 |

当前 CUAD goldenset 不用于完整评估 3 类路由分类，因为它几乎只有 `retrieval` 正例。路由准确率需要另外维护少量 `direct_response` 和 `ask_clarification` 对照样本，它们放在：

```text
evals/routing/contrast.jsonl
```

每行字段为 `id` / `intent` / `question` / `context` / `note`。`context` 记录该样本成立的前提会话状态（当前均为 `empty_session`，即无已选合同、无历史），因为这几个 `ask_clarification` 标签正是以指代缺失为前提的；`note` 记录该标签为何成立。不要把 41 个 category 当作路由意图。

## Chunk 与 evidence 的关系

运行时采用以下映射：

```text
gold evidence
  → normalized Markdown 文本定位
  → line span
  → 与 child_chunks 做覆盖/相交判断
  → child 作为检索与 citation 锚点
  → parent 作为生成上下文
```

goldenset 不断言任何具体 chunk 切分方式。chunk 参数或 tokenizer 改变后，只需重新执行 projection，不需要修改 goldenset。

表格 chunk 可能包含重复表头，而其 `line_start`/`line_end` 不包含重复表头。因此不能用 `chunk.content` 包含 evidence 作为唯一坐标验证；严格验证必须回到 normalized Markdown artifact 的真实行区间。

## 评测分层

### 全量确定性评测

目标范围是全部 20,910 个槽位（510 份 × 41 类别），不调用回答生成模型或 RAGAS judge。每条检索以所属合同版本作为显式 document scope；直接使用 CUAD 问题作为检索查询，不运行 LLM 意图改写。真实 dense/rerank 检索仍可能调用 embedding/rerank provider，因此须限流、缓存可缓存请求并记录请求数/成本。计算：

- document/version isolation；
- evidence 投影状态及 gold line span 到 child anchor 的覆盖率；
- Recall@K、Precision@K、MRR；
- evidence span recall；
- evidence gate 与预期弃答决策；
- 各 category 的召回统计；
- 检索延迟和各通道状态。

这层没有模型生成的 `[S#]`，不能报告 emitted-citation validity。实际回答的引用标记、权威回表坐标与 quote 检查在 410 条完整链路样本中运行。当前 100 合同快速档只能对 4,100 个槽位执行全量检索检查；结果须标为 `coverage=100/510`，不得外推或报告为全量结果。

### 410 条生成评测

对每个 category 10 条抽样执行完整链路：

- 路由、查询改写、召回、evidence gate、回答/弃答；
- emitted citation marker、document/version、line span、权威 quote 与 evidence coverage；
- Faithfulness、AnswerRelevancy；
- 可选 `ContextPrecisionWithoutReference`，单独作为较高成本档位；
- 每个类别/evidence-present/evidence-empty 分层的行为统计。

CUAD 没有 reference prose answer，因此不计算 RAGAS `ContextRecall`、带 reference 的 context precision、answer correctness。Evidence Recall 是上一层对 20,910 个槽位执行的确定性度量，不依赖 RAGAS。

## 构建校验

构建脚本必须拒绝以下情况：

- `id` 重复；
- `document_key` 为空；
- `document_key` 无法映射到唯一合同源文件；
- `question` 为空；
- `evidence` 不是字符串数组；
- evidence 非空但包含空字符串；
- category 不存在于 `categories.json`；
- 同一个 `(document_key, category)` 重复；
- 抽样集不是每个 category 10 条，或偏差没有写入构建报告；
- 抽样集混入非目标合同版本；
- `document_key` 不在本次 run manifest 绑定的目标语料内；
- 目标全量档未覆盖全部 510 份合同，或某 category 的样本数与构建报告所记偏差不一致。

当前 builder 的 `CORPUS_SIZE=100` 只验证快速档；升全量档时需调整 builder 与 `corpus.json` 生成逻辑，并重新生成金标。

构建结果应输出：

```text
总样本数
category 分布
有 evidence / 空 evidence 数量
合同源文件数量
重复键数量
无法映射的 document_key
抽样种子
输入文件 checksum
输出文件 checksum
```

抽样必须使用固定随机种子，保证 410 条评测集可重复生成。

## RAGAS 接入

RAGAS 的完整接入、document scope、运行时 trace、指标分层、成本控制和验证工件见：[RAGAS 评测接入实施方案](architecture/ragas-evaluation-integration.md)。

## 构建产物与命令

| 路径 | 内容 |
|---|---|
| `evals/cuad/corpus.json` | 当前文件是 100 份快速档清单；目标全量档升级为 510 份完整清单，改变后必须重新 ingestion |
| `evals/cuad/golden.jsonl` | 当前 410 条分层抽样；全量档启用时从 510 份合同的完整槽位重建 |
| `evals/cuad/categories.json` | 41 个 category 的描述与问题模板，已 review 的输入；与 CUAD 源不一致就会被拒绝 |
| `evals/cuad/build-report.json` | 抽样种子、输入/输出 checksum、category 分布、语料覆盖率、偏差与已知边界 |
| `evals/routing/contrast.jsonl` | 人工维护的两类路由对照样本 |

```powershell
# 构建（写入三个文件）、校验（重算并与已提交产物逐字节对比，不写入）
uv run python scripts/build-goldenset.py
uv run python scripts/build-goldenset.py --verify

# 把 golden.jsonl 投射到 RAGAS 列（不依赖 ragas 包）
uv run python scripts/goldenset_to_ragas.py
```

评测器将 `question`/`evidence` 投影到 `user_input`/`reference_contexts`，再按 `id` 关联运行时的 `retrieved_contexts` 和 `response`。RAGAS 所需的运行时列不存入 goldenset。goldenset 不保存 `reference`（参考 prose answer），因此 collections API 的 `ContextRecall`、带 reference 的 `ContextPrecision` 与 `FactualCorrectness` 不可用；`Evidence Recall` 是独立的确定性行区间指标。`goldenset_to_ragas.py` 当前打印的 NonLLM 指标名来自 legacy API，仅作列/指标盘点，不表示已与 RAGAS 0.4.3 collections API 兼容。

## 已知边界

- CUAD 是 out-of-domain 基线而非产品语料，`answers[].answer_start` 属于 CUAD 自己的 TXT 抽取，不是本平台坐标（见 `datasets/cuad/MANIFEST.json`）。
- evidence 是人工标注文本，含 SEC 脱敏占位符（`*`、`_`、`[]`、`omitted`）的 span 无法在源 PDF 中逐字找回；具体数量见构建报告的 `warnings`。
- evidence 的数组顺序不是文档顺序，投射后必须按平台自己的行号重排。
- 当前 100 合同快速档按覆盖度挑选，偏向罕见条款较多的合同，不代表 CUAD 平均合同；全量档需覆盖全部 510 份，才能声称对 20,910 个槽位完成确定性评测。
- `evals/cuad/corpus.json` 绑定已入库的集合。换源、改选择规则或改 `CORPUS_SEED` 都会换一批合同，必须重新 ingestion，之前基于旧语料的测量全部失效；改动时构建脚本会直接报错而不是静默覆写。
- CUAD 每个 category 在源里只有 510 个槽位，低空 evidence 类别（`Document Name`、`Parties`）无法凑足 5 条弃答样本，偏差逐类记在构建报告里；这两项是结构性的，换语料也消不掉。