"""多路检索、RRF 融合、重排与证据门控领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from domain.chunks.model import BlockType


class ChannelName(StrEnum):
    """检索渠道枚举"""

    DENSE = "dense"
    KEYWORD = "keyword"


class ChannelStatus(StrEnum):
    """检索渠道执行状态"""

    OK = "ok"
    """成功召回至少一条记录"""

    EMPTY = "empty"
    """执行成功但无匹配结果"""

    FAILED = "failed"
    """渠道执行失败"""


@dataclass(frozen=True, slots=True)
class ChannelMatch:
    """各渠道原始召回项（尚未在渠道内重编号排序）"""

    child_id: UUID
    parent_id: UUID
    document_version_id: UUID
    score: float | None


@dataclass(frozen=True, slots=True)
class ChannelHit:
    """渠道排序后的单项召回结果"""

    child_id: UUID
    parent_id: UUID
    document_version_id: UUID
    rank: int
    raw_score: float | None


@dataclass(frozen=True, slots=True)
class ChannelResult:
    """单渠道单轮检索响应结果"""

    channel: ChannelName
    status: ChannelStatus
    hits: tuple[ChannelHit, ...]
    latency_ms: int
    error_type: str | None = None

    @staticmethod
    def failed(
        channel: ChannelName,
        *,
        error_type: str,
        latency_ms: int,
    ) -> ChannelResult:
        """构建失败的渠道结果"""
        return ChannelResult(
            channel=channel,
            status=ChannelStatus.FAILED,
            hits=(),
            latency_ms=latency_ms,
            error_type=error_type,
        )


@dataclass(frozen=True, slots=True)
class RetrievalBudget:
    """单轮检索各渠道 Top-K 与融合重排预算配置"""

    dense_top_k: int
    keyword_top_k: int
    fusion_limit: int
    rerank_limit: int
    final_parent_limit: int
    max_context_tokens: int
    max_retrieval_rounds: int
    rrf_rank_constant: int
    dense_weight: float
    keyword_weight: float

    def top_k_for(self, channel: ChannelName) -> int:
        """获取指定渠道的最大召回数量"""
        return {
            ChannelName.DENSE: self.dense_top_k,
            ChannelName.KEYWORD: self.keyword_top_k,
        }[channel]

    def weight_for(self, channel: ChannelName) -> float:
        """获取指定渠道的 RRF 融合权重"""
        return {
            ChannelName.DENSE: self.dense_weight,
            ChannelName.KEYWORD: self.keyword_weight,
        }[channel]


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    """从数据库回表补全的子块完整元数据"""

    child_id: UUID
    parent_id: UUID
    document_version_id: UUID
    document_id: UUID
    knowledge_base_id: UUID
    document_name: str
    heading_path: tuple[str, ...]
    block_type: BlockType
    ordinal: int
    line_start: int
    line_end: int
    content: str
    token_count: int
    parent_content: str
    parent_token_count: int


@dataclass(frozen=True, slots=True)
class MergedHit:
    """去重合并后的块及各渠道排名映射"""

    record: ChunkRecord
    channel_ranks: Mapping[ChannelName, int]


@dataclass(frozen=True, slots=True)
class Candidate:
    """RRF 融合与重排后的候选块实体"""

    record: ChunkRecord
    channel_ranks: Mapping[ChannelName, int]
    rrf_score: float
    rerank_score: float | None = None

    @property
    def child_id(self) -> UUID:
        """子块唯一标识"""
        return self.record.child_id

    @property
    def parent_id(self) -> UUID:
        """父块唯一标识"""
        return self.record.parent_id

    @property
    def ordinal(self) -> int:
        """文档内部全局序号"""
        return self.record.ordinal

    def with_rerank_score(self, score: float) -> Candidate:
        """附加重排得分"""
        return replace(self, rerank_score=score)


def merge_channel_hits(
    hits_by_channel: Mapping[ChannelName, Sequence[ChannelHit]],
    records: Mapping[UUID, ChunkRecord],
) -> tuple[MergedHit, ...]:
    """跨渠道按 (document_version_id, child_id) 去重并保留各渠道最优排名"""
    ranks: dict[tuple[UUID, UUID], dict[ChannelName, int]] = {}
    for channel, hits in hits_by_channel.items():
        for hit in hits:
            if hit.child_id not in records:
                continue
            key = (hit.document_version_id, hit.child_id)
            per_channel = ranks.setdefault(key, {})
            per_channel[channel] = min(per_channel.get(channel, hit.rank), hit.rank)

    merged: list[MergedHit] = []
    for (version_id, child_id), per_channel in ranks.items():
        record = records.get(child_id)
        if record is None or record.document_version_id != version_id:
            continue
        merged.append(MergedHit(record=record, channel_ranks=dict(per_channel)))
    return tuple(merged)


def score_merged_hits(
    merged_hits: Sequence[MergedHit],
    *,
    budget: RetrievalBudget,
) -> tuple[Candidate, ...]:
    """计算 RRF 融合得分并按得分降序截取指定预算长度"""
    candidates = [
        Candidate(
            record=merged.record,
            channel_ranks=merged.channel_ranks,
            rrf_score=sum(
                budget.weight_for(channel) / (budget.rrf_rank_constant + rank)
                for channel, rank in merged.channel_ranks.items()
            ),
        )
        for merged in merged_hits
    ]
    candidates.sort(key=lambda candidate: (-candidate.rrf_score, str(candidate.child_id)))
    return tuple(candidates[: budget.fusion_limit])


def rank_channel_matches(matches: Sequence[ChannelMatch]) -> tuple[ChannelHit, ...]:
    """对单渠道内部的召回记录进行去重并重新生成从 1 起始的连续排名"""
    best: dict[UUID, ChannelMatch] = {}
    order: dict[UUID, int] = {}
    for position, match in enumerate(matches):
        previous = order.get(match.child_id)
        if previous is None or position < previous:
            order[match.child_id] = position
            best[match.child_id] = match
    ranked = sorted(
        best.values(),
        key=lambda match: (
            order[match.child_id],
            -(match.score if match.score is not None else 0.0),
        ),
    )
    return tuple(
        ChannelHit(
            child_id=match.child_id,
            parent_id=match.parent_id,
            document_version_id=match.document_version_id,
            rank=rank,
            raw_score=match.score,
        )
        for rank, match in enumerate(ranked, start=1)
    )


def fuse_query_hits(
    ranked_hits: Sequence[Sequence[ChannelHit]],
    *,
    rank_constant: int,
) -> tuple[ChannelHit, ...]:
    """融合同一渠道内多个查询各自的排名（查询级 RRF），输出去重后的统一 1..N 排名"""
    scores: dict[UUID, float] = {}
    representatives: dict[UUID, ChannelHit] = {}
    for hits in ranked_hits:
        for hit in hits:
            scores[hit.child_id] = scores.get(hit.child_id, 0.0) + 1.0 / (rank_constant + hit.rank)
            previous = representatives.get(hit.child_id)
            # raw_score 只在同一候选的多次命中之间取最大，绝不跨候选相加
            if previous is None or (
                hit.raw_score is not None
                and (previous.raw_score is None or hit.raw_score > previous.raw_score)
            ):
                representatives[hit.child_id] = hit
    ranked = sorted(
        representatives.values(),
        key=lambda hit: (-scores[hit.child_id], str(hit.child_id)),
    )
    return tuple(
        ChannelHit(
            child_id=hit.child_id,
            parent_id=hit.parent_id,
            document_version_id=hit.document_version_id,
            rank=rank,
            raw_score=hit.raw_score,
        )
        for rank, hit in enumerate(ranked, start=1)
    )


def order_by_rerank(
    candidates: Sequence[Candidate],
    scores: Mapping[UUID, float],
) -> tuple[Candidate, ...]:
    """按重排得分降序重排候选块（无重排分时按 RRF 兜底）"""
    scored = [
        candidate.with_rerank_score(scores[candidate.child_id])
        if candidate.child_id in scores
        else candidate
        for candidate in candidates
    ]
    scored.sort(
        key=lambda candidate: (
            -(candidate.rerank_score if candidate.rerank_score is not None else -1.0),
            -candidate.rrf_score,
            str(candidate.child_id),
        )
    )
    return tuple(scored)


class RerankError(Exception):
    """重排处理基础异常"""


class RerankRejectedError(RerankError):
    """重排服务明确拒绝异常（鉴权失败、配额超限或参数非法）"""


class TransientRerankError(RerankError):
    """重排服务瞬时网络或超时错误（可自动重试）"""


class RerankStatus(StrEnum):
    """重排执行状态"""

    OK = "ok"
    """正常完成重排打分"""

    DEGRADED = "degraded"
    """重排不可用，候选仅按 RRF 顺序保留在诊断中，不得据此生成"""

    SKIPPED = "skipped"
    """输入候选为空，跳过重排"""


@dataclass(frozen=True, slots=True)
class RerankReport:
    """重排阶段执行诊断报告"""

    status: RerankStatus
    model: str | None
    scored: int
    reason: str | None = None


class EvidenceStatus(StrEnum):
    """证据门控判定状态"""

    SUFFICIENT = "sufficient"
    """证据充分（至少一个候选块达到重排阈值且内容完整）"""

    DEGRADED = "degraded"
    """重排不可用，证据质量无法核验：仅供诊断与展示，不得生成结论"""

    INSUFFICIENT = "insufficient"
    """证据不足，拒绝作答"""

    UNVERIFIED = "unverified"
    """回答已生成但未携带任何可查验引用，因此不得当作已 grounding 的结论"""


@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    """证据门控判定结果"""

    status: EvidenceStatus
    reason: str
    accepted: tuple[UUID, ...]

    @property
    def grounded(self) -> bool:
        """是否具备足够的事实依据支撑回答（只有 SUFFICIENT 才算核验通过）"""
        return self.status is EvidenceStatus.SUFFICIENT


def gate_evidence(
    candidates: Sequence[Candidate],
    *,
    min_rerank_score: float,
    rerank: RerankReport,
) -> EvidenceDecision:
    """判定检索召回块是否达到生成可信回答的证据门槛

    重排不可用时一律 fail-closed：没有经过核验的候选不得进入上下文，因为 Dense 余弦分与
    BM25 分与重排阈值不同量纲，未经标定不得互相替代。
    """
    if not candidates:
        return EvidenceDecision(
            status=EvidenceStatus.INSUFFICIENT,
            reason="no candidate survived retrieval",
            accepted=(),
        )
    if rerank.status is RerankStatus.DEGRADED:
        return EvidenceDecision(
            status=EvidenceStatus.DEGRADED,
            reason=rerank.reason or "rerank was unavailable; evidence cannot be verified",
            accepted=(),
        )
    if rerank.status is not RerankStatus.OK:
        return EvidenceDecision(
            status=EvidenceStatus.INSUFFICIENT,
            reason="rerank did not score the candidates",
            accepted=(),
        )
    with_content = [candidate for candidate in candidates if candidate.record.content.strip()]
    if not with_content:
        return EvidenceDecision(
            status=EvidenceStatus.INSUFFICIENT,
            reason="no candidate carried the stored text a citation quotes",
            accepted=(),
        )
    scored = [
        candidate
        for candidate in with_content
        if candidate.rerank_score is not None and candidate.rerank_score >= min_rerank_score
    ]
    if not scored:
        return EvidenceDecision(
            status=EvidenceStatus.INSUFFICIENT,
            reason=f"no candidate reached the rerank threshold {min_rerank_score}",
            accepted=(),
        )
    return EvidenceDecision(
        status=EvidenceStatus.SUFFICIENT,
        reason=f"{len(scored)} candidates reached the rerank threshold",
        accepted=tuple(candidate.child_id for candidate in scored),
    )
