"""单路检索渠道抽象接口协议。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from domain.retrieval import ChannelMatch, ChannelName


class RetrievalChannel(Protocol):
    """候选块召回渠道接口协议"""

    channel: ChannelName

    async def search(
        self,
        *,
        knowledge_base_id: UUID,
        query: str,
        limit: int,
    ) -> Sequence[ChannelMatch]:
        """在知识库范围内检索匹配块列表"""
        ...
