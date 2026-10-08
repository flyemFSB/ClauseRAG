"""分块阶段异常定义与失败状态映射。"""

from __future__ import annotations

from domain.knowledge import (
    MANUAL_RETRY_STATE,
    DocumentVersionStatus,
    IngestionJobStatus,
    StageFailureState,
)


class ChunkError(Exception):
    """分块处理基础异常"""


class UnchunkableDocumentError(ChunkError):
    """文档缺失解析 Markdown 产物无法分块（需人工介入）"""


class TransientChunkError(ChunkError):
    """分块过程瞬时网络或存储超时错误（可自动重试）"""


CHUNK_FAILED_STATE: StageFailureState = StageFailureState(
    version_status=DocumentVersionStatus.CHUNK_FAILED,
    job_status=IngestionJobStatus.FAILED,
)


def failure_state_for(error: ChunkError) -> StageFailureState:
    """根据分块异常计算对应的失败终态"""
    if isinstance(error, UnchunkableDocumentError):
        return MANUAL_RETRY_STATE
    return CHUNK_FAILED_STATE
