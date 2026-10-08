"""清理意向数据行到领域实体的转换映射。"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from domain.cleanup import CleanupIntent, CleanupKind, CleanupStatus

if TYPE_CHECKING:
    from infrastructure.db.models.cleanup import CleanupIntentRow


def to_cleanup_intent(row: CleanupIntentRow) -> CleanupIntent:
    """将清理意向数据库行转换为领域实体。"""
    return CleanupIntent(
        id=row.id,
        kind=CleanupKind(row.kind),
        status=CleanupStatus(row.status),
        attempt=row.attempt,
        knowledge_base_id=row.knowledge_base_id,
        document_id=row.document_id,
        object_keys=tuple(row.object_keys),
        document_version_ids=tuple(uuid.UUID(value) for value in row.document_version_ids),
        child_ids=tuple(uuid.UUID(value) for value in row.child_ids),
        error_class=row.error_class,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )
