"""向量索引存储接口协议与异常定义。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from domain.embedding import EmbeddingWriteGuard, VectorPoint
    from domain.retrieval import ChannelMatch


class VectorIndexError(RuntimeError):
    """向量索引存储操作异常"""


class VectorIndexRejectedError(VectorIndexError):
    """向量索引服务明确拒绝操作异常（参数不合法或架构不匹配）"""


class VectorIndex(Protocol):
    """业务稠密向量索引接口协议。"""

    async def ensure_ready(self) -> None:
        """校验向量表、维度契约与近似最近邻索引可用（只读，不执行 DDL）"""
        ...

    async def upsert(self, points: Sequence[VectorPoint], *, guard: EmbeddingWriteGuard) -> None:
        """在写入门控仍然有效时批量插入或更新子块向量"""
        ...

    async def search_dense(
        self,
        *,
        vector: Sequence[float],
        knowledge_base_id: UUID,
        limit: int,
    ) -> Sequence[ChannelMatch]:
        """在指定知识库范围内检索最相近的向量点"""
        ...

    async def count_for_version(self, document_version_id: UUID) -> int:
        """精确统计指定版本当前模型下的有效向量数"""
        ...

    async def delete_versions(self, document_version_ids: Sequence[UUID]) -> None:
        """按文档版本 ID 批量删除所有关联的向量点"""
        ...

    async def delete_knowledge_base(self, knowledge_base_id: UUID) -> None:
        """按知识库 ID 范围删除所有关联的向量点"""
        ...
