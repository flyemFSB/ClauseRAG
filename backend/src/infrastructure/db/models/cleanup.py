"""持久化清理意向表数据模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.cleanup import CleanupKind, CleanupStatus
from infrastructure.db.base import (
    ENUM_VALUE_LENGTH,
    SHORT_TEXT_LENGTH,
    Base,
    DomainUuid,
    check_constraint_values,
)


class CleanupIntentRow(Base):
    """异步级联清理意向记录表数据模型。"""

    __tablename__ = "cleanup_intents"

    id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), primary_key=True)
    kind: Mapped[str] = mapped_column(sa.String(ENUM_VALUE_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(ENUM_VALUE_LENGTH), nullable=False)
    attempt: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default=sa.text("0"))
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(DomainUuid())
    object_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    document_version_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    child_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    error_class: Mapped[str | None] = mapped_column(sa.String(SHORT_TEXT_LENGTH))
    error_message: Mapped[str | None] = mapped_column(sa.Text())
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        sa.CheckConstraint(
            f"kind IN ({check_constraint_values(CleanupKind)})", name="ck_cleanup_intents_kind"
        ),
        sa.CheckConstraint(
            f"status IN ({check_constraint_values(CleanupStatus)})",
            name="ck_cleanup_intents_status",
        ),
        sa.CheckConstraint(
            "attempt >= 0",
            name="ck_cleanup_intents_attempt_nonnegative",
        ),
        sa.Index(
            "ix_cleanup_intents_pending_updated_id",
            "updated_at",
            "id",
            postgresql_where=sa.text("status = 'pending'"),
        ),
        sa.Index(
            "ix_cleanup_intents_running_updated_id",
            "updated_at",
            "id",
            postgresql_where=sa.text("status = 'running'"),
        ),
    )
