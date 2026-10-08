"""``normalize`` leaves the stage value domain.

Normalisation is a step inside the parse route — the parser's output is normalised into the Markdown
a version's artifact holds — not a stage of its own: nothing ever created a ``normalize`` job, and
``docs/architecture/ingestion-pipeline.md`` describes it that way. The value stayed in the check
constraint only because the enum still had it. Removing the enum member without narrowing the
constraint would leave the database accepting a stage no code can run, so the constraint is swapped
here. The stage values are spelled out rather than imported: a migration records the schema as it was
written.

Revision ID: 0013_drop_normalize_stage
Revises: 0012_ingestion_leases
Create Date: 2026-10-07

"""

from __future__ import annotations

from alembic import op

revision: str = "0013_drop_normalize_stage"
down_revision: str | None = "0012_ingestion_leases"
branch_labels: str | None = None
depends_on: str | None = None

_STAGE_VALUES = ("parse", "chunk", "embed", "index")
_STAGE_VALUES_WITH_NORMALIZE = ("parse", "normalize", "chunk", "embed", "index")


def _stage_check(values: tuple[str, ...]) -> str:
    return "stage IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.execute("DELETE FROM ingestion_jobs WHERE stage = 'normalize'")
    op.drop_constraint("ck_ingestion_jobs_stage", "ingestion_jobs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_jobs_stage",
        "ingestion_jobs",
        _stage_check(_STAGE_VALUES),
    )


def downgrade() -> None:
    op.drop_constraint("ck_ingestion_jobs_stage", "ingestion_jobs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_jobs_stage",
        "ingestion_jobs",
        _stage_check(_STAGE_VALUES_WITH_NORMALIZE),
    )
