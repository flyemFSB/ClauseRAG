"""知识库、文档、版本与摄取任务领域实体。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from uuid import UUID


class DocumentVersionStatus(StrEnum):
    """文档版本状态机枚举"""

    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    READY = "ready"
    PARSE_FAILED = "parse_failed"
    CHUNK_FAILED = "chunk_failed"
    EMBEDDING_FAILED = "embedding_failed"
    INDEX_FAILED = "index_failed"
    MANUAL_RETRY_REQUIRED = "manual_retry_required"


class IngestionStage(StrEnum):
    """文档摄取流水线阶段"""

    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"
    INDEX = "index"


class IngestionJobStatus(StrEnum):
    """摄取任务执行状态"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MANUAL_RETRY_REQUIRED = "manual_retry_required"


@dataclass(frozen=True, slots=True)
class StageFailureState:
    """阶段失败对应的版本状态与任务状态组合"""

    version_status: DocumentVersionStatus
    job_status: IngestionJobStatus


MANUAL_RETRY_STATE: StageFailureState = StageFailureState(
    version_status=DocumentVersionStatus.MANUAL_RETRY_REQUIRED,
    job_status=IngestionJobStatus.MANUAL_RETRY_REQUIRED,
)


@dataclass(frozen=True, slots=True)
class RetrySchedule:
    """阶段重试预算：最多尝试次数、退避基数与退避上限"""

    max_attempts: int
    delay_seconds: float
    max_delay_seconds: float

    def next_attempt_at(self, attempt: int, *, at: datetime) -> datetime | None:
        """计算下一次允许投递的时间，预算用尽时返回 None"""
        if attempt >= self.max_attempts:
            return None
        return at + timedelta(seconds=min(self.delay_seconds * attempt, self.max_delay_seconds))


def running_status_for(stage: IngestionStage) -> DocumentVersionStatus:
    """任务认领时文档版本应进入的运行中状态"""
    match stage:
        case IngestionStage.PARSE:
            return DocumentVersionStatus.PARSING
        case IngestionStage.CHUNK:
            return DocumentVersionStatus.CHUNKING
        case IngestionStage.EMBED:
            return DocumentVersionStatus.EMBEDDING
        case IngestionStage.INDEX:
            return DocumentVersionStatus.INDEXING
        case _:
            raise RuntimeError(f"阶段 {stage.value} 未定义对应的运行中状态")


def failure_status_for(stage: IngestionStage) -> DocumentVersionStatus:
    """阶段尝试终结时文档版本应进入的失败状态"""
    match stage:
        case IngestionStage.PARSE:
            return DocumentVersionStatus.PARSE_FAILED
        case IngestionStage.CHUNK:
            return DocumentVersionStatus.CHUNK_FAILED
        case IngestionStage.EMBED:
            return DocumentVersionStatus.EMBEDDING_FAILED
        case IngestionStage.INDEX:
            return DocumentVersionStatus.INDEX_FAILED
        case _:
            raise RuntimeError(f"阶段 {stage.value} 未定义对应的失败状态")


class KnowledgeNotFoundError(Exception):
    """知识库相关资源未找到或无权访问"""

    def __init__(self, resource: str, identifier: UUID) -> None:
        super().__init__(f"资源 {resource} (ID: {identifier}) 不存在或不可用")
        self.resource = resource
        self.identifier = identifier


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    """知识库领域实体"""

    id: UUID
    owner_id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Document:
    """逻辑文档实体"""

    id: UUID
    knowledge_base_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    """文档物理版本实体"""

    id: UUID
    document_id: UUID
    version_ordinal: int
    status: DocumentVersionStatus
    mime_type: str
    checksum: str
    size_bytes: int
    source_object_key: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class IngestionJob:
    """文档摄取阶段任务实体"""

    id: UUID
    document_version_id: UUID
    stage: IngestionStage
    status: IngestionJobStatus
    revision: int
    attempt: int
    error_class: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    """文档列表概览（文档基础信息与最新版本）"""

    document: Document
    latest_version: DocumentVersion | None


@dataclass(frozen=True, slots=True)
class DocumentDetail:
    """文档完整详情（包含所有历史版本）"""

    document: Document
    versions: Sequence[DocumentVersion]


@dataclass(frozen=True, slots=True)
class DocumentUpload:
    """文档上传结果组合对象"""

    document: Document
    version: DocumentVersion
    job: IngestionJob
