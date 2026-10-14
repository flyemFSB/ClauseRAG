"""检索综合流水线编排服务：多路召回、回表、RRF 融合、重排、门控与上下文构建。"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from application.retrieval.context import ContextSelection
from application.retrieval.fanout import ChannelFanOut, elapsed_ms
from application.retrieval.models import RetrievalDiagnostics, RetrievalResult
from domain.citation import CitationSource, render_context
from domain.retrieval import (
    Candidate,
    ChannelHit,
    ChannelResult,
    EvidenceDecision,
    MergedHit,
    RerankError,
    RerankReport,
    RerankStatus,
    gate_evidence,
    merge_channel_hits,
    order_by_rerank,
    score_merged_hits,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from application.retrieval.channels import RetrievalChannel
    from application.retrieval.chunks import ChunkStore
    from application.shared.providers import Reranker
    from domain.chunks.model import TokenCounter
    from domain.retrieval import ChannelName, ChunkRecord, RetrievalBudget

log = structlog.get_logger(__name__)


def normalize_queries(queries: Sequence[str], *, fallback: str) -> tuple[str, ...]:
    """去除空白查询、按顺序去重，全部为空时回退到原始问题"""
    unique = tuple(dict.fromkeys(cleaned for query in queries if (cleaned := query.strip())))
    return unique or (fallback,)


class RetrievalService:
    """多路混合检索应用服务"""

    def __init__(
        self,
        *,
        channels: Sequence[RetrievalChannel],
        chunks: ChunkStore,
        reranker: Reranker,
        budget: RetrievalBudget,
        counter: TokenCounter,
        channel_timeout_seconds: int,
        rerank_timeout_seconds: int,
        rerank_limit: int,
        rerank_max_documents: int,
        min_rerank_score: float,
        citation_quote_chars: int,
    ) -> None:
        self._channels = tuple(channels)
        self._chunks = chunks
        self._reranker = reranker
        self._budget = budget
        self._channel_timeout_seconds = channel_timeout_seconds
        self._rerank_timeout_seconds = rerank_timeout_seconds
        self._rerank_limit = rerank_limit
        self._rerank_max_documents = rerank_max_documents
        self._min_rerank_score = min_rerank_score
        self._citation_quote_chars = citation_quote_chars
        self._fan_out = ChannelFanOut(
            channels=channels,
            budget=budget,
            timeout_seconds=channel_timeout_seconds,
        )
        self._context = ContextSelection(
            budget=budget,
            quote_chars=citation_quote_chars,
            counter=counter,
        )

    @property
    def budget(self) -> RetrievalBudget:
        """获取当前检索阶段的预算与权重配置"""
        return self._budget

    async def retrieve(
        self,
        *,
        knowledge_base_id: UUID,
        query: str,
        rewritten_queries: Sequence[str] = (),
    ) -> RetrievalResult:
        """执行完整检索流水线并输出证据决策与上下文"""
        queries = normalize_queries(tuple(rewritten_queries) or (query,), fallback=query)
        started = time.perf_counter()
        channels = await self._run_channels(knowledge_base_id=knowledge_base_id, queries=queries)
        records = await self._hydrate(knowledge_base_id=knowledge_base_id, channels=channels)
        fused = self._fuse(merged_hits=self._deduplicate(channels=channels, records=records))
        reranked, rerank = await self._rerank(query=query, candidates=fused)
        evidence = self._gate(candidates=reranked, rerank=rerank)
        sources, context_tokens = self._select_context(candidates=reranked, evidence=evidence)
        log.info(
            "检索流水线执行完成",
            knowledge_base_id=str(knowledge_base_id),
            queries=len(queries),
            channels=len(channels),
            fused=len(fused),
            reranked=len(reranked),
            sources=len(sources),
            context_tokens=context_tokens,
            gate=evidence.status.value,
            rerank=rerank.status.value,
            latency_ms=elapsed_ms(started),
        )
        return RetrievalResult(
            evidence=evidence,
            sources=sources,
            context=render_context(sources),
            context_tokens=context_tokens,
            diagnostics=RetrievalDiagnostics(
                queries=queries,
                channels=channels,
                fused=fused,
                reranked=reranked,
                rerank=rerank,
            ),
        )

    async def _run_channels(
        self,
        *,
        knowledge_base_id: UUID,
        queries: Sequence[str],
    ) -> tuple[ChannelResult, ...]:
        """并发请求各检索渠道"""
        return await self._fan_out.run(knowledge_base_id=knowledge_base_id, queries=queries)

    async def _hydrate(
        self,
        *,
        knowledge_base_id: UUID,
        channels: Sequence[ChannelResult],
    ) -> Mapping[UUID, ChunkRecord]:
        """批量读取并补全各渠道召回记录的完整元数据"""
        child_ids = [hit.child_id for result in channels for hit in result.hits]
        if not child_ids:
            return {}
        started = time.perf_counter()
        records = await self._chunks.load_records(
            knowledge_base_id=knowledge_base_id,
            child_ids=child_ids,
        )
        log.info(
            "检索候选回表补全完成",
            knowledge_base_id=str(knowledge_base_id),
            hits=len(child_ids),
            records=len(records),
            latency_ms=elapsed_ms(started),
        )
        return records

    @staticmethod
    def _deduplicate(
        *,
        channels: Sequence[ChannelResult],
        records: Mapping[UUID, ChunkRecord],
    ) -> tuple[MergedHit, ...]:
        """按版本与子块去重合并多渠道召回项"""
        hits_by_channel: dict[ChannelName, Sequence[ChannelHit]] = {}
        for result in channels:
            hits_by_channel[result.channel] = result.hits
        return merge_channel_hits(hits_by_channel, records)

    def _fuse(self, *, merged_hits: Sequence[MergedHit]) -> tuple[Candidate, ...]:
        """执行 RRF 倒数排名融合"""
        return score_merged_hits(merged_hits, budget=self._budget)

    async def _rerank(
        self,
        *,
        query: str,
        candidates: Sequence[Candidate],
    ) -> tuple[tuple[Candidate, ...], RerankReport]:
        """调用重排模型重排候选块，模型不可用时降级为融合结果"""
        limited = tuple(candidates[: self._rerank_limit])
        if not limited:
            return (), RerankReport(
                status=RerankStatus.SKIPPED,
                model=None,
                scored=0,
                reason="no candidate to rerank",
            )
        documents = [candidate.record.content for candidate in limited]
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._rerank_timeout_seconds):
                scores_by_index = await self._reranker.rerank(
                    query=query,
                    documents=documents,
                    top_n=min(self._rerank_max_documents, len(limited)),
                )
        except asyncio.CancelledError:
            raise
        except (RerankError, TimeoutError) as error:
            log.warning(
                "重排服务异常，降级回退至RRF排序",
                error_type=type(error).__name__,
                candidates=len(limited),
                model=self._reranker.model,
                latency_ms=elapsed_ms(started),
            )
            return limited, RerankReport(
                status=RerankStatus.DEGRADED,
                model=self._reranker.model,
                scored=0,
                reason=type(error).__name__,
            )
        scores = {limited[index].child_id: score for index, score in scores_by_index.items()}
        report = RerankReport(
            status=RerankStatus.OK,
            model=self._reranker.model,
            scored=len(scores),
        )
        log.info(
            "重排打分完成",
            candidates=len(limited),
            scored=report.scored,
            model=report.model,
            latency_ms=elapsed_ms(started),
        )
        return order_by_rerank(limited, scores), report

    def _gate(
        self,
        *,
        candidates: Sequence[Candidate],
        rerank: RerankReport,
    ) -> EvidenceDecision:
        """判定候选块是否通过证据门控阈值（重排不可用时 fail-closed）"""
        decision = gate_evidence(
            candidates,
            min_rerank_score=self._min_rerank_score,
            rerank=rerank,
        )
        log.info(
            "证据门控判定完成",
            status=decision.status.value,
            accepted=len(decision.accepted),
            candidates=len(candidates),
            rerank=rerank.status.value,
        )
        return decision

    def _select_context(
        self,
        *,
        candidates: Sequence[Candidate],
        evidence: EvidenceDecision,
    ) -> tuple[tuple[CitationSource, ...], int]:
        """从有效证据中组装上下文并计算 Token 预算"""
        started = time.perf_counter()
        sources, tokens = self._context.select(candidates=candidates, evidence=evidence)
        log.info(
            "上下文资料组装完成",
            sources=len(sources),
            context_tokens=tokens,
            latency_ms=elapsed_ms(started),
        )
        return sources, tokens
