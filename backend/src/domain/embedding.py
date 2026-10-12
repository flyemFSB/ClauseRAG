"""向量嵌入与索引构建领域模型与异常定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.knowledge import (
    MANUAL_RETRY_STATE,
    DocumentVersionStatus,
    IngestionJobStatus,
    StageFailureState,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from domain.chunks.model import ChildChunk


@dataclass(frozen=True, slots=True)
class VectorPoint:
    """待写入向量索引的单条子块向量。"""

    child_id: UUID
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingWriteGuard:
    """基于版本、作业及尝试代次的向量写入门控。"""

    document_version_id: UUID
    job_id: UUID
    attempt: int


@dataclass(frozen=True, slots=True)
class EmbeddingTarget:
    """向量化目标对象，承载当前版本待处理的子分块列表。"""

    document_version_id: UUID
    children: tuple[ChildChunk, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingClaim:
    """Worker 认领的嵌入任务"""

    job_id: UUID
    target: EmbeddingTarget
    attempt: int


@dataclass(frozen=True, slots=True)
class EmbeddedVersion:
    """向量化成功产物元数据"""

    document_version_id: UUID
    child_count: int
    model: str
    dimension: int
    batch_count: int


@dataclass(frozen=True, slots=True)
class IndexTarget:
    """索引校验目标（版本 ID 与期望子块数量）"""

    document_version_id: UUID
    child_count: int


@dataclass(frozen=True, slots=True)
class IndexClaim:
    """Worker 认领的索引校验任务"""

    job_id: UUID
    target: IndexTarget
    attempt: int


@dataclass(frozen=True, slots=True)
class IndexedVersion:
    """索引校验通过确认对象"""

    document_version_id: UUID
    point_count: int
    child_count: int


class EmbeddingError(Exception):
    """向量化处理基础异常"""


class UnembeddableChunksError(EmbeddingError):
    """缺少可向量化的子块数据（需人工介入）"""


class EmbeddingProviderError(EmbeddingError):
    """向量化模型服务异常（鉴权失败、配额超限或向量维度不匹配）"""


class TransientEmbeddingError(EmbeddingError):
    """向量化网络或瞬时超时异常（可自动重试）"""


class IndexingError(Exception):
    """索引阶段基础异常"""


class UnindexableVersionError(IndexingError):
    """版本不可索引异常（需人工介入）"""


class VectorCountMismatchError(IndexingError):
    """向量点数量与数据库子块记录数不一致"""


class IndexRejectedError(IndexingError):
    """向量数据库拒绝操作异常"""


class TransientIndexingError(IndexingError):
    """向量数据库瞬时网络异常（可自动重试）"""


EMBEDDING_FAILED_STATE: StageFailureState = StageFailureState(
    version_status=DocumentVersionStatus.EMBEDDING_FAILED,
    job_status=IngestionJobStatus.FAILED,
)
INDEX_FAILED_STATE: StageFailureState = StageFailureState(
    version_status=DocumentVersionStatus.INDEX_FAILED,
    job_status=IngestionJobStatus.FAILED,
)


def embedding_failure_state_for(error: EmbeddingError) -> StageFailureState:
    """根据嵌入异常类型返回对应的失败终态"""
    if isinstance(error, UnembeddableChunksError):
        return MANUAL_RETRY_STATE
    return EMBEDDING_FAILED_STATE


def indexing_failure_state_for(error: IndexingError) -> StageFailureState:
    """根据索引异常类型返回对应的失败终态"""
    if isinstance(error, UnindexableVersionError):
        return MANUAL_RETRY_STATE
    return INDEX_FAILED_STATE


def plan_points(
    children: Sequence[ChildChunk],
    vectors: Sequence[Sequence[float]],
) -> tuple[VectorPoint, ...]:
    """将子块与对应的特征向量组装为待写入的向量集合"""
    if len(vectors) != len(children):
        raise EmbeddingProviderError(
            f"the provider returned {len(vectors)} vectors for {len(children)} texts"
        )
    return tuple(
        VectorPoint(child_id=child.child_id, vector=tuple(vector))
        for child, vector in zip(children, vectors, strict=True)
    )
