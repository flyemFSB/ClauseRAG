# RAGAS 官方接入调研摘要

调研基线：RAGAS `0.4.3`，Python `>=3.9`；ClauseRAG 固定使用 Python 3.12，因此应在 `uv.lock` 中锁定 RAGAS 的确切版本，而不是依赖浮动版本。

## 关键 API

- `SingleTurnSample` 支持 `user_input`、`response`、`retrieved_contexts`、`reference`、`reference_contexts`、`retrieved_context_ids` 和 `reference_context_ids`。
- RAGAS 0.4.3 的现代指标从 `ragas.metrics.collections` 导入，使用 `await metric.ascore(...)` 或 `await metric.abatch_score(...)`。
- 现代集合指标包括 `Faithfulness`、`AnswerRelevancy`、`ContextPrecisionWithoutReference`、`ContextPrecisionWithReference`、`ContextRecall` 和 `QuotedSpansAlignment`。
- `Faithfulness` 需要 `user_input`、`response`、`retrieved_contexts`。
- `AnswerRelevancy` 需要 `user_input`、`response`、LLM 和 embeddings。
- `ContextPrecisionWithoutReference` 需要 `user_input`、`response`、`retrieved_contexts`。
- `ContextRecall` 和 `ContextPrecisionWithReference` 需要 `reference`，而 CUAD 当前只标注 evidence spans，没有人工参考答案，不能伪造 `reference`。
- `NonLLMContextPrecisionWithReference` 和 `NonLLMContextRecall` 存在于 legacy `ragas.metrics` API（并需要 `rapidfuzz`），但不在 0.4.3 的 `ragas.metrics.collections` 导出中。若有迁移期需要，可将其作为可选文本相似度基线；它们不检查行坐标或 child 锚点，也不应作为长期 API 契约。
- `QuotedSpansAlignment` 检查回答中的引号文本是否出现在上下文中，不理解 ClauseRAG 的 `[S1]` 引用协议，因此不能代替 citation validation。

## 模型与运行控制

OpenAI-compatible 服务可以通过 `AsyncOpenAI(base_url=...)` 配合：

```python
from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory

judge = llm_factory("judge-model", client=async_client, cache=cache)
embeddings = embedding_factory(
    "openai", model="embedding-model", client=async_client, cache=cache
)
```

官方 `evaluate()`/`aevaluate()` 仍支持数据集、指标、`batch_size`、`raise_exceptions`、`return_executor`、`column_map`、token usage 和 `RunConfig`，但 0.4.x 已将它们标记为向 `@experiment` 迁移；新代码不应依赖旧的 `ragas.metrics` 导入或 `single_turn_ascore()`。首版应直接调用现代集合指标的 `ascore`，由 ClauseRAG 自己保存样本 ID、运行元数据、失败状态和坐标信息。

`RunConfig` 官方默认值为 `timeout=180`、`max_retries=10`、`max_wait=60`、`max_workers=16`、`seed=42`。生产评测必须显式降低并发、限制重试，并只对瞬时供应商错误重试。官方提供 `DiskCacheBackend`，但缓存目录必须位于受控评测工作区，且缓存身份应包含模型和评测配置。

## 对 ClauseRAG 的结论

RAGAS 只负责 LLM/embedding 质量指标，不负责：

- CUAD evidence 到 normalized Markdown 行区间的投影；
- child chunk 覆盖判断；
- document/version isolation；
- `[S1]` 到有效 child/citation 坐标的校验；
- evidence gate 和 abstention 正确性。

这些必须由 ClauseRAG 的确定性评测器先计算，再把实际回答和实际生成上下文投影成 RAGAS 样本。CUAD 没有参考答案时，首版使用 Faithfulness、AnswerRelevancy 和无参考 Context Precision；Context Recall、带 reference 的 Context Precision、Answer/Factual Correctness 留给未来增加人工 `reference_answer` 后的评测集。Legacy NonLLM context precision/recall 仅作为可选文本匹配基线，不替代坐标级 Evidence Recall。

## 一手来源

- https://pypi.org/project/ragas/
- https://github.com/vibrantlabsai/ragas/releases/tag/v0.4.3
- https://docs.ragas.io/en/stable/getstarted/rag_eval/
- https://docs.ragas.io/en/stable/references/evaluate/
- https://docs.ragas.io/en/stable/references/evaluation_schema/
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/
- https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04/
- https://docs.ragas.io/en/stable/howtos/customizations/customize_models/
- https://docs.ragas.io/en/stable/howtos/customizations/_caching/
- https://docs.ragas.io/en/stable/references/run_config/
- https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/__init__.py
- https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/faithfulness/metric.py
- https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/context_precision/metric.py
- https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/context_recall/metric.py
- https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_context_recall.py
- https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_context_precision.py
- https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/embeddings/base.py
- https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/answer_relevancy/metric.py
