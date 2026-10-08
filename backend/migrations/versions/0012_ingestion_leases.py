"""Ingestion jobs get a lease, a delivery clock and a publish stamp.

A job row is the record of the work the platform owes, so delivery has to be driven by that row
rather than by the message that happened to carry it: ``not_before`` is the earliest time a retry
may be delivered, ``lease_expires_at`` is how long a claim owns the job before another attempt may
take it over, and ``dispatched_at`` is the last publish so the dispatcher does not repeat one on
every tick. The two indexes are the predicates the dispatcher and the reaper read, and they are
spelled out here rather than imported: a migration records the schema as it was written.

Revision ID: 0012_ingestion_leases
Revises: 0011_drop_graph_channel
Create Date: 2026-10-07

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0012_ingestion_leases"
down_revision: str | None = "0011_drop_graph_channel"
branch_labels: str | None = None
depends_on: str | None = None

_PENDING = "status = 'pending'"
_RUNNING = "status = 'running'"


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_ingestion_jobs_pending_not_before",
        "ingestion_jobs",
        ["not_before", "updated_at", "id"],
        postgresql_where=sa.text(_PENDING),
    )
    op.create_index(
        "ix_ingestion_jobs_running_lease_expires_at",
        "ingestion_jobs",
        ["lease_expires_at", "id"],
        postgresql_where=sa.text(_RUNNING),
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_running_lease_expires_at", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_pending_not_before", table_name="ingestion_jobs")
    op.drop_column("ingestion_jobs", "dispatched_at")
    op.drop_column("ingestion_jobs", "lease_expires_at")
    op.drop_column("ingestion_jobs", "not_before")
