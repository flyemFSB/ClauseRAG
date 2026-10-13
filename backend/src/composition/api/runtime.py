"""业务 API 运行时组合装配：知识库、文档目录与队列分发。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from application.knowledge.document_catalog import DocumentCatalog
from application.knowledge.knowledge_bases import KnowledgeBaseService
from composition.shared.database import open_database
from composition.shared.health import open_health
from composition.shared.object_storage import open_object_storage
from composition.shared.queue import open_job_queue
from composition.shared.redis import open_rate_limit_guard
from composition.shared.stores import (
    open_document_store,
    open_ingestion_store,
    open_knowledge_bases,
)
from composition.shared.tracing import open_tracing
from infrastructure.config.settings import load_settings
from infrastructure.redis.client import open_client

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from application.shared.health import HealthService
    from application.shared.rate_limit import RateLimitGuard
    from infrastructure.config.settings import Settings
    from infrastructure.db.engine import Database
    from infrastructure.observability.langfuse_tracing import Tracing
    from infrastructure.queue.job_queue import IngestionJobQueue


@dataclass(frozen=True, slots=True)
class ApiRuntime:
    """业务 API 运行时容器持有的全部生命周期托管组件。"""

    settings: Settings
    health: HealthService
    knowledge_bases: KnowledgeBaseService
    catalog: DocumentCatalog
    job_queue: IngestionJobQueue
    rate_limits: RateLimitGuard
    tracing: Tracing
    database: Database
    redis: Redis | None

    async def close(self) -> None:
        """依序释放任务队列连接、追踪导出器、数据库连接池与业务 Redis 客户端。"""
        await self.job_queue.shutdown()
        self.tracing.shutdown()
        await self.database.dispose()
        if self.redis is not None:
            await self.redis.aclose()


def build_api_runtime() -> ApiRuntime:
    """加载配置并装配业务 API 运行时各层依赖。"""
    settings = load_settings()
    database = open_database(settings, pool_size=settings.api_database_pool_size)
    redis = open_client(settings)
    tracing = open_tracing(settings)
    objects = open_object_storage(settings)
    queue = open_job_queue(settings, tracing)
    knowledge_bases_store = open_knowledge_bases(database)
    document_store = open_document_store(database)

    return ApiRuntime(
        settings=settings,
        health=open_health(settings),
        knowledge_bases=KnowledgeBaseService(knowledge_bases=knowledge_bases_store),
        catalog=DocumentCatalog(
            knowledge_bases=knowledge_bases_store,
            documents=document_store,
            ingestion=open_ingestion_store(database, settings),
            objects=objects,
            dispatcher=queue,
            max_upload_bytes=settings.max_upload_bytes,
            job_stale_after=timedelta(seconds=settings.job_stale_after_seconds),
        ),
        job_queue=queue,
        rate_limits=open_rate_limit_guard(settings, redis),
        tracing=tracing,
        database=database,
        redis=redis,
    )
