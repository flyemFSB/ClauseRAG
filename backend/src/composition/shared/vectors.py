"""业务稠密向量索引装配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrastructure.retrieval.pgvector_index import PgVectorChildChunkIndex

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings
    from infrastructure.db.engine import Database


def open_vector_index(settings: Settings, *, database: Database) -> PgVectorChildChunkIndex:
    """构建共用业务数据库会话的 pgvector 索引适配器实例。"""
    return PgVectorChildChunkIndex(
        sessions=database.sessions,
        dimension=settings.embedding_dimension,
        model=settings.embedding_model,
        ef_search=settings.hnsw_ef_search,
        iterative_scan=settings.hnsw_iterative_scan,
        max_scan_tuples=settings.hnsw_max_scan_tuples,
    )
