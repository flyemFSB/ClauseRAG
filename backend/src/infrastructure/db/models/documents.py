"""文档目录与版本管理数据模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from domain.knowledge import DocumentVersionStatus
from infrastructure.db.base import (
    CHECKSUM_LENGTH,
    ENUM_VALUE_LENGTH,
    MIME_TYPE_LENGTH,
    TITLE_LENGTH,
    Base,
    DomainUuid,
    check_constraint_values,
)


class DocumentRow(Base):
    """逻辑文档元数据表模型。"""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), primary_key=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "knowledge_bases.id",
            ondelete="CASCADE",
            name="fk_documents_knowledge_base_id_knowledge_bases",
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(sa.String(TITLE_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    __table_args__ = (sa.Index("ix_documents_knowledge_base_id", "knowledge_base_id"),)


class DocumentVersionRow(Base):
    """文档版本元数据表模型。"""

    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "documents.id",
            ondelete="CASCADE",
            name="fk_document_versions_document_id_documents",
        ),
        nullable=False,
    )
    version_ordinal: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(ENUM_VALUE_LENGTH), nullable=False)
    mime_type: Mapped[str] = mapped_column(sa.String(MIME_TYPE_LENGTH), nullable=False)
    checksum: Mapped[str] = mapped_column(sa.CHAR(CHECKSUM_LENGTH), nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    source_object_key: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        sa.CheckConstraint(
            f"status IN ({check_constraint_values(DocumentVersionStatus)})",
            name="ck_document_versions_status",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_document_versions_size_nonnegative",
        ),
        sa.UniqueConstraint(
            "document_id",
            "version_ordinal",
            name="uq_document_versions_document_id_version_ordinal",
        ),
    )
