"""基于 SQLAlchemy 实现清理意向仓储（支持级联资源安全清理与状态锁竞争）。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import sqlalchemy as sa

from domain.cleanup import (
    LEASE_EXPIRED_ERROR_CLASS,
    CleanupIntent,
    CleanupKind,
    CleanupStatus,
)
from infrastructure.db.mappers.cleanup import to_cleanup_intent
from infrastructure.db.models.cleanup import CleanupIntentRow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def add_cleanup_intent(
    session: AsyncSession,
    *,
    kind: CleanupKind,
    knowledge_base_id: UUID,
    document_id: UUID | None,
    object_keys: Sequence[str],
    document_version_ids: Sequence[UUID],
    child_ids: Sequence[UUID],
    at: datetime,
) -> None:
    """在当前事务中记录待执行的资源清理意向。"""
    session.add(
        CleanupIntentRow(
            id=uuid4(),
            kind=kind.value,
            status=CleanupStatus.PENDING.value,
            attempt=0,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            object_keys=list(object_keys),
            document_version_ids=[str(version_id) for version_id in document_version_ids],
            child_ids=[str(child_id) for child_id in child_ids],
            error_class=None,
            error_message=None,
            created_at=at,
            updated_at=at,
            started_at=None,
            finished_at=None,
        )
    )


class SqlAlchemyCleanupStore:
    """清理意向仓储 SQLAlchemy 异步实现。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def claim_next(
        self,
        *,
        at: datetime,
        not_before: datetime,
        lease_before: datetime,
        max_attempts: int,
    ) -> CleanupIntent | None:
        """抢占并认领下一个最早待处理或租约过期的清理任务。"""
        async with self._sessions.begin() as session:
            await _expire_abandoned_claims(
                session,
                at=at,
                lease_before=lease_before,
                max_attempts=max_attempts,
            )
            row = await _claim(
                session,
                at=at,
                status=CleanupStatus.RUNNING,
                claimable=CleanupIntentRow.updated_at <= lease_before,
                max_attempts=max_attempts,
            )
            if row is None:
                row = await _claim(
                    session,
                    at=at,
                    status=CleanupStatus.PENDING,
                    claimable=sa.or_(
                        CleanupIntentRow.attempt == 0,
                        CleanupIntentRow.updated_at <= not_before,
                    ),
                    max_attempts=max_attempts,
                )
        return None if row is None else to_cleanup_intent(row)

    async def complete(self, intent_id: UUID, *, attempt: int, at: datetime) -> bool:
        """标记指定尝试的清理任务已执行完成。"""
        return await _settle_attempt(
            self._sessions,
            intent_id,
            attempt=attempt,
            status=CleanupStatus.SUCCEEDED,
            error_class=None,
            error_message=None,
            finished_at=at,
            at=at,
        )

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
        """记录清理任务失败状态或重新排队重试。"""
        return await _settle_attempt(
            self._sessions,
            intent_id,
            attempt=attempt,
            status=status,
            error_class=error_class,
            error_message=error_message,
            finished_at=None if status is CleanupStatus.PENDING else at,
            at=at,
        )


async def _claim(
    session: AsyncSession,
    *,
    at: datetime,
    status: CleanupStatus,
    claimable: sa.ColumnElement[bool],
    max_attempts: int,
) -> CleanupIntentRow | None:
    """执行带 SKIP LOCKED 的条件更新以认领单条清理意向。"""
    candidate = (
        sa.select(CleanupIntentRow.id)
        .where(
            CleanupIntentRow.status == status.value,
            CleanupIntentRow.attempt < max_attempts,
            claimable,
        )
        .order_by(CleanupIntentRow.updated_at, CleanupIntentRow.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .cte("next_intent")
    )
    statement = (
        sa.update(CleanupIntentRow)
        .where(CleanupIntentRow.id == candidate.c.id)
        .values(
            status=CleanupStatus.RUNNING.value,
            attempt=CleanupIntentRow.attempt + 1,
            started_at=at,
            finished_at=None,
            error_class=None,
            error_message=None,
            updated_at=at,
        )
        .returning(CleanupIntentRow)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def _expire_abandoned_claims(
    session: AsyncSession,
    *,
    at: datetime,
    lease_before: datetime,
    max_attempts: int,
) -> None:
    """将超出最大尝试次数且超时的任务标记为最终失败。"""
    await session.execute(
        sa.update(CleanupIntentRow)
        .where(
            CleanupIntentRow.status == CleanupStatus.RUNNING.value,
            CleanupIntentRow.attempt >= max_attempts,
            CleanupIntentRow.updated_at <= lease_before,
        )
        .values(
            status=CleanupStatus.FAILED.value,
            error_class=LEASE_EXPIRED_ERROR_CLASS,
            error_message=(
                f"the claim expired after {max_attempts} attempt(s) with no result; the derived "
                "cleanup is still owed, so the intent has to be re-opened to run it again"
            ),
            finished_at=at,
            updated_at=at,
        )
    )


async def _settle_attempt(
    sessions: async_sessionmaker[AsyncSession],
    intent_id: UUID,
    *,
    attempt: int,
    status: CleanupStatus,
    error_class: str | None,
    error_message: str | None,
    finished_at: datetime | None,
    at: datetime,
) -> bool:
    """条件更新终结指定清理尝试状态。"""
    statement = (
        sa.update(CleanupIntentRow)
        .where(
            CleanupIntentRow.id == intent_id,
            CleanupIntentRow.status == CleanupStatus.RUNNING.value,
            CleanupIntentRow.attempt == attempt,
        )
        .values(
            status=status.value,
            error_class=error_class,
            error_message=error_message,
            finished_at=finished_at,
            updated_at=at,
        )
        .returning(CleanupIntentRow.id)
    )
    async with sessions.begin() as session:
        settled = await session.scalar(statement)
    return settled is not None
