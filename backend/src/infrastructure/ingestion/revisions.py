"""文档解析重试时的修订版本追加与超时失效检查。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from domain.knowledge import DocumentVersionStatus, IngestionJobStatus, IngestionStage
from domain.parsing import (
    ABANDONED_ATTEMPT_CLASS,
    ABANDONED_ATTEMPT_MESSAGE,
    ParseRetry,
    ParseRetryOutcome,
)
from infrastructure.db.mappers.ingestion import to_ingestion_job
from infrastructure.db.models.documents import DocumentRow, DocumentVersionRow
from infrastructure.db.models.ingestion import IngestionJobRow
from infrastructure.db.models.knowledge_bases import KnowledgeBaseRow

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import datetime, timedelta
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


async def append_parse_revision(
    session: AsyncSession,
    owner_id: UUID,
    version_id: UUID,
    *,
    retryable_statuses: Collection[DocumentVersionStatus],
    stale_after: timedelta,
    at: datetime,
) -> ParseRetry | None:
    """尝试为文档版本追加新的解析修订版本或返回当前作业状态。"""
    version_row = await session.scalar(
        select(DocumentVersionRow)
        .join(DocumentRow, DocumentRow.id == DocumentVersionRow.document_id)
        .join(KnowledgeBaseRow, KnowledgeBaseRow.id == DocumentRow.knowledge_base_id)
        .where(
            DocumentVersionRow.id == version_id,
            KnowledgeBaseRow.owner_id == owner_id,
        )
        .with_for_update(of=DocumentVersionRow)
    )
    if version_row is None:
        return None
    job_rows = list(
        await session.scalars(
            select(IngestionJobRow)
            .where(
                IngestionJobRow.document_version_id == version_id,
                IngestionJobRow.stage == IngestionStage.PARSE.value,
            )
            .order_by(IngestionJobRow.revision)
        )
    )
    if not job_rows:
        raise RuntimeError(f"document version {version_id} has no parse job")
    status = DocumentVersionStatus(version_row.status)
    current = job_rows[-1]
    if current.status == IngestionJobStatus.PENDING.value:
        return ParseRetry(
            outcome=ParseRetryOutcome.QUEUED,
            version_status=status,
            job=to_ingestion_job(current),
        )
    if current.status == IngestionJobStatus.RUNNING.value:
        started_at = current.started_at
        if started_at is None or at - started_at <= stale_after:
            return ParseRetry(
                outcome=ParseRetryOutcome.RUNNING,
                version_status=status,
                job=to_ingestion_job(current),
            )
        outcome = ParseRetryOutcome.STALE
        current.status = IngestionJobStatus.FAILED.value
        current.error_class = ABANDONED_ATTEMPT_CLASS
        current.error_message = ABANDONED_ATTEMPT_MESSAGE
        current.finished_at = at
        current.updated_at = at
    elif status not in retryable_statuses:
        return ParseRetry(
            outcome=ParseRetryOutcome.NOT_RETRYABLE,
            version_status=status,
            job=to_ingestion_job(current),
        )
    else:
        outcome = ParseRetryOutcome.CREATED
    job_row = IngestionJobRow(
        id=uuid4(),
        document_version_id=version_id,
        stage=IngestionStage.PARSE.value,
        status=IngestionJobStatus.PENDING.value,
        revision=current.revision + 1,
        attempt=0,
        error_class=None,
        error_message=None,
        created_at=at,
        updated_at=at,
        started_at=None,
        finished_at=None,
    )
    session.add(job_row)
    version_row.status = DocumentVersionStatus.UPLOADED.value
    version_row.updated_at = at
    await session.flush()
    return ParseRetry(
        outcome=outcome,
        version_status=DocumentVersionStatus.UPLOADED,
        job=to_ingestion_job(job_row),
    )
