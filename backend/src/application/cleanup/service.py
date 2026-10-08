"""清理流水线：异步幂等清理已删除业务记录的外部衍生数据。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

import structlog

from application.shared.vectors import VectorIndexRejectedError
from domain.cleanup import CleanupIntent, CleanupKind, CleanupStatus

if TYPE_CHECKING:
    from uuid import UUID

    from application.shared.storage import ObjectStorage
    from application.shared.vectors import VectorIndex

log = structlog.get_logger(__name__)


class CleanupStore(Protocol):
    """清理意图持久化存储协议"""

    async def claim_next(
        self,
        *,
        at: datetime,
        not_before: datetime,
        lease_before: datetime,
        max_attempts: int,
    ) -> CleanupIntent | None:
        """认领下一个待处理的清理意图"""
        ...

    async def complete(self, intent_id: UUID, *, attempt: int, at: datetime) -> bool:
        """标记指定尝试次数的清理意图执行成功"""
        ...

    async def fail(
        self,
        intent_id: UUID,
        *,
        attempt: int,
        status: CleanupStatus,
        error_class: str,
        error_message: str,
        at: datetime,
    ) -> bool:
        """记录清理意图执行失败信息"""
        ...


class CleanupLane:
    """清理执行引擎：逐项清理外部存储对象与向量点"""

    def __init__(
        self,
        *,
        intents: CleanupStore,
        objects: ObjectStorage,
        index: VectorIndex,
        max_attempts: int,
        retry_backoff_seconds: float,
        lease_seconds: float,
    ) -> None:
        self._intents = intents
        self._objects = objects
        self._index = index
        self._max_attempts = max_attempts
        self._retry_backoff = timedelta(seconds=retry_backoff_seconds)
        self._lease = timedelta(seconds=lease_seconds)

    async def run_pending(self, *, limit: int) -> int:
        """轮询并认领处理一批待执行清理任务"""
        attempts = 0
        for _ in range(limit):
            at = datetime.now(UTC)
            intent = await self._intents.claim_next(
                at=at,
                not_before=at - self._retry_backoff,
                lease_before=at - self._lease,
                max_attempts=self._max_attempts,
            )
            if intent is None:
                break
            attempts += 1
            await self._run(intent, at=at)
        return attempts

    async def _run(self, intent: CleanupIntent, *, at: datetime) -> None:
        """执行单个清理任务步骤并更新持久化状态"""
        try:
            await self._clean(intent)
        except Exception as error:
            retry = self._is_transient(error) and intent.attempt < self._max_attempts
            status = CleanupStatus.PENDING if retry else CleanupStatus.FAILED
            settled = await self._intents.fail(
                intent.id,
                attempt=intent.attempt,
                status=status,
                error_class=type(error).__name__,
                error_message=str(error),
                at=at,
            )
            if not settled:
                _log_refused(intent, status=status)
                return
            log_method = log.warning if retry else log.error
            log_method(
                "清理任务尝试失败",
                cleanup_id=str(intent.id),
                kind=intent.kind.value,
                document_id=None if intent.document_id is None else str(intent.document_id),
                knowledge_base_id=str(intent.knowledge_base_id),
                attempt=intent.attempt,
                retry=retry,
                error_class=type(error).__name__,
                error_message=str(error),
            )
            return
        settled = await self._intents.complete(
            intent.id,
            attempt=intent.attempt,
            at=datetime.now(UTC),
        )
        if not settled:
            _log_refused(intent, status=CleanupStatus.SUCCEEDED)
            return
        log.info(
            "清理任务完成",
            cleanup_id=str(intent.id),
            kind=intent.kind.value,
            document_id=None if intent.document_id is None else str(intent.document_id),
            knowledge_base_id=str(intent.knowledge_base_id),
            attempt=intent.attempt,
            object_keys=len(intent.object_keys),
            document_version_ids=len(intent.document_version_ids),
            documents=len(intent.child_ids),
        )

    async def _clean(self, intent: CleanupIntent) -> None:
        """按依赖顺序清理对象存储与向量索引数据"""
        await self._delete_objects(intent)
        if intent.kind is CleanupKind.KNOWLEDGE_BASE:
            await self._index.delete_knowledge_base(intent.knowledge_base_id)
            return
        if intent.document_version_ids:
            await self._index.delete_versions(intent.document_version_ids)

    async def _delete_objects(self, intent: CleanupIntent) -> None:
        """删除关联的所有对象存储键"""
        for key in intent.object_keys:
            await self._objects.delete(key)

    @staticmethod
    def _is_transient(error: BaseException) -> bool:
        """判断清理异常是否属于可重试的偶发错误"""
        return not isinstance(error, VectorIndexRejectedError)


def _log_refused(intent: CleanupIntent, *, status: CleanupStatus) -> None:
    """记录因租约过期导致的任务结算拒绝日志"""
    log.warning(
        "清理任务结算被拒绝（租约已过期）",
        cleanup_id=str(intent.id),
        kind=intent.kind.value,
        knowledge_base_id=str(intent.knowledge_base_id),
        attempt=intent.attempt,
        outcome=status.value,
    )
