"""LangGraph Postgres 检查点持久化适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,  # pyright: ignore[reportMissingTypeStubs]
)
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

if TYPE_CHECKING:
    from psycopg import AsyncConnection
    from psycopg.rows import DictRow


async def _check_connection(connection: AsyncConnection[DictRow]) -> None:
    """健康检查：验证连接池中的连接是否可用。"""
    await connection.execute("select 1")


class GraphCheckpoints:
    """LangGraph 状态检查点连接池管理与持久化。"""

    def __init__(
        self,
        *,
        pool: AsyncConnectionPool[AsyncConnection[DictRow]],
        saver: AsyncPostgresSaver,
    ) -> None:
        self._pool = pool
        self._saver = saver

    @property
    def saver(self) -> AsyncPostgresSaver:
        """获取底层检查点存储器。"""
        return self._saver

    @classmethod
    async def open(cls, *, dsn: str, max_connections: int) -> GraphCheckpoints:
        """初始化异步连接池并幂等执行检查点表结构初始化。"""
        pool = cast(
            "AsyncConnectionPool[AsyncConnection[DictRow]]",
            AsyncConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=max_connections,
                open=False,
                check=_check_connection,
                # 检查点要求 autocommit 与字典行格式
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                },
            ),
        )
        await pool.open(wait=True)
        # 适配 LangGraph 类型注解差异，注入 dict_row 异步连接池
        saver = AsyncPostgresSaver(conn=pool)  # pyright: ignore[reportArgumentType]
        await saver.setup()
        return cls(pool=pool, saver=saver)

    async def close(self) -> None:
        """关闭连接池并释放数据库连接。"""
        await self._pool.close()
