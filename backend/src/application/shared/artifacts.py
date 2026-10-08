"""已废弃关联存储产物清理。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from application.shared.storage import ObjectStorageError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from application.shared.storage import ObjectStorage

log = structlog.get_logger(__name__)


async def delete_artifacts(
    objects: ObjectStorage,
    keys: Sequence[str],
    *,
    resource: str,
    resource_id: UUID,
    reason: str,
) -> None:
    """批量删除指定的存储对象，失败时仅记录告警日志而不中断流程"""
    for key in keys:
        try:
            await objects.delete(key)
        except ObjectStorageError as error:
            log.warning(
                "存储产物对象删除失败",
                object_key=key,
                resource=resource,
                resource_id=str(resource_id),
                reason=reason,
                error=str(error),
            )
