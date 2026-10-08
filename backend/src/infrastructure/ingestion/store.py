"""基于 SQLAlchemy 实现文档摄取仓储及各阶段状态流转。"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, TypeVar

import sqlalchemy as sa
from sqlalchemy import select

from application.ingestion.store import FailureWrite, LeaseReclamation, StageCompletion, StageWrite
from domain.chunks.model import ChildChunk, ChunkArtifact, ChunkClaim, ParentChunk
from domain.embedding import EmbeddingClaim, IndexClaim, IndexTarget
from domain.knowledge import (
    DocumentVersionStatus,
    IngestionStage,
    RetrySchedule,
    running_status_for,
)
from domain.parsing import (
    ParseArtifact,
    ParseClaim,
    ParseRetry,
    ParseTarget,
)
from infrastructure.db.mappers.ingestion import to_ingestion_job
from infrastructure.db.models.chunks import ChunkArtifactRow
from infrastructure.db.models.documents import DocumentVersionRow
from infrastructure.ingestion.attempts import (
    append_stage_job,
    child_count,
    chunk_target,
    claim_job,
    current_job,
    due_jobs,
    embedding_target,
    expire_attempt,
    expired_attempts,
    mark_dispatched,
    mark_version_failure,
    replaced_object_key,
    requeue_expired_attempt,
    reschedule_attempt,
    start_attempt,
    succeed_attempt,
    terminal_attempt,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Collection, Sequence
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from domain.knowledge import IngestionJob, StageFailureState
    from infrastructure.db.stores.chunk_store import SqlAlchemyChunkStore
from infrastructure.ingestion.artifacts import record_parse_artifact
from infrastructure.ingestion.revisions import append_parse_revision

TargetT = TypeVar("TargetT")
ClaimT = TypeVar("ClaimT")


class SqlAlchemyIngestionStore:
    """摄取仓储 SQLAlchemy 异步实现。"""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        chunks: SqlAlchemyChunkStore,
        *,
        retry: RetrySchedule,
        lease_seconds: float,
    ) -> None:
        self._sessions = sessions
        self._chunks = chunks
        self._retry = retry
        self._lease_seconds = lease_seconds

    def _lease_until(self, at: datetime) -> datetime:
        return at + timedelta(seconds=self._lease_seconds)

    async def start_parse_retry(
        self,
        owner_id: UUID,
        version_id: UUID,
        *,
        retryable_statuses: Collection[DocumentVersionStatus],
        stale_after: timedelta,
        at: datetime,
    ) -> ParseRetry | None:
        """发起解析重试并追加作业修订版本。"""
        async with self._sessions.begin() as session:
            return await append_parse_revision(
                session,
                owner_id,
                version_id,
                retryable_statuses=retryable_statuses,
                stale_after=stale_after,
                at=at,
            )

    async def begin_parse(self, version_id: UUID, *, at: datetime) -> ParseClaim | None:
        """启动直接解析并将当前作业置为运行中。"""
        return await self._begin(
            version_id, IngestionStage.PARSE, at=at, load=_parse_target, claim=ParseClaim
        )

    async def claim_parse_job(
        self,
        version_id: UUID,
        job_id: UUID,
        *,
        at: datetime,
    ) -> ParseClaim | None:
        """认领队列中待处理的解析作业。"""
        return await self._claim(
            version_id,
            job_id,
            IngestionStage.PARSE,
            at=at,
            load=_parse_target,
            claim=ParseClaim,
        )

    async def complete_parse(
        self,
        artifact: ParseArtifact,
        *,
        job_id: UUID,
        attempt: int,
        at: datetime,
    ) -> StageCompletion:
        """记录解析产物，将文档置为已解析并派发分块作业。"""
        async with self._sessions.begin() as session:
            version_row = await session.scalar(
                select(DocumentVersionRow).where(
                    DocumentVersionRow.id == artifact.document_version_id
                )
            )
            if version_row is None:
                return StageCompletion(write=StageWrite.VANISHED)
            if not await succeed_attempt(session, job_id, attempt=attempt, at=at):
                return StageCompletion(write=StageWrite.SUPERSEDED)
            replaced_key = replaced_object_key(
                await record_parse_artifact(session, artifact, at=at),
                artifact.markdown_object_key,
            )
            version_row.status = DocumentVersionStatus.PARSED.value
            version_row.updated_at = at
            chunk_job = await append_stage_job(
                session,
                artifact.document_version_id,
                IngestionStage.CHUNK,
                at=at,
            )
            await session.flush()
            return StageCompletion(
                write=StageWrite.RECORDED,
                next_job=to_ingestion_job(chunk_job),
                replaced_object_key=replaced_key,
            )

    async def begin_chunk(self, version_id: UUID, *, at: datetime) -> ChunkClaim | None:
        """启动直接分块并将当前作业置为运行中。"""
        return await self._begin(
            version_id, IngestionStage.CHUNK, at=at, load=chunk_target, claim=ChunkClaim
        )

    async def claim_chunk_job(
        self,
        version_id: UUID,
        job_id: UUID,
        *,
        at: datetime,
    ) -> ChunkClaim | None:
        """认领队列中待处理的分块作业。"""
        return await self._claim(
            version_id,
            job_id,
            IngestionStage.CHUNK,
            at=at,
            load=chunk_target,
            claim=ChunkClaim,
        )

    async def complete_chunk(
        self,
        artifact: ChunkArtifact,
        *,
        job_id: UUID,
        attempt: int,
        parents: Sequence[ParentChunk],
        children: Sequence[ChildChunk],
        at: datetime,
    ) -> StageCompletion:
        """保存分块产物与分块数据，并派发向量化作业。"""
        async with self._sessions.begin() as session:
            version_row = await session.scalar(
                select(DocumentVersionRow).where(
                    DocumentVersionRow.id == artifact.document_version_id
                )
            )
            if version_row is None:
                return StageCompletion(write=StageWrite.VANISHED)
            if not await succeed_attempt(session, job_id, attempt=attempt, at=at):
                return StageCompletion(write=StageWrite.SUPERSEDED)
            previous_artifact_key = await session.scalar(
                select(ChunkArtifactRow.object_key).where(
                    ChunkArtifactRow.document_version_id == artifact.document_version_id
                )
            )
            await self._chunks.replace_version_chunks(
                session,
                artifact=artifact,
                parents=parents,
                children=children,
                at=at,
            )
            version_row.status = DocumentVersionStatus.CHUNKING.value
            version_row.updated_at = at
            embed_job = await append_stage_job(
                session,
                artifact.document_version_id,
                IngestionStage.EMBED,
                at=at,
            )
            await session.flush()
            return StageCompletion(
                write=StageWrite.RECORDED,
                next_job=to_ingestion_job(embed_job),
                replaced_object_key=replaced_object_key(previous_artifact_key, artifact.object_key),
            )

    async def begin_embed(self, version_id: UUID, *, at: datetime) -> EmbeddingClaim | None:
        """启动直接向量化并将当前作业置为运行中。"""
        return await self._begin(
            version_id, IngestionStage.EMBED, at=at, load=embedding_target, claim=EmbeddingClaim
        )

    async def claim_embed_job(
        self,
        version_id: UUID,
        job_id: UUID,
        *,
        at: datetime,
    ) -> EmbeddingClaim | None:
        """认领队列中待处理的向量化作业。"""
        return await self._claim(
            version_id,
            job_id,
            IngestionStage.EMBED,
            at=at,
            load=embedding_target,
            claim=EmbeddingClaim,
        )

    async def complete_embed(
        self,
        version_id: UUID,
        *,
        job_id: UUID,
        attempt: int,
        at: datetime,
    ) -> StageCompletion:
        """完成向量化并派发索引验证作业。"""
        async with self._sessions.begin() as session:
            version_row = await session.scalar(
                select(DocumentVersionRow).where(DocumentVersionRow.id == version_id)
            )
            if version_row is None:
                return StageCompletion(write=StageWrite.VANISHED)
            if not await succeed_attempt(session, job_id, attempt=attempt, at=at):
                return StageCompletion(write=StageWrite.SUPERSEDED)
            version_row.status = DocumentVersionStatus.EMBEDDING.value
            version_row.updated_at = at
            index_job = await append_stage_job(session, version_id, IngestionStage.INDEX, at=at)
            await session.flush()
            return StageCompletion(
                write=StageWrite.RECORDED,
                next_job=to_ingestion_job(index_job),
            )

    async def begin_index(self, version_id: UUID, *, at: datetime) -> IndexClaim | None:
        """启动直接索引验证并将当前作业置为运行中。"""
        return await self._begin(
            version_id, IngestionStage.INDEX, at=at, load=_index_target, claim=IndexClaim
        )

    async def claim_index_job(
        self,
        version_id: UUID,
        job_id: UUID,
        *,
        at: datetime,
    ) -> IndexClaim | None:
        """认领队列中待处理的索引作业。"""
        return await self._claim(
            version_id,
            job_id,
            IngestionStage.INDEX,
            at=at,
            load=_index_target,
            claim=IndexClaim,
        )

    async def complete_index(
        self,
        version_id: UUID,
        *,
        job_id: UUID,
        attempt: int,
        at: datetime,
    ) -> StageCompletion:
        """完成索引阶段，将文档置为就绪。"""
        async with self._sessions.begin() as session:
            version_row = await session.scalar(
                select(DocumentVersionRow).where(DocumentVersionRow.id == version_id)
            )
            if version_row is None:
                return StageCompletion(write=StageWrite.VANISHED)
            if not await succeed_attempt(session, job_id, attempt=attempt, at=at):
                return StageCompletion(write=StageWrite.SUPERSEDED)
            version_row.status = DocumentVersionStatus.READY.value
            version_row.updated_at = at
            return StageCompletion(write=StageWrite.RECORDED)

    async def fail_attempt(
        self,
        *,
        version_id: UUID,
        job_id: UUID,
        attempt: int,
        stage: IngestionStage,
        error_class: str,
        error_message: str,
        retryable: bool,
        state: StageFailureState,
        at: datetime,
    ) -> FailureWrite:
        """按重试预算记录各流水线阶段的失败：置回等待中，或写成终态。"""
        async with self._sessions.begin() as session:
            version_row = await session.scalar(
                select(DocumentVersionRow).where(DocumentVersionRow.id == version_id)
            )
            if version_row is None:
                return FailureWrite.VANISHED
            next_attempt_at = self._retry.next_attempt_at(attempt, at=at) if retryable else None
            if next_attempt_at is not None:
                rescheduled = await reschedule_attempt(
                    session,
                    job_id,
                    attempt=attempt,
                    not_before=next_attempt_at,
                    error_class=error_class,
                    error_message=error_message,
                    at=at,
                )
                if not rescheduled:
                    return FailureWrite.SUPERSEDED
                version_row.updated_at = at
                return FailureWrite.RETRY_SCHEDULED
            recorded = await terminal_attempt(
                session,
                job_id,
                attempt=attempt,
                status=state.job_status,
                error_class=error_class,
                error_message=error_message,
                at=at,
            )
            if not recorded:
                return FailureWrite.SUPERSEDED
            version_row.status = state.version_status.value
            version_row.updated_at = at
            return FailureWrite.FAILED

    async def due_jobs(
        self,
        *,
        at: datetime,
        limit: int,
        republish_before: datetime,
    ) -> Sequence[IngestionJob]:
        """读取到点且未在重发窗口内投递过的等待中作业。"""
        async with self._sessions() as session:
            return await due_jobs(
                session,
                at=at,
                limit=limit,
                republish_before=republish_before,
            )

    async def mark_dispatched(self, job_ids: Sequence[UUID], *, at: datetime) -> None:
        """记录一批作业最近一次成功投递的时间。"""
        async with self._sessions.begin() as session:
            await mark_dispatched(session, job_ids, at=at)

    async def reclaim_expired_leases(
        self,
        *,
        at: datetime,
        limit: int,
    ) -> Sequence[LeaseReclamation]:
        """接管租约已过期的尝试：置回等待中，或用尽预算后写成终态。"""
        reclaimed: list[LeaseReclamation] = []
        async with self._sessions.begin() as session:
            for job_row in await expired_attempts(session, at=at, limit=limit):
                stage = IngestionStage(job_row.stage)
                requeued = job_row.attempt < self._retry.max_attempts
                settled = (
                    await requeue_expired_attempt(session, job_row, at=at)
                    if requeued
                    else await expire_attempt(session, job_row, at=at)
                )
                if not settled:
                    continue
                if not requeued:
                    await mark_version_failure(
                        session,
                        job_row.document_version_id,
                        stage,
                        at=at,
                    )
                reclaimed.append(
                    LeaseReclamation(
                        job_id=job_row.id,
                        document_version_id=job_row.document_version_id,
                        stage=stage,
                        attempt=job_row.attempt,
                        requeued=requeued,
                    )
                )
        return tuple(reclaimed)

    async def _begin(
        self,
        version_id: UUID,
        stage: IngestionStage,
        *,
        at: datetime,
        load: Callable[[AsyncSession, UUID], Awaitable[TargetT]],
        claim: Callable[[UUID, TargetT, int], ClaimT],
    ) -> ClaimT | None:
        """运维路径启动一次尝试：锁定当前作业行、占有租约并读取阶段输入。"""
        async with self._sessions.begin() as session:
            version_row = await session.scalar(
                select(DocumentVersionRow).where(DocumentVersionRow.id == version_id)
            )
            if version_row is None:
                return None
            job_row = await current_job(session, version_id, stage, for_update=True)
            start_attempt(version_row, job_row, at=at, lease_expires_at=self._lease_until(at))
            return claim(job_row.id, await load(session, version_id), job_row.attempt)

    async def _claim(
        self,
        version_id: UUID,
        job_id: UUID,
        stage: IngestionStage,
        *,
        at: datetime,
        load: Callable[[AsyncSession, UUID], Awaitable[TargetT]],
        claim: Callable[[UUID, TargetT, int], ClaimT],
    ) -> ClaimT | None:
        """队列路径认领一次尝试：条件写入并占有租约、置版本运行态、读取阶段输入。"""
        async with self._sessions.begin() as session:
            attempt = await claim_job(
                session,
                version_id,
                job_id,
                stage,
                at=at,
                lease_expires_at=self._lease_until(at),
            )
            if attempt is None:
                return None
            await session.execute(
                sa.update(DocumentVersionRow)
                .where(DocumentVersionRow.id == version_id)
                .values(status=running_status_for(stage).value, updated_at=at)
            )
            return claim(job_id, await load(session, version_id), attempt)


async def _parse_target(session: AsyncSession, version_id: UUID) -> ParseTarget:
    row = (
        await session.execute(
            select(DocumentVersionRow.source_object_key, DocumentVersionRow.mime_type).where(
                DocumentVersionRow.id == version_id
            )
        )
    ).one()
    return ParseTarget(
        document_version_id=version_id,
        source_object_key=row.source_object_key,
        mime_type=row.mime_type,
    )


async def _index_target(session: AsyncSession, version_id: UUID) -> IndexTarget:
    return IndexTarget(
        document_version_id=version_id,
        child_count=await child_count(session, version_id),
    )
