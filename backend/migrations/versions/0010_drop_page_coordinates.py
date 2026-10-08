"""Page coordinates leave the citation contract.

A page number was only ever available on one of the four parse routes. ``anydoc`` reports no page
number and no page marker for PDF, DOCX, PPTX or XLSX, HTML and plain text have none, so
``page_start``/``page_end`` were NULL for every chunk and every citation produced outside the OCR
route — including every PDF. The OCR route did have real page numbers, because PaddleOCR-VL's
``layoutParsingResults`` holds one element per page, and it recorded them as ``page_spans``: a page
to line-range map that survived normalization and that ``page_range()`` intersected with a chunk's
line range.

What actually locates a citation is the line range plus the quote, and both address the normalized
Markdown artifact the answer was built from (ADR-0016). A page number added nothing to that pair: it
was NULL where it was not known, and redundant where it was, because a page is a line range by
another name.

So the coordinate is dropped, and with it the only consumer of ``page_spans``. ``page_range()`` is
removed, which makes the map — and the normalization remap that kept it addressing the right lines —
unreachable, so they go too rather than sit as a field nothing reads.

``page_count`` stays. It is a fact about the document ("this scan is twenty pages"), it needs no
line map, the parse stage reports it and the ingestion stepper shows it.

The downgrade re-adds the columns as NULL. The dropped values are not recoverable and are not
backfilled: they were NULL on every non-OCR route, and on the OCR route they came from a page map
that no longer exists. A schema migrated down and up again therefore holds the columns it started
with, not the coordinates it started with.

Revision ID: 0010_drop_page_coordinates
Revises: 0009_drop_parse_projection
Create Date: 2026-10-06

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010_drop_page_coordinates"
down_revision: str | None = "0009_drop_parse_projection"
branch_labels: str | None = None
depends_on: str | None = None

# One (table, column, type) triple per dropped column, so the two directions cannot list them in
# different orders and the downgrade cannot restore a column with the wrong type.
_COLUMNS: tuple[tuple[str, str, sa.types.TypeEngine[object]], ...] = (
    ("parent_chunks", "page_start", sa.Integer()),
    ("parent_chunks", "page_end", sa.Integer()),
    ("child_chunks", "page_start", sa.Integer()),
    ("child_chunks", "page_end", sa.Integer()),
    ("citations", "page_start", sa.Integer()),
    ("citations", "page_end", sa.Integer()),
    ("parse_artifacts", "page_spans", JSONB()),
)


def upgrade() -> None:
    for table, column, _ in _COLUMNS:
        op.drop_column(table, column)


def downgrade() -> None:
    for table, column, type_ in _COLUMNS:
        op.add_column(table, sa.Column(column, type_, nullable=True))
