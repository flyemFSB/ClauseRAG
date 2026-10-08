"""RAGAS 评测引擎：唯一的 judge/embedding 客户端、指标集与结构化输出 smoke 校验。

只有本模块 import ragas，而 ragas 只存在于 `eval` 依赖组：

    uv run --group eval python -m cli evaluate-ragas --mode smoke

业务进程（api / worker / agent_runtime）既不在启动路径上导入本模块，也不导入 `cli.commands.evaluate`
的引擎，因此生产部署用 `uv sync --locked --no-group eval` 即可完全不装评测库。

RAGAS 只负责 LLM/embedding 质量指标。evidence 到 normalized Markdown 行区间的投影、child 覆盖、
document/version 隔离、`[S1]` 权威回表与弃答正确性都由 ClauseRAG 的确定性评测器计算，不经过本模块。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

try:
    from openai import AsyncOpenAI
    from ragas.cache import DiskCacheBackend
    from ragas.embeddings.base import BaseRagasEmbedding, embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithoutReference,
        Faithfulness,
    )
except ModuleNotFoundError as error:  # pragma: no cover - 依赖缺失时的唯一出口
    raise ModuleNotFoundError(
        f"RAGAS 评测依赖不可用（缺少 {error.name}）：请用 `uv run --group eval` 运行评测命令。"
    ) from error

from infrastructure.evaluation.specs import (
    ANSWER_RELEVANCY,
    CONTEXT_PRECISION_WITHOUT_REFERENCE,
    FAITHFULNESS,
    V1_METRICS,
    MetricSpec,
    missing_columns,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ragas.metrics.result import MetricResult

    from infrastructure.config.settings import Settings

#: smoke 行：自洽、极短，只用来验证列需求与 provider 的结构化输出，不代表任何评测结果。
SMOKE_ROW: dict[str, object] = {
    "user_input": "When does the agreement expire?",
    "response": "The agreement expires on 31 December 2024 unless it is renewed.",
    "generator_contexts": [
        "The Agreement shall expire on 31 December 2024 unless renewed by the parties."
    ],
    "ranked_candidate_contexts": [
        "The Agreement shall expire on 31 December 2024 unless renewed by the parties."
    ],
}


@dataclass(frozen=True)
class JudgeConfig:
    """一次评测运行的 judge/embedding 配置。

    judge 与 embedding **可以指向不同服务商**：judge 跟着对话端点走（`CHAT_*`，留空时回落
    SiliconFlow），而 embedding 固定在 SiliconFlow 的 bge-m3 —— 它不是一个 LLM，拿 judge 端点去
    请求 bge-m3 会被服务商拒绝。
    """

    api_key: str
    base_url: str
    judge_model: str
    embedding_api_key: str
    embedding_base_url: str
    embedding_model: str
    max_concurrency: int
    timeout_seconds: int
    max_retries: int
    cache_dir: Path
    answer_relevancy_strictness: int


@dataclass(frozen=True)
class MetricScore:
    """一个指标在一行样本上的结果；失败与跳过都不是 0 分，必须分开报告。"""

    name: str
    status: Literal["ok", "skipped", "error"]
    value: float | None = None
    reason: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    latency_ms: int = 0


def judge_config(settings: Settings) -> JudgeConfig:
    """解析评测 judge 配置；**未配置评测专用凭据时回落到 SiliconFlow**。

    回落是显式默认值而不是静默降级：成本与质量风险由调用方在启动时打印，而不是把一次打分失败
    伪装成低分。judge 与 embedding 共用同一个 client、同一个缓存目录和同一个并发门。
    """
    api_key = settings.eval_judge_api_key or settings.chat_api_key or settings.siliconflow_api_key
    return JudgeConfig(
        api_key=api_key.get_secret_value(),
        base_url=settings.eval_judge_base_url
        or settings.chat_base_url
        or settings.siliconflow_base_url,
        judge_model=settings.eval_judge_model or settings.chat_model,
        embedding_api_key=settings.siliconflow_api_key.get_secret_value(),
        embedding_base_url=settings.siliconflow_base_url,
        embedding_model=settings.eval_embedding_model or settings.embedding_model,
        max_concurrency=settings.eval_max_concurrency,
        timeout_seconds=settings.eval_timeout_seconds,
        max_retries=settings.eval_max_retries,
        cache_dir=Path(settings.eval_cache_dir),
        answer_relevancy_strictness=settings.eval_answer_relevancy_strictness,
    )


class RagasEngine:
    """一次评测运行的唯一客户端、缓存与并发门。

    重试交给 OpenAI client 自己的分类重试（只覆盖 408/409/429/5xx 与连接错误），因此这里不再叠一层
    重试：两层重试会把供应商限流放大成尖峰。
    """

    def __init__(self, config: JudgeConfig) -> None:
        self._config = config
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        self._gate = asyncio.Semaphore(config.max_concurrency)
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        self._cache = DiskCacheBackend(str(config.cache_dir))
        self._judge = llm_factory(
            config.judge_model, provider="openai", client=self._client, cache=self._cache
        )
        # Embedding 保持独立端点：AnswerRelevancy 依赖向量嵌入，不可随裁判模型路由至纯对话端点。
        self._embedding_client = AsyncOpenAI(
            api_key=config.embedding_api_key,
            base_url=config.embedding_base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        # embedding_factory 的返回类型是 legacy/modern 的联合；传入 client 即走 modern 分支，
        # 这里收窄到 AnswerRelevancy 接受的接口。
        self._embeddings = cast(
            "BaseRagasEmbedding",
            embedding_factory(
                "openai",
                model=config.embedding_model,
                client=self._embedding_client,
                cache=self._cache,
            ),
        )

    async def __aenter__(self) -> RagasEngine:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._embedding_client.close()
        await self._client.close()

    async def score(self, spec: MetricSpec, row: Mapping[str, object]) -> MetricScore:
        """在 ``row`` 上跑一个指标，把跳过、失败和成功分开返回。"""
        missing = missing_columns(spec, row)
        if missing:
            return MetricScore(
                name=spec.name, status="skipped", reason=f"缺少列: {', '.join(missing)}"
            )
        started = time.perf_counter()
        try:
            async with self._gate:
                result = await self._call(spec, row)
        except Exception as error:  # 单行失败必须记录而不是中断整轮评测
            return MetricScore(
                name=spec.name,
                status="error",
                error_class=type(error).__name__,
                error_message=str(error)[:500],
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        return MetricScore(
            name=spec.name,
            status="ok",
            value=float(result.value),
            reason=result.reason,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def _call(self, spec: MetricSpec, row: Mapping[str, object]) -> MetricResult:
        user_input = str(row["user_input"])
        response = str(row["response"])
        contexts = (
            [str(item) for item in cast("list[object]", row[spec.contexts])]
            if spec.contexts is not None
            else []
        )
        if spec.name == FAITHFULNESS:
            metric = Faithfulness(llm=self._judge)
            return await metric.ascore(
                user_input=user_input, response=response, retrieved_contexts=contexts
            )
        if spec.name == ANSWER_RELEVANCY:
            metric = AnswerRelevancy(
                llm=self._judge,
                embeddings=self._embeddings,
                strictness=self._config.answer_relevancy_strictness,
            )
            return await metric.ascore(user_input=user_input, response=response)
        if spec.name == CONTEXT_PRECISION_WITHOUT_REFERENCE:
            metric = ContextPrecisionWithoutReference(llm=self._judge)
            return await metric.ascore(
                user_input=user_input, response=response, retrieved_contexts=contexts
            )
        raise ValueError(f"metric {spec.name!r} has no call wiring")

    async def smoke(self) -> tuple[MetricScore, ...]:
        """用一行 dummy 样本逐个验证指标的列需求与 provider 的结构化输出。

        串行执行以便把失败定位到具体指标。任一指标不是 ``ok`` 就说明该 provider
        还不能承担这一版评测。
        """
        scores: list[MetricScore] = []
        for spec in V1_METRICS:
            scores.append(await self.score(spec, SMOKE_ROW))
        return tuple(scores)
