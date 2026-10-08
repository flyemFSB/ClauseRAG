"""异步数据库引擎与会话工厂构建配置。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@dataclass(frozen=True, slots=True)
class Database:
    """进程级数据库引擎与会话工厂封装。"""

    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]

    async def dispose(self) -> None:
        """释放数据库连接池所有连接。"""
        await self.engine.dispose()


def create_database(
    database_url: str,
    *,
    timeout_seconds: int,
    pool_size: int,
    max_overflow: int,
) -> Database:
    """创建配置了连接池心跳与超时限制的异步数据库实例。"""
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=timeout_seconds,
        connect_args={"timeout": timeout_seconds, "command_timeout": timeout_seconds},
    )
    return Database(engine=engine, sessions=async_sessionmaker(engine, expire_on_commit=False))
