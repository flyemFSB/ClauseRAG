"""关键字检索通道适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.retrieval import ChannelName

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from application.retrieval.chunks import ChunkStore
    from domain.retrieval import ChannelMatch


class KeywordChannel:
    """关键字检索通道：基于 PostgreSQL pg_search 的 BM25 索引执行词项检索。"""

    channel = ChannelName.KEYWORD

    def __init__(self, *, chunks: ChunkStore) -> None:
        self._chunks = chunks

    async def search(
        self,
        *,
        knowledge_base_id: UUID,
        query: str,
        limit: int,
    ) -> Sequence[ChannelMatch]:
        """按 BM25 相关性在就绪文档中检索切片。"""
        return await self._chunks.keyword_search(
            knowledge_base_id=knowledge_base_id,
            query=query,
            limit=limit,
        )
