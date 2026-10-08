"""摄取流水线状态数据模型：作业与解析产物。"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.knowledge import IngestionJobStatus, IngestionStage
from infrastructure.db.base import (
    CHECKSUM_LENGTH,
    ENUM_VALUE_LENGTH,
    SHORT_TEXT_LENGTH,
    Base,
    DomainUuid,
    check_constraint_values,
)


class IngestionJobRow(Base):
    """摄取阶段作业表数据模型。"""

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), primary_key=True)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "document_versions.id",
            ondelete="CASCADE",
            name="fk_ingestion_jobs_document_version_id_document_versions",
        ),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(sa.String(ENUM_VALUE_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(ENUM_VALUE_LENGTH), nullable=False)
    revision: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    attempt: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default=sa.text("0"))
    error_class: Mapped[str | None] = mapped_column(sa.String(SHORT_TEXT_LENGTH))
    error_message: Mapped[str | None] = mapped_column(sa.Text())
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    not_before: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        sa.CheckConstraint(
            f"stage IN ({check_constraint_values(IngestionStage)})",
            name="ck_ingestion_jobs_stage",
        ),
        sa.CheckConstraint(
            f"status IN ({check_constraint_values(IngestionJobStatus)})",
            name="ck_ingestion_jobs_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_ingestion_jobs_revision_positive"),
        sa.CheckConstraint("attempt >= 0", name="ck_ingestion_jobs_attempt_nonnegative"),
        sa.UniqueConstraint(
            "document_version_id",
            "stage",
            "revision",
            name="uq_ingestion_jobs_document_version_id_stage_revision",
        ),
        sa.Index(
            "ix_ingestion_jobs_pending_not_before",
            "not_before",
            "updated_at",
            "id",
            postgresql_where=sa.text("status = 'pending'"),
        ),
        sa.Index(
            "ix_ingestion_jobs_running_lease_expires_at",
            "lease_expires_at",
            "id",
            postgresql_where=sa.text("status = 'running'"),
        ),
    )


class ParseArtifactRow(Base):
    """解析阶段产物表数据模型。"""

    __tablename__ = "parse_artifacts"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "document_versions.id",
            ondelete="CASCADE",
            name="fk_parse_artifacts_document_version_id_document_versions",
        ),
        primary_key=True,
    )
    parser_name: Mapped[str] = mapped_column(sa.String(SHORT_TEXT_LENGTH), nullable=False)
    parser_version: Mapped[str] = mapped_column(sa.String(SHORT_TEXT_LENGTH), nullable=False)
    markdown_object_key: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    checksum: Mapped[str] = mapped_column(sa.CHAR(CHECKSUM_LENGTH), nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    page_count: Mapped[int | None] = mapped_column(sa.Integer())
    warnings: Mapped[list[str] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_parse_artifacts_size_nonnegative",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_parse_artifacts_page_count_nonnegative",
        ),
    )
