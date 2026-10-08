"""Phase 1 schema: users, sessions, knowledge bases, documents, versions and ingestion jobs.

The complete Phase 1 schema is created here in one revision so that later phases add behavior
without rewriting this migration. LangGraph checkpoint tables are not
owned by this Alembic history.

Revision ID: 0001_phase1_schema
Revises:
Create Date: 2026-10-02

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase1_schema"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

# Value lists are frozen here: a migration records the schema as it was, and later enum changes
# arrive as new revisions instead of edits to this one.
DOCUMENT_VERSION_STATUS_VALUES = (
    "uploaded",
    "parsing",
    "parsed",
    "chunking",
    "embedding",
    "indexing",
    "ready",
    "parse_failed",
    "chunk_failed",
    "embedding_failed",
    "index_failed",
    "manual_retry_required",
)
INGESTION_STAGE_VALUES = ("parse", "normalize", "chunk", "embed", "index", "graph_build")
INGESTION_JOB_STATUS_VALUES = (
    "pending",
    "running",
    "succeeded",
    "failed",
    "manual_retry_required",
)

_TABLES_IN_DROP_ORDER = (
    "ingestion_jobs",
    "document_versions",
    "documents",
    "knowledge_bases",
    "sessions",
    "users",
)


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # PostgreSQL functional unique index: one account per email, case-insensitively.
    op.execute("CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))")

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_knowledge_bases_owner_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_knowledge_bases_owner_id_name"),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name="fk_documents_knowledge_base_id_knowledge_bases",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_knowledge_base_id", "documents", ["knowledge_base_id"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("checksum", sa.CHAR(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_object_key", sa.Text(), nullable=False),
        sa.Column("markdown_object_key", sa.Text(), nullable=True),
        sa.Column("parser_name", sa.String(length=100), nullable=True),
        sa.Column("parser_version", sa.String(length=100), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_in_list(DOCUMENT_VERSION_STATUS_VALUES)})",
            name="ck_document_versions_status",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_versions_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "version_ordinal",
            name="uq_document_versions_document_id_version_ordinal",
        ),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_class", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"stage IN ({_in_list(INGESTION_STAGE_VALUES)})",
            name="ck_ingestion_jobs_stage",
        ),
        sa.CheckConstraint(
            f"status IN ({_in_list(INGESTION_JOB_STATUS_VALUES)})",
            name="ck_ingestion_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_ingestion_jobs_document_version_id_document_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id",
            "stage",
            "revision",
            name="uq_ingestion_jobs_document_version_id_stage_revision",
        ),
    )


def downgrade() -> None:
    for table in _TABLES_IN_DROP_ORDER:
        op.drop_table(table, if_exists=True)
