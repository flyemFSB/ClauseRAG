"""Qdrant 向量数据库就绪探针。"""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient

from domain.dependency import Dependency


class QdrantProbe:
    """Qdrant 连通性探针：调用 get_collections 检查服务可用性。"""

    def __init__(self, *, qdrant_url: str, api_key: str | None, timeout_seconds: int) -> None:
        self.dependency = Dependency.QDRANT
        self._qdrant_url = qdrant_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def probe(self) -> None:
        """执行探活检查，不可达或鉴权失败则抛出异常。"""
        client = AsyncQdrantClient(
            url=self._qdrant_url,
            api_key=self._api_key,
            timeout=self._timeout_seconds,
            check_compatibility=False,
        )
        try:
            await client.get_collections()
        finally:
            await client.close()
