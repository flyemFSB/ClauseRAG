"""分块数据模型：包含父分块、子分块、子块向量及分块产物表映射。"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
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

# 向量维度与模型部署契约，需与数据表约束一致。
EMBEDDING_DIMENSION = 1024
EMBEDDING_MODEL = "BAAI/bge-m3"

# 统一维护数据表名与检索索引名常量。
CHILD_CHUNKS_TABLE = "child_chunks"
EMBEDDINGS_TABLE = "child_chunk_embeddings"
CHILD_CHUNKS_BM25_INDEX = "ix_child_chunks_lexical"
EMBEDDINGS_HNSW_INDEX = "ix_child_chunk_embeddings_hnsw_cosine"


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

    __tablename__ = CHILD_CHUNKS_TABLE

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
        # ParadeDB BM25 关键词检索索引。
        sa.Index(
            CHILD_CHUNKS_BM25_INDEX,
            "child_id",
            "content",
            "document_version_id",
            postgresql_using="paradedb",
        ),
    )


class ChildChunkEmbeddingRow(Base):
    """子块向量表数据模型（pgvector 原生 vector 列与 HNSW cosine 索引）。"""

    __tablename__ = EMBEDDINGS_TABLE

    child_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "child_chunks.child_id",
            ondelete="CASCADE",
            name="fk_child_chunk_embeddings_child_id_child_chunks",
        ),
        primary_key=True,
    )
    # 关联知识库用于检索范围过滤。
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        DomainUuid(),
        sa.ForeignKey(
            "knowledge_bases.id",
            ondelete="CASCADE",
            name="fk_child_chunk_embeddings_knowledge_base_id_knowledge_bases",
        ),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIMENSION), nullable=False)

    __table_args__ = (
        # 约束单部署模型名称一致性。
        sa.CheckConstraint(
            f"embedding_model = {EMBEDDING_MODEL!r}",
            name="ck_child_chunk_embeddings_embedding_model",
        ),
        # 过滤全零与非法向量。
        sa.CheckConstraint(
            "vector_norm(embedding) > 0",
            name="ck_child_chunk_embeddings_embedding_nonzero",
        ),
        sa.Index(
            "ix_child_chunk_embeddings_knowledge_base",
            "knowledge_base_id",
        ),
        sa.Index(
            EMBEDDINGS_HNSW_INDEX,
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
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
