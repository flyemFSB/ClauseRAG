"""CLI 命令行运行时工厂：按命令族按需组装轻量级依赖容器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from composition.shared.database import open_database
from composition.shared.object_storage import open_object_storage
from composition.shared.parsers import open_parsers
from composition.shared.providers import open_chat, open_embedding_provider
from composition.shared.vectors import open_vector_index
from composition.worker.cleanup import open_cleanup_lane
from composition.worker.ingestion import open_ingestion
from domain.knowledge import IngestionStage
from infrastructure.config.settings import load_settings
from infrastructure.db.schema import SchemaBootstrap
from infrastructure.storage.s3_bucket import S3BucketInitializer

if TYPE_CHECKING:
    from application.cleanup.service import CleanupLane
    from application.ingestion.document_ingestion import DocumentIngestion
    from infrastructure.config.settings import Settings
    from infrastructure.db.engine import Database
    from infrastructure.providers.siliconflow_chat import SiliconFlowChat
    from infrastructure.providers.siliconflow_embeddings import SiliconFlowEmbeddingProvider
    from infrastructure.retrieval.pgvector_index import PgVectorChildChunkIndex

RUNNABLE_STAGES: tuple[IngestionStage, ...] = (
    IngestionStage.PARSE,
    IngestionStage.CHUNK,
    IngestionStage.EMBED,
    IngestionStage.INDEX,
)


@dataclass(frozen=True, slots=True)
class StageRuntime:
    """摄取单步执行命令运行时。"""

    settings: Settings
    database: Database
    ingestion: DocumentIngestion
    vector_index: PgVectorChildChunkIndex | None = None
    embedding: SiliconFlowEmbeddingProvider | None = None
    chat: SiliconFlowChat | None = None

    async def close(self) -> None:
        if self.embedding is not None:
            await self.embedding.close()
        if self.chat is not None:
            await self.chat.close()
        await self.database.dispose()


@dataclass(frozen=True, slots=True)
class StorageRuntime:
    """存储桶初始化命令运行时。"""

    settings: Settings
    bucket_initializer: S3BucketInitializer


@dataclass(frozen=True, slots=True)
class SchemaRuntime:
    """业务 schema 建立与清空命令运行时。"""

    settings: Settings
    database: Database
    bootstrap: SchemaBootstrap

    async def close(self) -> None:
        await self.database.dispose()


@dataclass(frozen=True, slots=True)
class CleanupRuntime:
    """物理清理执行命令运行时。"""

    settings: Settings
    database: Database
    lane: CleanupLane
    vector_index: PgVectorChildChunkIndex
    embedding: SiliconFlowEmbeddingProvider
    chat: SiliconFlowChat

    async def close(self) -> None:
        await self.embedding.close()
        await self.chat.close()
        await self.database.dispose()


def _open_database(settings: Settings) -> Database:
    return open_database(settings, pool_size=settings.worker_database_pool_size)


def build_run_stage_runtime(stage: IngestionStage) -> StageRuntime:
    """构建单阶段摄取运行时。"""
    settings = load_settings()
    database = _open_database(settings)
    if stage in (IngestionStage.PARSE, IngestionStage.CHUNK):
        return StageRuntime(
            settings=settings,
            database=database,
            ingestion=open_ingestion(
                settings,
                database=database,
                objects=open_object_storage(settings),
                parsers=open_parsers(settings),
                stages=(stage,),
            ),
        )
    if stage in (IngestionStage.EMBED, IngestionStage.INDEX):
        vector_index = open_vector_index(settings, database=database)
        embedding = open_embedding_provider(settings)
        return StageRuntime(
            settings=settings,
            database=database,
            ingestion=open_ingestion(
                settings,
                database=database,
                index=vector_index,
                embedding=embedding,
                stages=(stage,),
            ),
            vector_index=vector_index,
            embedding=embedding,
        )
    raise RuntimeError(f"the {stage.value} stage is not one the operator path runs")


def build_reindex_runtime() -> StageRuntime:
    """构建重新向量化与索引校验运行时。"""
    settings = load_settings()
    database = _open_database(settings)
    vector_index = open_vector_index(settings, database=database)
    embedding = open_embedding_provider(settings)
    return StageRuntime(
        settings=settings,
        database=database,
        ingestion=open_ingestion(
            settings,
            database=database,
            index=vector_index,
            embedding=embedding,
            stages=(IngestionStage.EMBED, IngestionStage.INDEX),
        ),
        vector_index=vector_index,
        embedding=embedding,
    )


def build_storage_runtime() -> StorageRuntime:
    settings = load_settings()
    return StorageRuntime(
        settings=settings,
        bucket_initializer=S3BucketInitializer(
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key=settings.s3_access_key.get_secret_value(),
            secret_key=settings.s3_secret_key.get_secret_value(),
            bucket=settings.s3_bucket,
            timeout_seconds=settings.health_probe_timeout_seconds,
        ),
    )


def build_schema_runtime() -> SchemaRuntime:
    """构建业务 schema 建立与清空运行时。"""
    settings = load_settings()
    database = _open_database(settings)
    return SchemaRuntime(
        settings=settings,
        database=database,
        bootstrap=SchemaBootstrap(engine=database.engine),
    )


def build_cleanup_runtime() -> CleanupRuntime:
    """构建未决清理流水线运维运行时。"""
    settings = load_settings()
    database = _open_database(settings)
    vector_index = open_vector_index(settings, database=database)
    embedding = open_embedding_provider(settings)
    chat = open_chat(settings)
    return CleanupRuntime(
        settings=settings,
        database=database,
        lane=open_cleanup_lane(
            settings,
            database=database,
            objects=open_object_storage(settings),
            index=vector_index,
        ),
        vector_index=vector_index,
        embedding=embedding,
        chat=chat,
    )
