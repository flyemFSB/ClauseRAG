"""摄取任务分发接口、提示投递与到期对账。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

import structlog

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from application.ingestion.store import IngestionStore, LeaseReclamation
    from domain.knowledge import IngestionJob, IngestionStage

log = structlog.get_logger(__name__)

RECONCILE_LIMIT = 50
LEASE_RECLAIM_LIMIT = 50


async def dispatch_committed_job(
    dispatcher: JobDispatcher,
    job: IngestionJob,
    *,
    event: str,
) -> None:
    """提交后立即投递任务消息：低延迟提示，失败由对账兜底。"""
    try:
        await dispatcher.dispatch_stage(
            stage=job.stage,
            document_version_id=job.document_version_id,
            job_id=job.id,
        )
    except JobDispatchError as error:
        log.warning(
            event,
            document_version_id=str(job.document_version_id),
            job_id=str(job.id),
            stage=job.stage.value,
            error_class=type(error).__name__,
        )


class IngestionDispatch:
    """按数据库状态对账并投递到期作业：投递的唯一所有者。"""

    def __init__(
        self,
        *,
        documents: IngestionStore,
        dispatcher: JobDispatcher,
        republish_seconds: float,
        limit: int = RECONCILE_LIMIT,
    ) -> None:
        self._documents = documents
        self._dispatcher = dispatcher
        self._republish_seconds = republish_seconds
        self._limit = limit

    async def reconcile(self) -> Sequence[LeaseReclamation]:
        """接管过期租约，并投递每一个到点的等待中作业。"""
        at = datetime.now(UTC)
        reclaimed = await self._documents.reclaim_expired_leases(
            at=at,
            limit=LEASE_RECLAIM_LIMIT,
        )
        for item in reclaimed:
            log.warning(
                "摄取尝试租约过期已被接管",
                document_version_id=str(item.document_version_id),
                job_id=str(item.job_id),
                stage=item.stage.value,
                attempt=item.attempt,
                requeued=item.requeued,
            )
        jobs = await self._documents.due_jobs(
            at=at,
            limit=self._limit,
            republish_before=at - timedelta(seconds=self._republish_seconds),
        )
        dispatched: list[UUID] = []
        for job in jobs:
            try:
                await self._dispatcher.dispatch_stage(
                    stage=job.stage,
                    document_version_id=job.document_version_id,
                    job_id=job.id,
                )
            except JobDispatchError as error:
                log.warning(
                    "摄取任务投递失败，等待下一轮对账",
                    document_version_id=str(job.document_version_id),
                    job_id=str(job.id),
                    stage=job.stage.value,
                    error_class=type(error).__name__,
                )
                continue
            dispatched.append(job.id)
        if dispatched:
            await self._documents.mark_dispatched(dispatched, at=at)
        if jobs:
            log.info(
                "摄取任务对账完成",
                due=len(jobs),
                dispatched=len(dispatched),
                reclaimed=len(reclaimed),
            )
        return reclaimed


class JobDispatchError(RuntimeError):
    """任务分发至消息队列异常。"""


class JobDispatcher(Protocol):
    """摄取任务分发器协议。"""

    async def dispatch_stage(
        self,
        *,
        stage: IngestionStage,
        document_version_id: UUID,
        job_id: UUID,
    ) -> None:
        """发布指定阶段的任务消息至消息队列。"""
        ...
