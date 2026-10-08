"""Alembic environment for the business schema.

The URL comes from ``DATABASE_URL`` and the migrations run on the same async driver the
application uses (``asyncpg``). ``fileConfig`` is deliberately not called, so this project does not
need the logging sections an ``alembic.ini`` based on the stock template carries.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Every mapped table must be imported before the metadata is read, or a migration would compare
# against an incomplete schema. Importing the modules rather than their names says why they are
# here: the mapping is registered by the import itself, and no name from them is used. The
# ``noqa`` is load-bearing: without it an unused-import fix would empty the metadata this reads.
from infrastructure.db.base import Base
from infrastructure.db.models import (  # noqa: F401 - for the mapping side effect
    chunks,
    cleanup,
    conversations,
    documents,
    ingestion,
    knowledge_bases,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    """Read the business database URL from the process environment."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL must be set, for example "
            "postgresql+asyncpg://rag:rag_local@127.0.0.1:5432/rag"
        )
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting, for review of a migration."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure the migration context on an established connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Apply migrations over an async engine and release it afterwards."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=database_url(),
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
