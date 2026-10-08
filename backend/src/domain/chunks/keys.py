"""分块 UUID 确定性派生与对象存储键命名规则。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, UUID, uuid5

if TYPE_CHECKING:
    from domain.chunks.model import ChunkKind

_CHUNK_ID_NAMESPACE: UUID = uuid5(NAMESPACE_URL, "rag-platform/chunk")


def chunk_id(document_version_id: UUID, kind: ChunkKind, ordinal: int) -> UUID:
    """根据版本 ID、层级类型与全局序号派生确定性的 UUID5"""
    return uuid5(_CHUNK_ID_NAMESPACE, f"{document_version_id}:{kind.value}:{ordinal}")


def chunks_object_key(document_version_id: UUID, job_id: UUID, attempt: int) -> str:
    """生成分块产物 JSONL 在对象存储中的键"""
    return f"chunks/{document_version_id}/{job_id}/attempt-{attempt}/chunks.jsonl"
