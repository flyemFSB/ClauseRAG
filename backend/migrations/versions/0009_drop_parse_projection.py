"""One source for the parse result: ``parse_artifacts``, not a projection on the version.

The single-source decision ADR-0026 records (its Migration 0009).
``document_versions`` carried ``markdown_object_key``, ``parser_name``, ``parser_version`` and
``page_count`` while ``parse_artifacts`` carried the same four facts: one transaction wrote both, so
they agreed — until a future writer updated one of them. The artifact row is now the only place a
parse result lives, and a reader that needs it joins the row that owns it.

Nothing on the wire changes: the version response never exposed these fields (the version detail
response reports them from ``ParseArtifactResponse``, which is built from the artifact), and the
chunk stage already read ``markdown_object_key``, ``checksum``, ``size_bytes`` and ``page_spans``
from the artifact row. The two internal readers that did use the version's copy — the deletion paths
that report the object keys they removed — read the artifact table instead, in the same
pre-delete statement set that already reads the chunk artifacts.

The downgrade backfills each column from ``parse_artifacts``, so a schema migrated down again holds
the same facts it did before the upgrade rather than four NULLs.

The revision identifier is deliberately short: ``alembic_version.version_num`` is ``varchar(32)``,
and the first name this migration had — ``0009_drop_version_parse_projection`` — was 34 characters,
so ``alembic upgrade head`` failed on the version-table write *after* running the migration (measured
against the real container).

Revision ID: 0009_drop_parse_projection
Revises: 0008_artifact_identity
Create Date: 2026-10-05

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009_drop_parse_projection"
down_revision: str | None = "0008_artifact_identity"
branch_labels: str | None = None
depends_on: str | None = None

# The projection, and the artifact columns to back the downgrade from. One pair per column so the
# two directions cannot list them in different orders.
_COLUMNS = (
    ("markdown_object_key", sa.Text()),
    ("parser_name", sa.String(length=100)),
    ("parser_version", sa.String(length=100)),
    ("page_count", sa.Integer()),
)


def upgrade() -> None:
    for column, _ in _COLUMNS:
        op.drop_column("document_versions", column)


def downgrade() -> None:
    for column, type_ in _COLUMNS:
        op.add_column("document_versions", sa.Column(column, type_, nullable=True))
    assignments = ", ".join(f"{column} = a.{column}" for column, _ in _COLUMNS)
    op.execute(
        "UPDATE document_versions v SET "
        f"{assignments} "
        "FROM parse_artifacts a WHERE a.document_version_id = v.id"
    )
