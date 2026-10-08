"""Parent and child chunks: the retrieval units, their context sections and the chunk artifact.

Three tables, because the two chunk levels and the artifact are three different things:

* ``parent_chunks`` — the structural section a child is expanded to, one row per section;
* ``child_chunks`` — the retrieval unit, one row per unit, always attached to its parent by a
  foreign key, so an orphan child cannot exist in the schema at all;
* ``chunk_artifacts`` — one row per document version, the object key, digest, size and counts of the
  JSONL the chunk stage wrote, replaced by a rebuild under a fixed key (ADR-0016's rule).

The identifiers are primary keys rather than surrogate ``id`` columns: ``parent_id`` and
``child_id`` are derived from ``(document_version_id, kind, ordinal)`` by UUID5 (ADR-0018), so they
*are* the business identity, and the unique ``(document_version_id, ordinal)`` constraints make the
derivation checkable instead of assumed.

This migration also enables ``pg_trgm`` and indexes child content with GIN trigrams. That index is
the foundation of the keyword channel of ADR-0008 — ``content LIKE '%query%'`` accelerated by GIN,
with ``similarity()`` used only to score — and ``postgres:18-alpine`` ships ``pg_trgm`` as a
trusted extension, so no superuser step is needed (measured in
``docs/research/probes/live-dependency-contracts.md`` §1a).

Revision ID: 0003_parent_child_chunks
Revises: 0002_parse_artifacts
Create Date: 2026-10-03

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003_parent_child_chunks"
down_revision: str | None = "0002_parse_artifacts"
branch_labels: str | None = None
depends_on: str | None = None

# The block types a child may be labelled with. Spelled out here rather than imported from the
# domain, because a migration records the schema as it was written: a later enum member is a later
# migration, not an edit of this one.
_BLOCK_TYPES = ("heading", "paragraph", "list", "table", "code", "image")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "parent_chunks",
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        # A JSON array of heading titles, read whole and never joined on.
        sa.Column("heading_path", JSONB(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_parent_chunks_document_version_id_document_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("parent_id"),
        sa.UniqueConstraint(
            "document_version_id",
            "ordinal",
            name="uq_parent_chunks_document_version_id_ordinal",
        ),
    )
    op.create_index(
        "ix_parent_chunks_document_version_id",
        "parent_chunks",
        ["document_version_id"],
    )

    op.create_table(
        "child_chunks",
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("heading_path", JSONB(), nullable=False),
        sa.Column("block_type", sa.String(length=32), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        # Line numbers address the normalized Markdown artifact.
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "block_type IN (" + ", ".join(f"'{value}'" for value in _BLOCK_TYPES) + ")",
            name="ck_child_chunks_block_type",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["parent_chunks.parent_id"],
            name="fk_child_chunks_parent_id_parent_chunks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_child_chunks_document_version_id_document_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("child_id"),
        sa.UniqueConstraint(
            "document_version_id",
            "ordinal",
            name="uq_child_chunks_document_version_id_ordinal",
        ),
    )
    op.create_index(
        "ix_child_chunks_document_version_id",
        "child_chunks",
        ["document_version_id"],
    )
    op.create_index("ix_child_chunks_parent_id", "child_chunks", ["parent_id"])
    # The keyword channel of ADR-0008: LIKE over the GIN trigram index, with similarity() for
    # scoring only. The operator class needs the extension, which is created above.
    op.create_index(
        "ix_child_chunks_content_trgm",
        "child_chunks",
        ["content"],
        postgresql_using="gin",
        postgresql_ops={"content": "gin_trgm_ops"},
    )

    op.create_table(
        "chunk_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("checksum", sa.CHAR(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("parent_count", sa.Integer(), nullable=False),
        sa.Column("child_count", sa.Integer(), nullable=False),
        sa.Column("warnings", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_chunk_artifacts_document_version_id_document_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id",
            name="uq_chunk_artifacts_document_version_id",
        ),
    )


def downgrade() -> None:
    # The tables carry the GIN index, so dropping them drops the index with them. ``pg_trgm`` stays
    # installed: it is a database-wide extension and another owner of this database — the graph
    # store, a later migration — may use it, while an upgrade re-creates it idempotently.
    op.drop_table("chunk_artifacts")
    op.drop_table("child_chunks")
    op.drop_table("parent_chunks")
