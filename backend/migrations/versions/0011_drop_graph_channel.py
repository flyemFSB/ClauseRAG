"""The knowledge graph channel is removed: its table and its stage value go with it.

The retrieval lane is dense + keyword + RRF; there is no third channel, no ``graph_build`` stage and
no ``graph_build_runs`` table. ``0005_graph_build_runs`` is a no-op revision that keeps its id
resolvable, so a database stamped at it can still upgrade, while a database that never ran it never
grows the table; what remains here is the cleanup a database that already ran it needs: drop the
table and narrow the stage check constraint that ``0001_phase1_schema`` wrote with ``graph_build``
in its value list. ``0001`` stays frozen (its own comment says later value changes arrive as new
revisions rather than edits to it).

``stage`` is a string column with a check constraint rather than a PostgreSQL enum type, so
narrowing the domain is a constraint swap. Any ``graph_build`` job row must go before the narrower
constraint can be added, and it is a finished or abandoned stage either way: the jobs table is a
ledger of stage attempts, not a fact any retrieval path reads.

Revision ID: 0011_drop_graph_channel
Revises: 0010_drop_page_coordinates
Create Date: 2026-10-06

"""

from __future__ import annotations

from alembic import op

revision: str = "0011_drop_graph_channel"
down_revision: str | None = "0010_drop_page_coordinates"
branch_labels: str | None = None
depends_on: str | None = None

# Spelled out rather than imported from the domain: a migration records the schema as it was
# written. This is 0001's list with `graph_build` removed, and its inverse for the downgrade.
_STAGE_VALUES = ("parse", "normalize", "chunk", "embed", "index")
_STAGE_VALUES_WITH_GRAPH = (*_STAGE_VALUES, "graph_build")


def _stage_check(values: tuple[str, ...]) -> str:
    return "stage IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.drop_table("graph_build_runs", if_exists=True)
    op.execute("DELETE FROM ingestion_jobs WHERE stage = 'graph_build'")
    op.drop_constraint("ck_ingestion_jobs_stage", "ingestion_jobs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_jobs_stage",
        "ingestion_jobs",
        _stage_check(_STAGE_VALUES),
    )


def downgrade() -> None:
    """The stage value comes back; the table deliberately does not.

    ``graph_build_runs`` is not recreated: no code in this revision writes it, and ``0005`` no
    longer replays its DDL. Restoring the value domain is enough to make a downgrade honest about
    what the schema used to accept.
    """
    op.drop_constraint("ck_ingestion_jobs_stage", "ingestion_jobs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_jobs_stage",
        "ingestion_jobs",
        _stage_check(_STAGE_VALUES_WITH_GRAPH),
    )
