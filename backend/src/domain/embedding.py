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
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from domain.chunks.model import ChildChunk

PAYLOAD_FIELDS: tuple[str, ...] = (
    "child_id",
    "parent_id",
    "document_id",
    "document_version_id",
    "knowledge_base_id",
    "heading_path",
    "block_type",
    "ordinal",
    "line_start",
    "line_end",
    "text",
)

INDEXED_PAYLOAD_FIELDS: tuple[str, ...] = (
    "knowledge_base_id",
    "document_version_id",
    "document_id",
    "parent_id",
    "block_type",
)


def child_payload(
    child: ChildChunk,
    *,
    knowledge_base_id: UUID,
    document_id: UUID,
) -> dict[str, object]:
    """构建子块写入向量数据库的 Payload 字典"""
    return {
        "child_id": str(child.child_id),
        "parent_id": str(child.parent_id),
        "document_id": str(document_id),
        "document_version_id": str(child.document_version_id),
        "knowledge_base_id": str(knowledge_base_id),
        "heading_path": list(child.heading_path),
        "block_type": child.block_type.value,
        "ordinal": child.ordinal,
        "line_start": child.line_start,
        "line_end": child.line_end,
        "text": child.content,
    }


@dataclass(frozen=True, slots=True)
class VectorPoint:
    """向量数据库单点记录（点 ID 与子块 ID 一致）"""

    point_id: UUID
    payload: Mapping[str, object]
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingTarget:
    """向量化目标对象（包含该版本下所有待嵌入子块）"""

    document_version_id: UUID
    knowledge_base_id: UUID
    document_id: UUID
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
    *,
    knowledge_base_id: UUID,
    document_id: UUID,
) -> tuple[VectorPoint, ...]:
    """将子块与对应的特征向量组装为向量数据点集合"""
    if len(vectors) != len(children):
        raise EmbeddingProviderError(
            f"the provider returned {len(vectors)} vectors for {len(children)} texts"
        )
    return tuple(
        VectorPoint(
            point_id=child.child_id,
            payload=child_payload(
                child,
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
            ),
            vector=tuple(vector),
        )
        for child, vector in zip(children, vectors, strict=True)
    )
