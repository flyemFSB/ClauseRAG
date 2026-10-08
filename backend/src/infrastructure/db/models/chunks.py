"""分块数据模型：包含父分块、子分块及分块产物表映射。"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.chunks.model import BlockType
from infrastructure.db.base import (
    CHECKSUM_LENGTH,
    ENUM_VALUE_LENGTH,
    Base,
    DomainUuid,
    check_constraint_values,
)


class ParentChunkRow(Base):
    """父分块表数据模型（承载段落上下文与结构层级）。"""

    __tablename__ = "parent_chunks"

    parent_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), primary_key=True)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "document_versions.id",
            ondelete="CASCADE",
            name="fk_parent_chunks_document_version_id_document_versions",
        ),
        nullable=False,
    )
    heading_path: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    ordinal: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    content: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    token_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "document_version_id",
            "ordinal",
            name="uq_parent_chunks_document_version_id_ordinal",
        ),
        sa.UniqueConstraint(
            "parent_id",
            "document_version_id",
            name="uq_parent_chunks_id_version",
        ),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_parent_chunks_ordinal_nonnegative",
        ),
        sa.CheckConstraint(
            "token_count >= 0",
            name="ck_parent_chunks_token_count_nonnegative",
        ),
    )


class ChildChunkRow(Base):
    """子分块表数据模型（承载检索定位与行号引用范围）。"""

    __tablename__ = "child_chunks"

    child_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), primary_key=True)
    parent_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "document_versions.id",
            ondelete="CASCADE",
            name="fk_child_chunks_document_version_id_document_versions",
        ),
        nullable=False,
    )
    heading_path: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    block_type: Mapped[str] = mapped_column(sa.String(ENUM_VALUE_LENGTH), nullable=False)
    ordinal: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    line_start: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    line_end: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    content: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    token_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False)

    __table_args__ = (
        sa.CheckConstraint(
            f"block_type IN ({check_constraint_values(BlockType)})",
            name="ck_child_chunks_block_type",
        ),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_child_chunks_ordinal_nonnegative",
        ),
        sa.CheckConstraint(
            "line_start >= 1 AND line_end >= line_start",
            name="ck_child_chunks_line_range",
        ),
        sa.CheckConstraint(
            "token_count >= 0",
            name="ck_child_chunks_token_count_nonnegative",
        ),
        sa.UniqueConstraint(
            "document_version_id",
            "ordinal",
            name="uq_child_chunks_document_version_id_ordinal",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "document_version_id"],
            ["parent_chunks.parent_id", "parent_chunks.document_version_id"],
            ondelete="CASCADE",
            name="fk_child_chunks_parent_same_version",
        ),
        sa.Index("ix_child_chunks_parent_id", "parent_id"),
        sa.Index(
            "ix_child_chunks_content_trgm",
            "content",
            postgresql_using="gin",
            postgresql_ops={"content": "gin_trgm_ops"},
        ),
    )


class ChunkArtifactRow(Base):
    """分块阶段产物表数据模型。"""

    __tablename__ = "chunk_artifacts"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "document_versions.id",
            ondelete="CASCADE",
            name="fk_chunk_artifacts_document_version_id_document_versions",
        ),
        primary_key=True,
    )
    object_key: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    checksum: Mapped[str] = mapped_column(sa.CHAR(CHECKSUM_LENGTH), nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    parent_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    child_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    warnings: Mapped[list[str] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        sa.CheckConstraint(
            "size_bytes >= 0 AND parent_count >= 0 AND child_count >= 0",
            name="ck_chunk_artifacts_size_nonnegative",
        ),
    )
