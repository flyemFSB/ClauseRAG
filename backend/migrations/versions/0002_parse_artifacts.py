"""Parse artifacts: one row per document version, holding its normalized Markdown.

The table is the durable record of the parse stage: which parser and version produced the
Markdown, where the object is, its digest and size as measured from the stored object, and the
page attribution the parser could report. It is one row per version — the retry lane replaces the
row and rewrites the same object key (ADR-0016) — so ``document_version_id`` is unique.

Revision ID: 0002_parse_artifacts
Revises: 0001_phase1_schema
Create Date: 2026-10-02

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002_parse_artifacts"
down_revision: str | None = "0001_phase1_schema"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "parse_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("parser_name", sa.String(length=100), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=False),
        sa.Column("markdown_object_key", sa.Text(), nullable=False),
        sa.Column("checksum", sa.CHAR(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        # Page attribution and parser warnings are read whole and never joined on, so they are
        # JSON documents rather than child tables.
        sa.Column("page_spans", JSONB(), nullable=True),
        sa.Column("warnings", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_parse_artifacts_document_version_id_document_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id",
            name="uq_parse_artifacts_document_version_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("parse_artifacts")
