"""The graph build stage's table is gone, but its revision id has to stay resolvable.

``0011_drop_graph_channel`` removes the table and the stage value, and its own comment records that
a fresh database never creates ``graph_build_runs``. Deleting this file as well would leave every
database that was migrated up to this revision stamped at an id the current history cannot resolve,
and such a database could not upgrade. So this revision keeps its id and becomes a no-op: a database
that already ran the original revision keeps the table it has (``0011`` drops it), and a database
that never ran it never grows one. ``0006`` revises this revision so the chain stays linear.

Revision ID: 0005_graph_build_runs
Revises: 0004_conversations
Create Date: 2026-10-03

"""

from __future__ import annotations

revision: str = "0005_graph_build_runs"
down_revision: str | None = "0004_conversations"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """The original revision's DDL is not replayed."""


def downgrade() -> None:
    """The original revision's DDL is not replayed."""
