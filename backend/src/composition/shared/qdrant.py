"""Qdrant 业务向量索引客户端装配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrastructure.retrieval.qdrant_index import QdrantChildChunkIndex

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings


def open_vector_index(settings: Settings) -> QdrantChildChunkIndex:
    """构建用于存储文档切片向量的 Qdrant 索引客户端实例。"""
    return QdrantChildChunkIndex(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        collection=settings.qdrant_collection,
        dimension=settings.embedding_dimension,
        timeout_seconds=settings.qdrant_timeout_seconds,
    )
