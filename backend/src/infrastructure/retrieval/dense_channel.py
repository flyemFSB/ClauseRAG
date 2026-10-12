"""向量稠密检索通道适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.retrieval import ChannelName

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from application.shared.providers import EmbeddingProvider
    from application.shared.vectors import VectorIndex
    from domain.retrieval import ChannelMatch


class DenseChannel:
    """稠密向量检索通道：先向量化查询，再基于知识库过滤检索最近邻子块。"""

    channel = ChannelName.DENSE

    def __init__(self, *, provider: EmbeddingProvider, index: VectorIndex) -> None:
        self._provider = provider
        self._index = index

    async def search(
        self,
        *,
        knowledge_base_id: UUID,
        query: str,
        limit: int,
    ) -> Sequence[ChannelMatch]:
        """将用户查询转化为向量并检索相似切片。"""
        if limit <= 0 or not query.strip():
            return ()
        vectors = await self._provider.embed([query])
        if not vectors:
            return ()
        return await self._index.search_dense(
            vector=vectors[0],
            knowledge_base_id=knowledge_base_id,
            limit=limit,
        )
