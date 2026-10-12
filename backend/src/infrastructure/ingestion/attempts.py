"""摄取流水线各阶段任务尝试的状态控制与条件写入逻辑。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import func, select

from domain.chunks.model import ChunkTarget
from domain.embedding import EmbeddingTarget
from domain.knowledge import (
    IngestionJobStatus,
    IngestionStage,
    failure_status_for,
    running_status_for,
)
from infrastructure.db.mappers.ingestion import to_child_chunk, to_ingestion_job
from infrastructure.db.models.chunks import ChildChunkRow
from infrastructure.db.models.documents import DocumentVersionRow
from infrastructure.db.models.ingestion import IngestionJobRow, ParseArtifactRow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from domain.knowledge import IngestionJob

LEASE_EXPIRED_ERROR_CLASS = "AttemptLeaseExpired"
LEASE_EXPIRED_MESSAGE = "任务尝试已超出租约有效期且未上报结果；作业已被重新接管"


async def current_job(
    session: AsyncSession,
    version_id: UUID,
    stage: IngestionStage,
    *,
    for_update: bool = False,
) -> IngestionJobRow:
    """获取文档版本在指定阶段的最新版本作业记录。"""
    statement = (
        select(IngestionJobRow)
        .where(
            IngestionJobRow.document_version_id == version_id,
            IngestionJobRow.stage == stage.value,
        )
        .order_by(IngestionJobRow.revision.desc())
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update()
    job_row = await session.scalar(statement)
    if job_row is None:
        raise RuntimeError(f"文档版本 {version_id} 缺少 {stage.value} 阶段的作业记录") from None
    return job_row


def start_attempt(
    version_row: DocumentVersionRow,
    job_row: IngestionJobRow,
    *,
    at: datetime,
    lease_expires_at: datetime,
) -> None:
    """启动一次运维路径的尝试：累加尝试次数并占有作业租约。"""
    version_row.status = running_status_for(IngestionStage(job_row.stage)).value
    version_row.updated_at = at
    job_row.status = IngestionJobStatus.RUNNING.value
    job_row.attempt += 1
    job_row.started_at = at
    job_row.finished_at = None
    job_row.not_before = None
    job_row.lease_expires_at = lease_expires_at
    job_row.dispatched_at = None
    job_row.error_class = None
    job_row.error_message = None
    job_row.updated_at = at


async def claim_job(
    session: AsyncSession,
    version_id: UUID,
    job_id: UUID,
    stage: IngestionStage,
    *,
    at: datetime,
    lease_expires_at: datetime,
) -> int | None:
    """原子认领等待中的作业并占有租约，成功则返回本次尝试序号。"""
    return await session.scalar(
        sa.update(IngestionJobRow)
        .where(
            IngestionJobRow.id == job_id,
            IngestionJobRow.document_version_id == version_id,
            IngestionJobRow.stage == stage.value,
            IngestionJobRow.status == IngestionJobStatus.PENDING.value,
        )
        .values(
            status=IngestionJobStatus.RUNNING.value,
            attempt=IngestionJobRow.attempt + 1,
            started_at=at,
            finished_at=None,
            not_before=None,
            lease_expires_at=lease_expires_at,
            dispatched_at=None,
            error_class=None,
            error_message=None,
            updated_at=at,
        )
        .returning(IngestionJobRow.attempt)
    )


async def _settle(
    session: AsyncSession,
    job_id: UUID,
    *,
    attempt: int,
    status: IngestionJobStatus,
    error_class: str | None,
    error_message: str | None,
    not_before: datetime | None,
    finished_at: datetime | None,
    at: datetime,
) -> bool:
    """以尝试序号为围栏终结一次尝试，旧尝试的结算被拒绝。"""
    settled = await session.scalar(
        sa.update(IngestionJobRow)
        .where(
            IngestionJobRow.id == job_id,
            IngestionJobRow.status == IngestionJobStatus.RUNNING.value,
            IngestionJobRow.attempt == attempt,
        )
        .values(
            status=status.value,
            error_class=error_class,
            error_message=error_message,
            not_before=not_before,
            lease_expires_at=None,
            finished_at=finished_at,
            updated_at=at,
        )
        .returning(IngestionJobRow.id)
    )
    return settled is not None


async def succeed_attempt(
    session: AsyncSession,
    job_id: UUID,
    *,
    attempt: int,
    at: datetime,
) -> bool:
    """标记本次尝试成功。"""
    return await _settle(
        session,
        job_id,
        attempt=attempt,
        status=IngestionJobStatus.SUCCEEDED,
        error_class=None,
        error_message=None,
        not_before=None,
        finished_at=at,
        at=at,
    )


async def reschedule_attempt(
    session: AsyncSession,
    job_id: UUID,
    *,
    attempt: int,
    not_before: datetime,
    error_class: str,
    error_message: str,
    at: datetime,
) -> bool:
    """把本次尝试置回等待中，并记录允许再次投递的时间。"""
    return await _settle(
        session,
        job_id,
        attempt=attempt,
        status=IngestionJobStatus.PENDING,
        error_class=error_class,
        error_message=error_message,
        not_before=not_before,
        finished_at=None,
        at=at,
    )


async def terminal_attempt(
    session: AsyncSession,
    job_id: UUID,
    *,
    attempt: int,
    status: IngestionJobStatus,
    error_class: str,
    error_message: str,
    at: datetime,
) -> bool:
    """把本次尝试写成终态。"""
    return await _settle(
        session,
        job_id,
        attempt=attempt,
        status=status,
        error_class=error_class,
        error_message=error_message,
        not_before=None,
        finished_at=at,
        at=at,
    )


async def due_jobs(
    session: AsyncSession,
    *,
    at: datetime,
    limit: int,
    republish_before: datetime,
) -> Sequence[IngestionJob]:
    """读取到点且未在重发窗口内投递过的等待中作业。"""
    rows = await session.scalars(
        select(IngestionJobRow)
        .where(
            IngestionJobRow.status == IngestionJobStatus.PENDING.value,
            sa.or_(IngestionJobRow.not_before.is_(None), IngestionJobRow.not_before <= at),
            sa.or_(
                IngestionJobRow.dispatched_at.is_(None),
                IngestionJobRow.dispatched_at <= republish_before,
            ),
        )
        .order_by(IngestionJobRow.not_before.asc().nulls_first(), IngestionJobRow.updated_at)
        .limit(limit)
    )
    return tuple(to_ingestion_job(row) for row in rows)


async def mark_dispatched(session: AsyncSession, job_ids: Sequence[UUID], *, at: datetime) -> None:
    """记录一批作业最近一次成功投递的时间。"""
    if not job_ids:
        return
    await session.execute(
        sa.update(IngestionJobRow)
        .where(
            IngestionJobRow.id.in_(list(job_ids)),
            IngestionJobRow.status == IngestionJobStatus.PENDING.value,
        )
        .values(dispatched_at=at)
    )


async def expired_attempts(
    session: AsyncSession,
    *,
    at: datetime,
    limit: int,
) -> Sequence[IngestionJobRow]:
    """锁定并读取租约已经过期的运行中作业。"""
    rows = await session.scalars(
        select(IngestionJobRow)
        .where(
            IngestionJobRow.status == IngestionJobStatus.RUNNING.value,
            IngestionJobRow.lease_expires_at.is_not(None),
            IngestionJobRow.lease_expires_at <= at,
        )
        .order_by(IngestionJobRow.lease_expires_at, IngestionJobRow.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return tuple(rows)


async def requeue_expired_attempt(
    session: AsyncSession,
    job_row: IngestionJobRow,
    *,
    at: datetime,
) -> bool:
    """把租约过期的尝试按尝试序号围栏置回等待中。"""
    settled = await session.scalar(
        sa.update(IngestionJobRow)
        .where(
            IngestionJobRow.id == job_row.id,
            IngestionJobRow.status == IngestionJobStatus.RUNNING.value,
            IngestionJobRow.attempt == job_row.attempt,
        )
        .values(
            status=IngestionJobStatus.PENDING.value,
            error_class=LEASE_EXPIRED_ERROR_CLASS,
            error_message=LEASE_EXPIRED_MESSAGE,
            not_before=at,
            dispatched_at=None,
            lease_expires_at=None,
            finished_at=None,
            updated_at=at,
        )
        .returning(IngestionJobRow.id)
    )
    return settled is not None


async def expire_attempt(
    session: AsyncSession,
    job_row: IngestionJobRow,
    *,
    at: datetime,
) -> bool:
    """把预算耗尽的租约过期尝试按尝试序号围栏写成终态。"""
    settled = await session.scalar(
        sa.update(IngestionJobRow)
        .where(
            IngestionJobRow.id == job_row.id,
            IngestionJobRow.status == IngestionJobStatus.RUNNING.value,
            IngestionJobRow.attempt == job_row.attempt,
        )
        .values(
            status=IngestionJobStatus.FAILED.value,
            error_class=LEASE_EXPIRED_ERROR_CLASS,
            error_message=LEASE_EXPIRED_MESSAGE,
            not_before=None,
            lease_expires_at=None,
            finished_at=at,
            updated_at=at,
        )
        .returning(IngestionJobRow.id)
    )
    return settled is not None


async def mark_version_failure(
    session: AsyncSession,
    version_id: UUID,
    stage: IngestionStage,
    *,
    at: datetime,
) -> None:
    """按阶段失败状态终结文档版本，且只在它仍停在该阶段运行态时生效。"""
    await session.execute(
        sa.update(DocumentVersionRow)
        .where(
            DocumentVersionRow.id == version_id,
            DocumentVersionRow.status == running_status_for(stage).value,
        )
        .values(status=failure_status_for(stage).value, updated_at=at)
    )


async def child_count(session: AsyncSession, version_id: UUID) -> int:
    """统计文档版本当前拥有的子分块总数。"""
    count = await session.scalar(
        select(func.count())
        .select_from(ChildChunkRow)
        .where(ChildChunkRow.document_version_id == version_id)
    )
    return count or 0


async def embedding_target(session: AsyncSession, version_id: UUID) -> EmbeddingTarget:
    """读取向量化所需的子分块。"""
    exists = await session.scalar(
        select(DocumentVersionRow.id).where(DocumentVersionRow.id == version_id)
    )
    if exists is None:
        raise RuntimeError(f"document version {version_id} has no document")
    child_rows = await session.scalars(
        select(ChildChunkRow)
        .where(ChildChunkRow.document_version_id == version_id)
        .order_by(ChildChunkRow.ordinal)
    )
    return EmbeddingTarget(
        document_version_id=version_id,
        children=tuple(to_child_chunk(row) for row in child_rows),
    )


async def append_stage_job(
    session: AsyncSession,
    version_id: UUID,
    stage: IngestionStage,
    *,
    at: datetime,
) -> IngestionJobRow:
    """追加指定阶段的下一修订版本待处理作业记录。"""
    newest = await session.scalar(
        select(func.max(IngestionJobRow.revision)).where(
            IngestionJobRow.document_version_id == version_id,
            IngestionJobRow.stage == stage.value,
        )
    )
    job_row = IngestionJobRow(
        id=uuid4(),
        document_version_id=version_id,
        stage=stage.value,
        status=IngestionJobStatus.PENDING.value,
        revision=(newest or 0) + 1,
        attempt=0,
        error_class=None,
        error_message=None,
        created_at=at,
        updated_at=at,
        started_at=None,
        finished_at=None,
        not_before=None,
        lease_expires_at=None,
        dispatched_at=None,
    )
    session.add(job_row)
    return job_row


def replaced_object_key(previous_key: str | None, published_key: str) -> str | None:
    """计算被替换且需要清理的历史对象存储键。"""
    if previous_key is None or previous_key == published_key:
        return None
    return previous_key


async def chunk_target(session: AsyncSession, version_id: UUID) -> ChunkTarget:
    """读取分块阶段所需的 Markdown 产物定位信息。"""
    artifact = (
        await session.execute(
            select(
                ParseArtifactRow.markdown_object_key,
                ParseArtifactRow.checksum,
                ParseArtifactRow.size_bytes,
            ).where(ParseArtifactRow.document_version_id == version_id)
        )
    ).one_or_none()
    if artifact is None:
        raise RuntimeError(f"document version {version_id} has a chunk job but no parse artifact")
    return ChunkTarget(
        document_version_id=version_id,
        markdown_object_key=artifact.markdown_object_key,
        markdown_checksum=artifact.checksum,
        markdown_size_bytes=artifact.size_bytes,
    )
