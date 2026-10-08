"""数据库引擎与连接池装配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrastructure.db.engine import Database, create_database

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings


def open_database(settings: Settings, *, pool_size: int) -> Database:
    """按进程角色声明的连接池配额初始化 PostgreSQL 异步数据库引擎。"""
    return create_database(
        settings.database_url.get_secret_value(),
        timeout_seconds=settings.database_timeout_seconds,
        pool_size=pool_size,
        max_overflow=settings.database_max_overflow,
    )
