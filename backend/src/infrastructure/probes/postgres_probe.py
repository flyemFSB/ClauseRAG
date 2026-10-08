"""PostgreSQL 数据库就绪探针。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from domain.dependency import Dependency


class PostgresProbe:
    """PostgreSQL 连通性探针：建立单次连接并执行 SELECT 1。"""

    def __init__(self, *, database_url: str, timeout_seconds: int) -> None:
        self.dependency = Dependency.POSTGRES
        self._database_url = database_url
        self._timeout_seconds = timeout_seconds

    async def probe(self) -> None:
        """执行探活检查，不可达或超时则抛出异常。"""
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
        finally:
            await engine.dispose()
