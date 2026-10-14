"""对话与检索调试相关的 HTTP 请求与响应模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from application.retrieval.cache import CACHE_SCHEMA_VERSION
from application.retrieval.models import RetrievalResult
from domain.citation import CitationSource
from domain.conversation import (
    CitationRecord,
    Conversation,
    ConversationDetail,
    Message,
)
from domain.retrieval import Candidate, ChannelResult, EvidenceDecision

_MAX_QUESTION_CHARS = 4000
_MAX_TITLE_CHARS = 200


class CreateConversationRequest(BaseModel):
    """创建对话请求"""

    title: str | None = Field(default=None, max_length=_MAX_TITLE_CHARS)


class RenameConversationRequest(BaseModel):
    """重命名对话请求"""

    title: str = Field(min_length=1, max_length=_MAX_TITLE_CHARS)


class AskRequest(BaseModel):
    """发送消息/提问请求"""

    content: str = Field(min_length=1, max_length=_MAX_QUESTION_CHARS)


class ConversationResponse(BaseModel):
    """对话概览响应"""

    id: UUID
    knowledge_base_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def from_conversation(conversation: Conversation) -> ConversationResponse:
        """从领域对象构建对话响应"""
        return ConversationResponse(
            id=conversation.id,
            knowledge_base_id=conversation.knowledge_base_id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class CitationResponse(BaseModel):
    """引用来源响应"""

    citation_id: str
    document_id: UUID
    document_version_id: UUID
    document_name: str
    parent_id: UUID
    child_ids: list[UUID]
    heading_path: list[str]
    line_start: int
    line_end: int
    quote: str

    @staticmethod
    def from_record(record: CitationRecord) -> CitationResponse:
        """从引用记录构建响应"""
        return CitationResponse(
            citation_id=record.citation_id,
            document_id=record.document_id,
            document_version_id=record.document_version_id,
            document_name=record.document_name,
            parent_id=record.parent_id,
            child_ids=[record.child_id],
            heading_path=list(record.heading_path),
            line_start=record.line_start,
            line_end=record.line_end,
            quote=record.quote,
        )


class MessageResponse(BaseModel):
    """对话消息响应（包含执行结果与引用）"""

    id: UUID
    role: str
    content: str
    status: str
    created_at: datetime
    updated_at: datetime
    evidence_status: str | None = None
    retrieval_rounds: int | None = None
    intent: str | None = None
    finish_reason: str | None = None
    error_class: str | None = None
    citations: list[CitationResponse] = []

    @staticmethod
    def from_message(message: Message) -> MessageResponse:
        """从领域消息构建响应"""
        return MessageResponse(
            id=message.id,
            role=message.role.value,
            content=message.content,
            status=message.status.value,
            created_at=message.created_at,
            updated_at=message.updated_at,
            evidence_status=(
                message.evidence_status.value if message.evidence_status is not None else None
            ),
            retrieval_rounds=message.retrieval_rounds,
            intent=message.intent,
            finish_reason=message.finish_reason,
            error_class=message.error_class,
            citations=[CitationResponse.from_record(record) for record in message.citations],
        )


class ConversationDetailResponse(BaseModel):
    """对话详情响应（包含历史消息列表）"""

    conversation: ConversationResponse
    messages: list[MessageResponse]

    @staticmethod
    def from_detail(detail: ConversationDetail) -> ConversationDetailResponse:
        """从领域对话详情构建响应"""
        return ConversationDetailResponse(
            conversation=ConversationResponse.from_conversation(detail.conversation),
            messages=[MessageResponse.from_message(message) for message in detail.messages],
        )


class RetrievalDebugRequest(BaseModel):
    """检索调试请求"""

    knowledge_base_id: UUID
    query: str = Field(min_length=1, max_length=_MAX_QUESTION_CHARS)


class RetrievalChannelHitResponse(BaseModel):
    """单检索渠道召回项响应"""

    child_id: UUID
    parent_id: UUID
    document_version_id: UUID
    rank: int
    raw_score: float | None


class RetrievalChannelResponse(BaseModel):
    """单检索渠道执行结果响应"""

    channel: str
    status: str
    latency_ms: int
    error_type: str | None
    hits: list[RetrievalChannelHitResponse]

    @staticmethod
    def from_result(result: ChannelResult) -> RetrievalChannelResponse:
        """从渠道检索结果构建响应"""
        return RetrievalChannelResponse(
            channel=result.channel.value,
            status=result.status.value,
            latency_ms=result.latency_ms,
            error_type=result.error_type,
            hits=[
                RetrievalChannelHitResponse(
                    child_id=hit.child_id,
                    parent_id=hit.parent_id,
                    document_version_id=hit.document_version_id,
                    rank=hit.rank,
                    raw_score=hit.raw_score,
                )
                for hit in result.hits
            ],
        )


class RetrievalCandidateResponse(BaseModel):
    """候选块排序响应（融合与重排得分）"""

    child_id: UUID
    parent_id: UUID
    document_version_id: UUID
    ordinal: int
    rrf_score: float
    rerank_score: float | None
    channel_ranks: dict[str, int]

    @staticmethod
    def from_candidate(candidate: Candidate) -> RetrievalCandidateResponse:
        """从检索候选块构建响应"""
        return RetrievalCandidateResponse(
            child_id=candidate.child_id,
            parent_id=candidate.parent_id,
            document_version_id=candidate.record.document_version_id,
            ordinal=candidate.ordinal,
            rrf_score=candidate.rrf_score,
            rerank_score=candidate.rerank_score,
            channel_ranks={
                channel.value: rank for channel, rank in candidate.channel_ranks.items()
            },
        )


class RetrievalRerankResponse(BaseModel):
    """重排执行状态响应"""

    status: str
    model: str | None
    scored: int
    reason: str | None


class RetrievalEvidenceResponse(BaseModel):
    """证据门控判定响应"""

    status: str
    reason: str
    accepted: list[UUID]

    @staticmethod
    def from_decision(decision: EvidenceDecision) -> RetrievalEvidenceResponse:
        """从证据判定结果构建响应"""
        return RetrievalEvidenceResponse(
            status=decision.status.value,
            reason=decision.reason,
            accepted=list(decision.accepted),
        )


class RetrievalContextSourceResponse(BaseModel):
    """上下文注入来源响应"""

    citation_id: str
    child_id: UUID
    parent_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_name: str
    heading_path: list[str]
    line_start: int
    line_end: int
    quote: str

    @staticmethod
    def from_source(source: CitationSource) -> RetrievalContextSourceResponse:
        """从引用源构建响应"""
        return RetrievalContextSourceResponse(
            citation_id=source.citation_id,
            child_id=source.child_id,
            parent_id=source.parent_id,
            document_id=source.document_id,
            document_version_id=source.document_version_id,
            document_name=source.document_name,
            heading_path=list(source.heading_path),
            line_start=source.line_start,
            line_end=source.line_end,
            quote=source.quote,
        )


class RetrievalDebugResponse(BaseModel):
    """完整检索调试响应（意图、多路召回、融合、重排、门控与上下文）"""

    query: str
    queries: list[str]
    intent: str
    channels: list[RetrievalChannelResponse]
    fused: list[RetrievalCandidateResponse]
    reranked: list[RetrievalCandidateResponse]
    rerank: RetrievalRerankResponse
    evidence: RetrievalEvidenceResponse
    context_sources: list[RetrievalContextSourceResponse]
    context_tokens: int

    @staticmethod
    def from_result(
        result: RetrievalResult,
        *,
        query: str,
        intent: str,
    ) -> RetrievalDebugResponse:
        """从检索综合结果构建调试响应"""
        diagnostics = result.diagnostics
        return RetrievalDebugResponse(
            query=query,
            queries=list(diagnostics.queries),
            intent=intent,
            channels=[
                RetrievalChannelResponse.from_result(channel) for channel in diagnostics.channels
            ],
            fused=[
                RetrievalCandidateResponse.from_candidate(candidate)
                for candidate in diagnostics.fused
            ],
            reranked=[
                RetrievalCandidateResponse.from_candidate(candidate)
                for candidate in diagnostics.reranked
            ],
            rerank=RetrievalRerankResponse(
                status=diagnostics.rerank.status.value,
                model=diagnostics.rerank.model,
                scored=diagnostics.rerank.scored,
                reason=diagnostics.rerank.reason,
            ),
            evidence=RetrievalEvidenceResponse.from_decision(result.evidence),
            context_sources=[
                RetrievalContextSourceResponse.from_source(source) for source in result.sources
            ],
            context_tokens=result.context_tokens,
        )


class CachedRetrievalDebug(BaseModel):
    """检索调试响应缓存信封，携带结构版本与语料版本校验标识。"""

    schema_version: int = CACHE_SCHEMA_VERSION
    corpus_revision: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    response: RetrievalDebugResponse
