"""会话与问答历史数据行到领域实体的转换映射。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.conversation import CitationRecord, Conversation, Message, MessageRole, MessageStatus
from domain.retrieval import EvidenceStatus

if TYPE_CHECKING:
    from collections.abc import Sequence

    from infrastructure.db.models.conversations import CitationRow, ConversationRow, MessageRow


def to_conversation(row: ConversationRow) -> Conversation:
    """将会话数据库行转换为领域实体。"""
    return Conversation(
        id=row.id,
        owner_id=row.owner_id,
        knowledge_base_id=row.knowledge_base_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def to_citation(row: CitationRow) -> CitationRecord:
    """将引文数据库行转换为领域引文记录实体。"""
    return CitationRecord(
        citation_id=row.citation_id,
        child_id=row.child_id,
        parent_id=row.parent_id,
        document_id=row.document_id,
        document_version_id=row.document_version_id,
        document_name=row.document_name,
        heading_path=tuple(row.heading_path),
        line_start=row.line_start,
        line_end=row.line_end,
        quote=row.quote,
    )


def to_message(row: MessageRow, citations: Sequence[CitationRow] = ()) -> Message:
    """将消息数据库行及关联引文转换为领域消息实体。"""
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        role=MessageRole(row.role),
        content=row.content,
        status=MessageStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        evidence_status=EvidenceStatus(row.evidence_status) if row.evidence_status else None,
        retrieval_rounds=row.retrieval_rounds,
        intent=row.intent,
        finish_reason=row.finish_reason,
        error_class=row.error_class,
        citations=tuple(to_citation(citation) for citation in citations),
    )
