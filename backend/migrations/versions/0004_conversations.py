"""Conversations, messages and citations: the chat surface's business records.

Three tables, because the chat has three things to keep:

* ``conversations`` — one chat, bound to the knowledge base that scopes its retrieval. The knowledge
  base cascades, so a conversation cannot outlive the scope it retrieves in; the owner does not
  cascade, exactly like a knowledge base.
* ``messages`` — one turn, with the outcome of the run that produced it. ``status`` starts
  ``streaming`` for an assistant message and is replaced by exactly one terminal status, so a row
  left ``streaming`` names a run whose process died mid-answer. The run's own facts (the evidence
  status the gate decided, the number of retrieval rounds, the route, the provider's
  ``finish_reason`` and the failure class) are columns here rather than part of a checkpoint: the
  LangGraph checkpoint holds the *run's* state and is never read as the conversation's history
  (``docs/architecture/data-flow.md``).
* ``citations`` — one validated citation per label, stored resolved: the quote and the location were
  read from the stored chunk when the run validated the model's marker, which is what makes a
  citation click-through survive a reload.

The check constraints spell the enum values out rather than importing them from the domain: a
migration records the schema as it was written, so a later enum member is a later migration and not
an edit of this one.

Revision ID: 0004_conversations
Revises: 0003_parent_child_chunks
Create Date: 2026-10-03

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004_conversations"
down_revision: str | None = "0003_parent_child_chunks"
branch_labels: str | None = None
depends_on: str | None = None

_ROLES = ("user", "assistant")
_MESSAGE_STATUSES = ("streaming", "completed", "failed", "cancelled")
_EVIDENCE_STATUSES = ("sufficient", "degraded", "insufficient")

_ENUM_VALUE_LENGTH = 32
_SHORT_TEXT_LENGTH = 100
_TITLE_LENGTH = 500


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=_TITLE_LENGTH), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_conversations_owner_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name="fk_conversations_knowledge_base_id_knowledge_bases",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=_ENUM_VALUE_LENGTH), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=_ENUM_VALUE_LENGTH), nullable=False),
        sa.Column("evidence_status", sa.String(length=_ENUM_VALUE_LENGTH), nullable=True),
        sa.Column("retrieval_rounds", sa.Integer(), nullable=True),
        sa.Column("intent", sa.String(length=_ENUM_VALUE_LENGTH), nullable=True),
        sa.Column("finish_reason", sa.String(length=_ENUM_VALUE_LENGTH), nullable=True),
        sa.Column("error_class", sa.String(length=_SHORT_TEXT_LENGTH), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN (" + ", ".join(f"'{value}'" for value in _ROLES) + ")",
            name="ck_messages_role",
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{value}'" for value in _MESSAGE_STATUSES) + ")",
            name="ck_messages_status",
        ),
        sa.CheckConstraint(
            "evidence_status IS NULL OR evidence_status IN ("
            + ", ".join(f"'{value}'" for value in _EVIDENCE_STATUSES)
            + ")",
            name="ck_messages_evidence_status",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_messages_conversation_id",
        "messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("citation_id", sa.String(length=_ENUM_VALUE_LENGTH), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("document_name", sa.String(length=_TITLE_LENGTH), nullable=False),
        sa.Column("heading_path", JSONB(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name="fk_citations_message_id_messages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "citation_id",
            name="uq_citations_message_id_citation_id",
        ),
    )
    op.create_index("ix_citations_message_id", "citations", ["message_id"])


def downgrade() -> None:
    op.drop_table("citations")
    op.drop_table("messages")
    op.drop_table("conversations")
