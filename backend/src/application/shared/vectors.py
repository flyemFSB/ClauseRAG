"""向量索引存储接口协议与异常定义。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from domain.embedding import VectorPoint
    from domain.retrieval import ChannelMatch


class VectorIndexError(RuntimeError):
    """向量索引存储操作异常"""


class VectorIndexRejectedError(VectorIndexError):
    """向量索引服务明确拒绝操作异常（参数不合法或架构不匹配）"""


class VectorIndex(Protocol):
    """业务稠密向量索引接口协议"""

    async def ensure_ready(self) -> None:
        """确保目标向量集合及载荷索引已就绪（幂等创建）"""
        ...

    async def upsert(self, points: Sequence[VectorPoint]) -> None:
        """批量插入或更新向量点"""
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
        """精确统计指定版本在向量库中的点总数"""
        ...

    async def delete_versions(self, document_version_ids: Sequence[UUID]) -> None:
        """按文档版本 ID 批量删除所有关联的向量点"""
        ...

    async def delete_knowledge_base(self, knowledge_base_id: UUID) -> None:
        """按知识库 ID 范围删除集合内的所有向量点"""
        ...

    async def close(self) -> None:
        """释放底层网络连接资源"""
        ...
