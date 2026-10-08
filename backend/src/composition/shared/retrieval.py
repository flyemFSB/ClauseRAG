"""多路召回与重排资源配额装配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.retrieval import RetrievalBudget

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings


def retrieval_budget(settings: Settings) -> RetrievalBudget:
    """根据系统配置组装多渠道检索配额对象。"""
    return RetrievalBudget(
        dense_top_k=settings.dense_top_k,
        keyword_top_k=settings.keyword_top_k,
        fusion_limit=settings.fusion_limit,
        rerank_limit=settings.rerank_limit,
        final_parent_limit=settings.final_parent_limit,
        max_context_tokens=settings.max_context_tokens,
        max_retrieval_rounds=settings.max_retrieval_rounds,
        rrf_rank_constant=settings.rrf_rank_constant,
        dense_weight=settings.dense_channel_weight,
        keyword_weight=settings.keyword_channel_weight,
    )
