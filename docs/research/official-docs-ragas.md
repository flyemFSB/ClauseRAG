# 官方文档核对：RAGAS 评测集与指标（Official docs cross-check）

日期：2026-10-06 · 抓取方式：直接抓取 `docs.ragas.io` 稳定版页面（`/en/stable/...`）。

抓取页面（均 200）：

1. `/getstarted/rag_eval/` — Evaluate a simple RAG system
2. `/concepts/metrics/available_metrics/` — 指标清单
3. `/concepts/metrics/available_metrics/faithfulness/`
4. `/concepts/metrics/available_metrics/context_precision/`
5. `/concepts/metrics/available_metrics/context_recall/`
6. `/concepts/metrics/available_metrics/answer_relevance/`
7. `/concepts/test_data_generation/` — 只有一句定位说明；其子页（`.../ragas/`、`.../synthetic_data/`）返回 404，
   本次没拿到可引用的合成数据集方法论细节，下文第 7 节按“文档未给”处理。

本文服务于 `docs/goldenset-construction.md` 的 goldenset 构建与评测分层。只记录官方文档声明与本次取舍；
文档没写的写明“文档未给”。

---

## 1. 评测集是一张列契约，不是一个类型

官方把评测数据当成“每行一组列”，`evaluate()` 吃的就是这些列：

> To collect evaluation data, we first need a set of queries to run against our RAG. We can run the
> queries through the RAG system and collect the `response`, `retrieved_contexts` for each query.
> You may also optionally prepare a set of golden answers for each query to evaluate the system's
> performance.
>
> ```python
> dataset.append({"user_input": query, "retrieved_contexts": relevant_docs, "response": response})
> ```
>
> —— <https://docs.ragas.io/en/stable/getstarted/rag_eval/>

**含义（对本项目）**：goldenset 不需要是 RAGAS 的类型，也不需要 import `ragas`。它只要提供
`user_input`（问题）与 `reference_contexts`/`reference` 中它真正拥有的那部分；`retrieved_contexts`
与 `response` 由评测运行时按 `id` 关联。这就是 `scripts/goldenset_to_ragas.py` 的全部职责——
它刻意不 import `ragas`，因此换评测器（或升级 RAGAS 大版本）都不动 goldenset。

## 2. 已有参考上下文时，直接当 `reference_contexts` 用

非 LLM 版的上下文精确率/召回率都是拿 `retrieved_contexts` 与 `reference_contexts` 比对：

> The `NonLLMContextPrecisionWithReference` metric is designed for scenarios where both retrieved
> contexts and reference contexts are available for a `user_input`. To determine if a retrieved
> context is relevant, this method compares each retrieved context or chunk in `retrieved_contexts`
> with every context in `reference_contexts` using a non-LLM-based similarity measure. Note that
> this metric would need the rapidfuzz package to be installed.
>
> —— <https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/>

**含义（对本项目）**：CUAD 的 `evidence` 就是人工标注的参考上下文，直接映射为 `reference_contexts`，
不需要先用 LLM 合成参考答案。这也让“全量 20,910 条不调评测 LLM”的确定性评测层可以覆盖上下文指标。

## 3. 没有参考答案时，哪些指标能用

LLM 版上下文召回**必须有**参考答案，它把参考答案当 `reference_contexts` 的代理：

> The LLM-based Context Recall metric uses `reference` as a proxy to `reference_contexts`, which
> makes it easier to use as annotating reference contexts can be very time-consuming. To estimate
> context recall from the `reference`, the reference is broken down into claims, and each claim is
> analyzed to determine whether it can be attributed to the retrieved context or not.
>
> —— <https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/>

而上下文精确率有免参考答案的版本：

> The `LLMContextPrecisionWithoutReference` metric can be used without the availability of a
> reference answer. To estimate if the retrieved contexts are relevant, this method uses the LLM to
> compare each chunk in `retrieved_contexts` with the `response`.
>
> —— <https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/>

Faithfulness 只用问题、回答与检索上下文（示例签名里没有 `reference`），Answer Relevancy 只用
`user_input` 与 `response`。

**含义（对本项目）**：goldenset 不存参考答案，因此可用集是

| 指标 | 需要的列 | 本项目是否可用 |
|---|---|---|
| `Faithfulness` | user_input, response, retrieved_contexts | 可用 |
| `AnswerRelevancy` | user_input, response | 可用（需 embedding 模型） |
| `LLMContextPrecisionWithoutReference` | user_input, response, retrieved_contexts | 可用 |
| `NonLLMContextPrecisionWithReference` | retrieved_contexts, reference_contexts | 可用（需 rapidfuzz） |
| `NonLLMContextRecall` | retrieved_contexts, reference_contexts | 可用 |
| `IDBasedContextRecall` | retrieved_context_ids, reference_context_ids | 需把 child id 当参考 id，本项目改用坐标校验 |
| `LLMContextRecall` | reference, retrieved_contexts | **不可用** |
| `LLMContextPrecisionWithReference` | reference, retrieved_contexts | **不可用** |
| `FactualCorrectness` | response, reference | **不可用** |

## 4. 不要绑定指标类名：legacy API 已宣告移除

> This API will be deprecated in version 0.4 and removed in version 1.0. Please migrate to the
> collections-based API shown above.
>
> —— <https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/>

**含义（对本项目）**：`from ragas.metrics import Faithfulness` 这类 import 有明确寿命。适配层因此只承诺
**列名**（`user_input` / `retrieved_contexts` / `response` / `reference_contexts`），不承诺类名；
`scripts/goldenset_to_ragas.py` 的文档里那张表是提示不是依赖。

## 5. Answer Relevancy 不是纯 LLM judge

> 1. Generate a set of artificial questions (default is 3) based on the response. ...
> 2. Compute the cosine similarity between the embedding of the user input ($E_o$) and the embedding
>    of each generated question ($E_{g_i}$). 3. Take the average of these cosine similarity scores
>
> —— <https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/>

同页还提醒该分数**不保证落在 0–1**（“While the score usually falls between 0 and 1, it is not
guarantee…”），且 `strictness` 默认 3 会决定生成几个问题。

**含义（对本项目）**：它需要 embedding 模型而非只靠评测 LLM；报告里出现 >1 的分数不是 bug。

## 6. 输出键是类名的小写

`evaluate(...)` 的返回示例是 `{'context_recall': 1.0000, 'faithfulness': 0.8571,
'factual_correctness': 0.7280}`（`/getstarted/rag_eval/`）。**含义**：报告字段实际上绑在指标类名上，
这也是第 4 条的另一个理由——归档评测报告时同时记录 RAGAS 版本。

## 7. 合成数据集生成：本项目的取舍

`/concepts/test_data_generation/` 正文只有一句定位：

> Curating a high quality test dataset is crucial for evaluating the performance of your AI
> application.

**含义（对本项目）**：合成数据集是“没有人工标注时”的替代路径。CUAD 已经有 20,910 个人工标注槽位，
再用 LLM 合成问题只会把人工标注换成模型生成，降低金标可信度——与「可追溯的记录」冲突。因此
goldenset 的 question/evidence 全部取自 CUAD 原始标注，不做任何 LLM 改写。

## 文档未给的

- 空 `reference_contexts`（弃答样本）下各指标的行为，文档未给。本项目按
  `docs/goldenset-construction.md` 的规定处理：弃答决策走确定性检查，不喂给上下文指标。
- `evaluate()` 对多余列（例如 `id`）是否报错，文档未给。适配层因此把 `id` 留在 RAGAS 行之外，
  由调用方用它回填分数。
