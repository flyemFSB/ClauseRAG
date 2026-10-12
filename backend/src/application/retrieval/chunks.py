"""检索回表与关键词匹配存储接口协议。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from domain.retrieval import ChannelMatch, ChunkRecord


class ChunkStore(Protocol):
    """子块数据检索与回表存储接口"""

    async def keyword_search(
        self,
        *,
        knowledge_base_id: UUID,
        query: str,
        limit: int,
    ) -> Sequence[ChannelMatch]:
        """在知识库已就绪版本中执行 BM25 词项匹配检索"""
        ...

    async def load_records(
        self,
        *,
        knowledge_base_id: UUID,
        child_ids: Sequence[UUID],
    ) -> Mapping[UUID, ChunkRecord]:
        """批量读取并补全子块的元数据记录（仅返回属于指定知识库且已就绪的块）"""
        ...
