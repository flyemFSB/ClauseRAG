"""基于 ORM 模型定义幂等建立或清空业务数据库表结构。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import inspect, text

from infrastructure.db.models import Base

if TYPE_CHECKING:
    from sqlalchemy import Connection
    from sqlalchemy.ext.asyncio import AsyncEngine

_CREATE_EXTENSIONS = (
    # 显式建立 vector 与 pg_search 检索扩展。
    text("CREATE EXTENSION IF NOT EXISTS vector"),
    text("CREATE EXTENSION IF NOT EXISTS pg_search CASCADE"),
)


class SchemaBootstrap:
    """业务 schema 的建立与清空。"""

    def __init__(self, *, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self) -> tuple[str, ...]:
        """幂等建立扩展与缺失的表，返回本次新建的表名。"""
        async with self._engine.begin() as connection:
            for statement in _CREATE_EXTENSIONS:
                await connection.execute(statement)
            existing = await connection.run_sync(_table_names)
            await connection.run_sync(Base.metadata.create_all)
        return _missing_before(existing)

    async def reset(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """删除全部业务表后重建，返回 (被删除的表, 新建的表)。"""
        async with self._engine.begin() as connection:
            existing = await connection.run_sync(_table_names)
            await connection.run_sync(Base.metadata.drop_all)
        return _present_before(existing), await self.create()


def _table_names(connection: Connection) -> frozenset[str]:
    return frozenset(inspect(connection).get_table_names())


def _declared() -> frozenset[str]:
    return frozenset(Base.metadata.tables)


def _missing_before(existing: frozenset[str]) -> tuple[str, ...]:
    return tuple(sorted(_declared() - existing))


def _present_before(existing: frozenset[str]) -> tuple[str, ...]:
    return tuple(sorted(_declared() & existing))
