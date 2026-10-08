"""评测指标的列契约：哪些列每个指标要读、哪些指标在当前 goldenset 下不可用。

本模块**不 import ragas**，因此 goldenset 投影校验与服务侧代码都能读它；真正调用指标的适配代码
在 :mod:`infrastructure.evaluation.engine`。契约与适配分开，是因为「指标需要什么列」是评测数据形状的
事实，而「怎么调用 ragas」才是外部库的细节。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

FAITHFULNESS = "faithfulness"
ANSWER_RELEVANCY = "answer_relevancy"
CONTEXT_PRECISION_WITHOUT_REFERENCE = "context_precision_without_reference"

#: 上下文的两条来源不能混用：``generator_contexts`` 是实际送进回答模型的 source block，
#: ``ranked_candidate_contexts`` 是重排后的候选文本。
ContextSource = Literal["generator_contexts", "ranked_candidate_contexts"]


@dataclass(frozen=True)
class MetricSpec:
    """一个 RAGAS 指标读哪些列、走哪一路上下文、要不要 embedding、是否默认开启。"""

    name: str
    contexts: ContextSource | None
    uses_embeddings: bool = False
    default_enabled: bool = True


#: 首版指标集。缺的列由运行时的 trace 提供（``response`` 与两路上下文），goldenset 只提供
#: ``user_input`` 与 ``reference_contexts``。
V1_METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(FAITHFULNESS, contexts="generator_contexts"),
    MetricSpec(ANSWER_RELEVANCY, contexts=None, uses_embeddings=True),
    MetricSpec(
        CONTEXT_PRECISION_WITHOUT_REFERENCE,
        contexts="ranked_candidate_contexts",
        default_enabled=False,
    ),
)


@dataclass(frozen=True)
class UnavailableMetric:
    """一个当前不可用的指标，以及它缺什么、为什么缺。"""

    name: str
    missing: str
    reason: str


#: 不可用指标被写成数据而不是散落在注释里：报告必须能逐条说明「为什么这一版没有这个分数」。
UNAVAILABLE_METRICS: tuple[UnavailableMetric, ...] = (
    UnavailableMetric("context_recall", "reference", "CUAD 只标注 evidence 片段，没有人工参考答案"),
    UnavailableMetric(
        "context_precision_with_reference", "reference", "同上，evidence 不能冒充参考答案"
    ),
    UnavailableMetric("answer_correctness", "reference", "同上"),
    UnavailableMetric("factual_correctness", "reference", "同上"),
    UnavailableMetric(
        "non_llm_context_precision_with_reference",
        "public api",
        "ragas 0.4.3 只把它们导出为私有名 _NonLLM*，不构成公开契约",
    ),
    UnavailableMetric(
        "non_llm_context_recall",
        "public api",
        "同上；文本相似度也不检查行坐标或 child 锚点",
    ),
)


def missing_columns(spec: MetricSpec, row: Mapping[str, object]) -> tuple[str, ...]:
    """该指标在 ``row`` 上缺失或缺内容的列名；非空即应跳过而不是让 judge 去猜。"""
    needed = ["user_input", "response"]
    if spec.contexts is not None:
        needed.append(spec.contexts)
    return tuple(name for name in needed if not str(row.get(name) or "").strip())
