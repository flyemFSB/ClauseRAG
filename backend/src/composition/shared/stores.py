"""PostgreSQL 各领域仓储实例工厂。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.knowledge import RetrySchedule
from infrastructure.db.stores.chunk_store import SqlAlchemyChunkStore
from infrastructure.db.stores.cleanup_store import SqlAlchemyCleanupStore
from infrastructure.db.stores.document_store import SqlAlchemyDocumentStore
from infrastructure.db.stores.knowledge_base_store import SqlAlchemyKnowledgeBaseStore
from infrastructure.ingestion.store import SqlAlchemyIngestionStore

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings
    from infrastructure.db.engine import Database


def open_cleanup_store(database: Database) -> SqlAlchemyCleanupStore:
    """构建清理意图持久化仓储。"""
    return SqlAlchemyCleanupStore(database.sessions)


def open_document_store(database: Database) -> SqlAlchemyDocumentStore:
    """构建文档与版本元数据仓储。"""
    return SqlAlchemyDocumentStore(database.sessions)


def open_chunk_store(database: Database) -> SqlAlchemyChunkStore:
    """构建文档切片持久化仓储。"""
    return SqlAlchemyChunkStore(database.sessions)


def open_ingestion_store(database: Database, settings: Settings) -> SqlAlchemyIngestionStore:
    """构建摄取任务与阶段流转持久化仓储。"""
    return SqlAlchemyIngestionStore(
        database.sessions,
        open_chunk_store(database),
        retry=RetrySchedule(
            max_attempts=settings.job_max_attempts,
            delay_seconds=settings.job_retry_delay_seconds,
            max_delay_seconds=settings.job_retry_max_delay_seconds,
        ),
        lease_seconds=settings.job_stale_after_seconds,
    )


def open_knowledge_bases(database: Database) -> SqlAlchemyKnowledgeBaseStore:
    """构建知识库持久化仓储。"""
    return SqlAlchemyKnowledgeBaseStore(database.sessions)
