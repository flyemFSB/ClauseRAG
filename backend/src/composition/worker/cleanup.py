"""Worker 物理清理流水线装配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.cleanup.service import CleanupLane
from composition.shared.stores import open_cleanup_store

if TYPE_CHECKING:
    from application.shared.storage import ObjectStorage
    from application.shared.vectors import VectorIndex
    from infrastructure.config.settings import Settings
    from infrastructure.db.engine import Database


def open_cleanup_lane(
    settings: Settings,
    *,
    database: Database,
    objects: ObjectStorage,
    index: VectorIndex,
) -> CleanupLane:
    """构建清理流水线服务，负责异步执行已提交删除意图的物理清理。"""
    return CleanupLane(
        intents=open_cleanup_store(database),
        objects=objects,
        index=index,
        max_attempts=settings.job_max_attempts,
        retry_backoff_seconds=settings.cleanup_retry_delay_seconds,
        lease_seconds=settings.cleanup_lease_seconds,
    )
