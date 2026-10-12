"""PostgreSQL 数据库就绪探针（含检索扩展与索引校验）。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from domain.dependency import Dependency
from infrastructure.db.models.chunks import (
    CHILD_CHUNKS_BM25_INDEX,
    EMBEDDINGS_HNSW_INDEX,
    EMBEDDINGS_TABLE,
)

# 检索依赖的扩展、数据表与索引校验查询。
_RETRIEVAL_SCHEMA = text(
    """
    SELECT
        (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS vector_version,
        (SELECT extversion FROM pg_extension WHERE extname = 'pg_search') AS pg_search_version,
        to_regclass(:embeddings_table) IS NOT NULL AS has_embeddings,
        to_regclass(:hnsw_index) IS NOT NULL AS has_hnsw,
        to_regclass(:bm25_index) IS NOT NULL AS has_bm25
    """
)
_RETRIEVAL_SCHEMA_PARAMS = {
    "embeddings_table": EMBEDDINGS_TABLE,
    "hnsw_index": EMBEDDINGS_HNSW_INDEX,
    "bm25_index": CHILD_CHUNKS_BM25_INDEX,
}


class PostgresProbe:
    """PostgreSQL 就绪探针：连接可用，且检索扩展、向量表与两类检索索引均已就位。"""

    def __init__(self, *, database_url: str, timeout_seconds: int) -> None:
        self.dependency = Dependency.POSTGRES
        self._database_url = database_url
        self._timeout_seconds = timeout_seconds

    async def probe(self) -> None:
        """执行探活检查，不可达、超时或检索架构缺失则抛出异常。"""
        engine = create_async_engine(
            self._database_url,
            poolclass=NullPool,
            connect_args={
                "timeout": self._timeout_seconds,
                "command_timeout": self._timeout_seconds,
            },
        )
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                row = (await connection.execute(_RETRIEVAL_SCHEMA, _RETRIEVAL_SCHEMA_PARAMS)).one()
        finally:
            await engine.dispose()
        missing = [
            label
            for label, present in (
                ("vector 扩展", row.vector_version is not None),
                ("pg_search 扩展", row.pg_search_version is not None),
                (f"{EMBEDDINGS_TABLE} 表", row.has_embeddings),
                ("HNSW 向量索引", row.has_hnsw),
                ("BM25 关键词索引", row.has_bm25),
            )
            if not present
        ]
        if missing:
            raise RuntimeError("检索架构尚未就绪，缺少: " + "、".join(missing))
