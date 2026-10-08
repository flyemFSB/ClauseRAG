"""Artifact identity: the document version *is* the artifact key.

The artifact-identity decision ADR-0026 records. ``parse_artifacts`` and
``chunk_artifacts`` both hold exactly one row per document version — a repeated attempt replaces the
row rather than appending one — and neither
the mappings nor the business DTOs ever read the surrogate ``id`` those two tables carried. The
primary key becomes ``document_version_id``, the random identifier and the unique constraint that
duplicated it are dropped, and the upserts that replace a row now conflict on the primary key.

The downgrade restores a distinct ``id`` per row rather than reusing the version identifier, so a
schema migrated down and up again is the schema it started from: ``gen_random_uuid()`` is built into
PostgreSQL 13 and later.

Revision ID: 0008_artifact_identity
Revises: 0007_schema_hardening
Create Date: 2026-10-05

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008_artifact_identity"
down_revision: str | None = "0007_schema_hardening"
branch_labels: str | None = None
depends_on: str | None = None

# Both tables, and the constraint names each one carries. The primary key keeps its original name
# through the change, so the downgrade restores exactly the constraints the upgrade replaced.
_TABLES = ("parse_artifacts", "chunk_artifacts")


def upgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"uq_{table}_document_version_id", table, type_="unique")
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.drop_column(table, "id")
        op.create_primary_key(f"{table}_pkey", table, ["document_version_id"])


def downgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("id", sa.Uuid(), nullable=True))
        # A distinct identifier per row, which is what the table held before: the version identifier
        # would make the restored column a second spelling of the primary key it replaced.
        op.execute(f"UPDATE {table} SET id = gen_random_uuid() WHERE id IS NULL")
        op.alter_column(table, "id", nullable=False)
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.create_primary_key(f"{table}_pkey", table, ["id"])
        op.create_unique_constraint(
            f"uq_{table}_document_version_id", table, ["document_version_id"]
        )
