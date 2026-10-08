"""Schema hardening: the invariants the database did not yet express, and the indexes queries use.

The first step of the schema hardening that ADR-0026 records. Four groups of change, none of
which adds or removes a table:

**Composite foreign keys (P0).** A child chunk could name a parent of another version, and a
conversation could name a knowledge base another user owns: the application never writes either, but
nothing in the schema refused it. Both are now refused by the database. The single-column foreign
keys they replace are dropped, so one relationship is not constrained twice; the column set is
``(knowledge_base_id, owner_id)`` rather than only ``knowledge_base_id``, which is why the parent
and knowledge-base tables gain the unique key the composite foreign key needs as a target.

**Value-domain checks (P1).** Non-negative sizes, ordinals, token counts, attempt counters, a
positive revision, and a line range whose end is not before its start. These are already invariants
of the application; the migration only makes them invariants of the schema. They are added as
validating constraints rather than ``NOT VALID`` + ``VALIDATE``: that pair exists to keep a large
production table writable while an existing backlog is cleaned, and this deployment is
pre-production, where a row that violates one of these is a bug to fix rather than data to keep
serving.

**Indexes that match the queries (P1).** The owner/order lists, the cleanup claim's two states, and
the message history. Each one is created here as a plain ``CREATE INDEX`` because that is what a
pre-production deployment needs; a large production table needs ``CREATE INDEX CONCURRENTLY``, which
cannot run inside Alembic's transaction and therefore needs an autocommit block (``alembic``'s
``op.get_context().autocommit_block()``) with ``postgresql_concurrently=True`` on the same call.

**Indexes that no query uses (P1).** Three single-column indexes are removed because a composite
unique constraint already serves their left prefix — PostgreSQL scans a B-tree backwards, so the
descending reads they were once added for need no index of their own. ``citations(message_id)`` is
the third: ``unique(message_id, citation_id)`` answers a message's citations.

The email column is canonicalized the same way (P1): a repository-wide ``lower(email)`` expression
index is replaced by the plain unique index the query can use, with a check constraint that keeps
the stored form canonical. ``normalize_email`` already lowercases and strips before every write, so
existing rows satisfy it; a row that did not would fail this migration loudly rather than disappear.

Revision ID: 0007_schema_hardening
Revises: 0006_cleanup_intents
Create Date: 2026-10-05

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007_schema_hardening"
down_revision: str | None = "0006_cleanup_intents"
branch_labels: str | None = None
depends_on: str | None = None

# The two partial indexes of the cleanup claim, whose predicate is the state they serve. Spelled out
# rather than imported from the domain: a migration records the schema as it was written.
_PENDING = "status = 'pending'"
_RUNNING = "status = 'running'"


def upgrade() -> None:
    # --- the email's canonical form is enforced, and the plain unique index is what lookups use ---
    op.drop_index("uq_users_email_lower", table_name="users")
    op.create_check_constraint(
        "ck_users_email_canonical",
        "users",
        "email = lower(email) AND email = btrim(email)",
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    # --- a conversation's owner must be its knowledge base's owner ---
    op.create_unique_constraint(
        "uq_knowledge_bases_id_owner",
        "knowledge_bases",
        ["id", "owner_id"],
    )
    op.create_foreign_key(
        "fk_conversations_owner_matches_kb",
        "conversations",
        "knowledge_bases",
        ["knowledge_base_id", "owner_id"],
        ["id", "owner_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_conversations_knowledge_base_id_knowledge_bases",
        "conversations",
        type_="foreignkey",
    )

    # --- a child chunk's parent must be a parent of the child's own version ---
    op.create_unique_constraint(
        "uq_parent_chunks_id_version",
        "parent_chunks",
        ["parent_id", "document_version_id"],
    )
    op.create_foreign_key(
        "fk_child_chunks_parent_same_version",
        "child_chunks",
        "parent_chunks",
        ["parent_id", "document_version_id"],
        ["parent_id", "document_version_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_child_chunks_parent_id_parent_chunks",
        "child_chunks",
        type_="foreignkey",
    )

    # --- the value domains the application already maintains ---
    op.create_check_constraint(
        "ck_document_versions_size_nonnegative",
        "document_versions",
        "size_bytes >= 0",
    )
    op.create_check_constraint(
        "ck_ingestion_jobs_revision_positive",
        "ingestion_jobs",
        "revision >= 1",
    )
    op.create_check_constraint(
        "ck_ingestion_jobs_attempt_nonnegative",
        "ingestion_jobs",
        "attempt >= 0",
    )
    op.create_check_constraint(
        "ck_parse_artifacts_size_nonnegative",
        "parse_artifacts",
        "size_bytes >= 0",
    )
    op.create_check_constraint(
        "ck_parse_artifacts_page_count_nonnegative",
        "parse_artifacts",
        "page_count IS NULL OR page_count >= 0",
    )
    op.create_check_constraint(
        "ck_parent_chunks_ordinal_nonnegative",
        "parent_chunks",
        "ordinal >= 0",
    )
    op.create_check_constraint(
        "ck_parent_chunks_token_count_nonnegative",
        "parent_chunks",
        "token_count >= 0",
    )
    op.create_check_constraint(
        "ck_child_chunks_ordinal_nonnegative",
        "child_chunks",
        "ordinal >= 0",
    )
    op.create_check_constraint(
        "ck_child_chunks_line_range",
        "child_chunks",
        "line_start >= 1 AND line_end >= line_start",
    )
    op.create_check_constraint(
        "ck_child_chunks_token_count_nonnegative",
        "child_chunks",
        "token_count >= 0",
    )
    op.create_check_constraint(
        "ck_chunk_artifacts_size_nonnegative",
        "chunk_artifacts",
        "size_bytes >= 0 AND parent_count >= 0 AND child_count >= 0",
    )
    op.create_check_constraint(
        "ck_messages_retrieval_rounds_nonnegative",
        "messages",
        "retrieval_rounds IS NULL OR retrieval_rounds >= 0",
    )
    op.create_check_constraint(
        "ck_cleanup_intents_attempt_nonnegative",
        "cleanup_intents",
        "attempt >= 0",
    )

    # --- the indexes the list and claim queries order by ---
    op.create_index(
        "ix_knowledge_bases_owner_created_id",
        "knowledge_bases",
        ["owner_id", sa.text("created_at DESC"), "id"],
    )
    op.drop_index("ix_conversations_owner_id", table_name="conversations")
    op.create_index(
        "ix_conversations_owner_updated_id",
        "conversations",
        ["owner_id", sa.text("updated_at DESC"), "id"],
    )
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.create_index(
        "ix_messages_conversation_created_id",
        "messages",
        ["conversation_id", "created_at", "id"],
    )
    op.drop_index("ix_cleanup_intents_status_updated_at", table_name="cleanup_intents")
    op.create_index(
        "ix_cleanup_intents_pending_updated_id",
        "cleanup_intents",
        ["updated_at", "id"],
        postgresql_where=sa.text(_PENDING),
    )
    op.create_index(
        "ix_cleanup_intents_running_updated_id",
        "cleanup_intents",
        ["updated_at", "id"],
        postgresql_where=sa.text(_RUNNING),
    )

    # --- indexes a composite unique constraint already serves ---
    op.drop_index("ix_parent_chunks_document_version_id", table_name="parent_chunks")
    op.drop_index("ix_child_chunks_document_version_id", table_name="child_chunks")
    op.drop_index("ix_citations_message_id", table_name="citations")


def downgrade() -> None:
    op.create_index("ix_citations_message_id", "citations", ["message_id"])
    op.create_index(
        "ix_child_chunks_document_version_id",
        "child_chunks",
        ["document_version_id"],
    )
    op.create_index(
        "ix_parent_chunks_document_version_id",
        "parent_chunks",
        ["document_version_id"],
    )

    op.drop_index("ix_cleanup_intents_running_updated_id", table_name="cleanup_intents")
    op.drop_index("ix_cleanup_intents_pending_updated_id", table_name="cleanup_intents")
    op.create_index(
        "ix_cleanup_intents_status_updated_at",
        "cleanup_intents",
        ["status", "updated_at"],
    )
    op.drop_index("ix_messages_conversation_created_id", table_name="messages")
    op.create_index(
        "ix_messages_conversation_id",
        "messages",
        ["conversation_id", "created_at"],
    )
    op.drop_index("ix_conversations_owner_updated_id", table_name="conversations")
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])
    op.drop_index("ix_knowledge_bases_owner_created_id", table_name="knowledge_bases")

    op.drop_constraint("ck_cleanup_intents_attempt_nonnegative", "cleanup_intents", type_="check")
    op.drop_constraint("ck_messages_retrieval_rounds_nonnegative", "messages", type_="check")
    op.drop_constraint("ck_chunk_artifacts_size_nonnegative", "chunk_artifacts", type_="check")
    op.drop_constraint("ck_child_chunks_token_count_nonnegative", "child_chunks", type_="check")
    op.drop_constraint("ck_child_chunks_line_range", "child_chunks", type_="check")
    op.drop_constraint("ck_child_chunks_ordinal_nonnegative", "child_chunks", type_="check")
    op.drop_constraint("ck_parent_chunks_token_count_nonnegative", "parent_chunks", type_="check")
    op.drop_constraint("ck_parent_chunks_ordinal_nonnegative", "parent_chunks", type_="check")
    op.drop_constraint(
        "ck_parse_artifacts_page_count_nonnegative", "parse_artifacts", type_="check"
    )
    op.drop_constraint("ck_parse_artifacts_size_nonnegative", "parse_artifacts", type_="check")
    op.drop_constraint("ck_ingestion_jobs_attempt_nonnegative", "ingestion_jobs", type_="check")
    op.drop_constraint("ck_ingestion_jobs_revision_positive", "ingestion_jobs", type_="check")
    op.drop_constraint("ck_document_versions_size_nonnegative", "document_versions", type_="check")

    op.create_foreign_key(
        "fk_child_chunks_parent_id_parent_chunks",
        "child_chunks",
        "parent_chunks",
        ["parent_id"],
        ["parent_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_child_chunks_parent_same_version",
        "child_chunks",
        type_="foreignkey",
    )
    op.drop_constraint("uq_parent_chunks_id_version", "parent_chunks", type_="unique")

    op.create_foreign_key(
        "fk_conversations_knowledge_base_id_knowledge_bases",
        "conversations",
        "knowledge_bases",
        ["knowledge_base_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_conversations_owner_matches_kb",
        "conversations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_knowledge_bases_id_owner",
        "knowledge_bases",
        type_="unique",
    )

    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_constraint("ck_users_email_canonical", "users", type_="check")
    op.execute("CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))")
