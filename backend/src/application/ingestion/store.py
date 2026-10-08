"""摄取存储接口与阶段状态转移模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from datetime import datetime, timedelta
    from uuid import UUID

    from domain.chunks.model import ChildChunk, ChunkArtifact, ChunkClaim, ParentChunk
    from domain.embedding import EmbeddingClaim, IndexClaim
    from domain.knowledge import (
        DocumentVersionStatus,
        IngestionJob,
        IngestionStage,
        StageFailureState,
    )
    from domain.parsing import (
        ParseArtifact,
        ParseClaim,
        ParseRetry,
    )


class StageWrite(StrEnum):
    """阶段写入结果状态。"""

    RECORDED = "recorded"
    """认领任务仍有效，写入成功生效。"""

    SUPERSEDED = "superseded"
    """任务已被更新版本取代，本次写入作废。"""

    VANISHED = "vanished"
    """文档版本在运行期间已被删除，写入跳过。"""


class FailureWrite(StrEnum):
    """阶段失败写入结果状态。"""

    RETRY_SCHEDULED = "retry_scheduled"
    """失败可重试且预算未用尽，作业已置回等待中并记录投递时间。"""

    FAILED = "failed"
    """失败不可重试或预算已用尽，作业已写成终态。"""

    SUPERSEDED = "superseded"
    """本次尝试已被接管或取代，失败状态未写入。"""

    VANISHED = "vanished"
    """文档版本在运行期间已被删除，失败状态未写入。"""


@dataclass(frozen=True, slots=True)
class StageCompletion:
    """阶段完成响应：写入状态与后续追加任务。"""

    write: StageWrite
    next_job: IngestionJob | None = None
    replaced_object_key: str | None = None


@dataclass(frozen=True, slots=True)
class LeaseReclamation:
    """租约过期后被接管的尝试及其去向。"""

    job_id: UUID
    document_version_id: UUID
    stage: IngestionStage
    attempt: int
    requeued: bool


class IngestionStore(Protocol):
    """摄取存储仓储协议：管理任务行与阶段流转。"""

    async def start_parse_retry(
        self,
        owner_id: UUID,
        version_id: UUID,
        *,
        retryable_statuses: Collection[DocumentVersionStatus],
        stale_after: timedelta,
        at: datetime,
    ) -> ParseRetry | None:
        """重试指定文档版本的解析阶段。"""
        ...

    async def begin_parse(self, version_id: UUID, *, at: datetime) -> ParseClaim | None:
        """运维路径启动解析尝试：占有租约并把版本与任务置为运行中。"""
        ...

    async def claim_parse_job(
        self,
        version_id: UUID,
        job_id: UUID,
        *,
        at: datetime,
    ) -> ParseClaim | None:
        """队列 Worker 认领排队中的解析任务。"""
        ...

    async def complete_parse(
        self,
        artifact: ParseArtifact,
        *,
        job_id: UUID,
        attempt: int,
        at: datetime,
    ) -> StageCompletion:
        """记录解析成功状态，持久化产物并生成分块任务。"""
        ...

    async def begin_chunk(self, version_id: UUID, *, at: datetime) -> ChunkClaim | None:
        """运维路径启动分块尝试。"""
        ...

    async def claim_chunk_job(
        self,
        version_id: UUID,
        job_id: UUID,
        *,
        at: datetime,
    ) -> ChunkClaim | None:
        """队列 Worker 认领排队中的分块任务。"""
        ...

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
        """记录分块成功状态，替换旧块并生成向量化任务。"""
        ...

    async def begin_embed(self, version_id: UUID, *, at: datetime) -> EmbeddingClaim | None:
        """运维路径启动向量化尝试。"""
        ...

    async def claim_embed_job(
        self,
        version_id: UUID,
        job_id: UUID,
        *,
        at: datetime,
    ) -> EmbeddingClaim | None:
        """队列 Worker 认领排队中的向量化任务。"""
        ...

    async def complete_embed(
        self,
        version_id: UUID,
        *,
        job_id: UUID,
        attempt: int,
        at: datetime,
    ) -> StageCompletion:
        """记录向量化成功状态，生成索引门控校验任务。"""
        ...

    async def begin_index(self, version_id: UUID, *, at: datetime) -> IndexClaim | None:
        """运维路径启动索引门控检查尝试。"""
        ...

    async def claim_index_job(
        self,
        version_id: UUID,
        job_id: UUID,
        *,
        at: datetime,
    ) -> IndexClaim | None:
        """队列 Worker 认领排队中的索引门控检查任务。"""
        ...

    async def complete_index(
        self,
        version_id: UUID,
        *,
        job_id: UUID,
        attempt: int,
        at: datetime,
    ) -> StageCompletion:
        """标记版本就绪 (ready)，索引任务成功。"""
        ...

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
        """按重试预算把失败写成等待重试或终态。"""
        ...

    async def due_jobs(
        self,
        *,
        at: datetime,
        limit: int,
        republish_before: datetime,
    ) -> Sequence[IngestionJob]:
        """读取到点且未在重发窗口内投递过的等待中作业。"""
        ...

    async def mark_dispatched(self, job_ids: Sequence[UUID], *, at: datetime) -> None:
        """记录一批作业最近一次成功投递的时间。"""
        ...

    async def reclaim_expired_leases(
        self,
        *,
        at: datetime,
        limit: int,
    ) -> Sequence[LeaseReclamation]:
        """接管租约已过期的尝试：置回等待中，或用尽预算后写成终态。"""
        ...
