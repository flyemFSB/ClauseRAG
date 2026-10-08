"""会话与问答历史数据模型：包含会话、消息及引用信息。"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.conversation import MessageRole, MessageStatus
from domain.retrieval import EvidenceStatus
from infrastructure.db.base import (
    ENUM_VALUE_LENGTH,
    SHORT_TEXT_LENGTH,
    TITLE_LENGTH,
    Base,
    DomainUuid,
    check_constraint_values,
)


class ConversationRow(Base):
    """会话表数据模型。"""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), primary_key=True)
    # No foreign key: there is no account table to point at (ADR-0033). The column stays because
    # it is half of ``fk_conversations_owner_matches_kb`` below, which is what keeps a conversation
    # in its own knowledge base.
    owner_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), nullable=False)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(TITLE_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["knowledge_base_id", "owner_id"],
            ["knowledge_bases.id", "knowledge_bases.owner_id"],
            ondelete="CASCADE",
            name="fk_conversations_owner_matches_kb",
        ),
        sa.Index(
            "ix_conversations_owner_updated_id",
            "owner_id",
            sa.text("updated_at DESC"),
            "id",
        ),
    )


class MessageRow(Base):
    """对话消息表数据模型。"""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
            name="fk_messages_conversation_id_conversations",
        ),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(sa.String(ENUM_VALUE_LENGTH), nullable=False)
    content: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(ENUM_VALUE_LENGTH), nullable=False)
    evidence_status: Mapped[str | None] = mapped_column(sa.String(ENUM_VALUE_LENGTH))
    retrieval_rounds: Mapped[int | None] = mapped_column(sa.Integer())
    intent: Mapped[str | None] = mapped_column(sa.String(ENUM_VALUE_LENGTH))
    finish_reason: Mapped[str | None] = mapped_column(sa.String(ENUM_VALUE_LENGTH))
    error_class: Mapped[str | None] = mapped_column(sa.String(SHORT_TEXT_LENGTH))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        sa.CheckConstraint(
            f"role IN ({check_constraint_values(MessageRole)})",
            name="ck_messages_role",
        ),
        sa.CheckConstraint(
            f"status IN ({check_constraint_values(MessageStatus)})",
            name="ck_messages_status",
        ),
        sa.CheckConstraint(
            "evidence_status IS NULL OR evidence_status IN ("
            f"{check_constraint_values(EvidenceStatus)})",
            name="ck_messages_evidence_status",
        ),
        sa.CheckConstraint(
            "retrieval_rounds IS NULL OR retrieval_rounds >= 0",
            name="ck_messages_retrieval_rounds_nonnegative",
        ),
        sa.Index("ix_messages_conversation_created_id", "conversation_id", "created_at", "id"),
    )


class CitationRow(Base):
    """引文信息表数据模型。"""

    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "messages.id",
            ondelete="CASCADE",
            name="fk_citations_message_id_messages",
        ),
        nullable=False,
    )
    citation_id: Mapped[str] = mapped_column(sa.String(ENUM_VALUE_LENGTH), nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), nullable=False)
    parent_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), nullable=False)
    document_name: Mapped[str] = mapped_column(sa.String(TITLE_LENGTH), nullable=False)
    heading_path: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    line_start: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    line_end: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    quote: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "message_id", "citation_id", name="uq_citations_message_id_citation_id"
        ),
    )
