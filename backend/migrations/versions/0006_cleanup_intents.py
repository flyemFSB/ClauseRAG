"""The durable cleanup intents: the derived cleanup a committed deletion still owes.

``docs/architecture/data-flow.md`` removes rows first and derived data second, and this table is how
the second half survives a provider outage: the deletion writes the intent in the same transaction
that removes the rows, the worker claims the intent with the same conditional write the ingestion
jobs use, and the intent stays ``pending`` until every store it names is clean. The record keeps no
foreign key to the rows it describes — they are gone, and the intent is what outlives them.

The check constraints spell the kind and status values out rather than importing them from the
domain: a migration records the schema as it was written.

Revision ID: 0006_cleanup_intents
Revises: 0005_graph_build_runs
Create Date: 2026-10-03

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006_cleanup_intents"
down_revision: str | None = "0005_graph_build_runs"
branch_labels: str | None = None
depends_on: str | None = None

_KINDS = ("document", "knowledge_base")
_STATUSES = ("pending", "running", "succeeded", "failed")

_ENUM_VALUE_LENGTH = 32
_SHORT_TEXT_LENGTH = 100


def upgrade() -> None:
    op.create_table(
        "cleanup_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=_ENUM_VALUE_LENGTH), nullable=False),
        sa.Column("status", sa.String(length=_ENUM_VALUE_LENGTH), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("object_keys", JSONB, nullable=False),
        sa.Column("document_version_ids", JSONB, nullable=False),
        sa.Column("child_ids", JSONB, nullable=False),
        sa.Column("error_class", sa.String(length=_SHORT_TEXT_LENGTH), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{value}'" for value in _KINDS) + ")",
            name="ck_cleanup_intents_kind",
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{value}'" for value in _STATUSES) + ")",
            name="ck_cleanup_intents_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cleanup_intents_status_updated_at",
        "cleanup_intents",
        ["status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cleanup_intents_status_updated_at", table_name="cleanup_intents")
    op.drop_table("cleanup_intents")
