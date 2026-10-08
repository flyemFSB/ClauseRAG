"""异步清理意图领域模型与状态枚举。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID


class CleanupKind(StrEnum):
    """清理对象类型"""

    DOCUMENT = "document"
    """单个文档及其版本与索引"""

    KNOWLEDGE_BASE = "knowledge_base"
    """整个知识库及其所有关联资源"""


class CleanupStatus(StrEnum):
    """清理任务执行状态"""

    PENDING = "pending"
    """待处理（可被 Worker 认领）"""

    RUNNING = "running"
    """执行中（持有租约）"""

    SUCCEEDED = "succeeded"
    """清理完成"""

    FAILED = "failed"
    """重试超限，执行失败"""


LEASE_EXPIRED_ERROR_CLASS = "LeaseExpired"


@dataclass(frozen=True, slots=True)
class CleanupIntent:
    """持久化清理意图记录"""

    id: UUID
    kind: CleanupKind
    status: CleanupStatus
    attempt: int
    knowledge_base_id: UUID
    document_id: UUID | None
    object_keys: tuple[str, ...]
    document_version_ids: tuple[UUID, ...]
    child_ids: tuple[UUID, ...]
    error_class: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
