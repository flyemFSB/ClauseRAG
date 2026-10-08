"""Worker 运行时组合装配：消息队列消费、摄取流水线与物理清理。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from application.ingestion.dispatch import IngestionDispatch
from composition.shared.database import open_database
from composition.shared.object_storage import open_object_storage
from composition.shared.parsers import open_parsers
from composition.shared.providers import open_embedding_provider
from composition.shared.qdrant import open_vector_index
from composition.shared.queue import open_job_queue
from composition.shared.stores import open_ingestion_store
from composition.shared.tracing import open_tracing
from composition.worker.cleanup import open_cleanup_lane
from composition.worker.ingestion import open_ingestion
from infrastructure.config.settings import load_settings

if TYPE_CHECKING:
    from uuid import UUID

    from application.cleanup.service import CleanupLane
    from application.ingestion.document_ingestion import DocumentIngestion
    from domain.knowledge import IngestionJob, IngestionStage
    from infrastructure.config.settings import Settings
    from infrastructure.db.engine import Database
    from infrastructure.observability.langfuse_tracing import Tracing
    from infrastructure.providers.siliconflow_embeddings import SiliconFlowEmbeddingProvider
    from infrastructure.queue.job_queue import IngestionJobQueue, StageRunner
    from infrastructure.retrieval.qdrant_index import QdrantChildChunkIndex


@dataclass(frozen=True, slots=True)
class WorkerRuntime:
    """Worker 运行时容器持有的全部生命周期托管组件。"""

    settings: Settings
    ingestion: DocumentIngestion
    dispatch: IngestionDispatch
    cleanup: CleanupLane
    job_queue: IngestionJobQueue
    database: Database
    vector_index: QdrantChildChunkIndex
    tracing: Tracing
    embedding: SiliconFlowEmbeddingProvider

    async def close(self) -> None:
        """依序释放向量索引、模型适配器、追踪导出器与数据库连接池。"""
        await self.vector_index.close()
        await self.embedding.close()
        self.tracing.shutdown()
        await self.database.dispose()


def build_worker_runtime() -> WorkerRuntime:
    """加载配置并装配 Worker 运行时各层依赖。"""
    settings = load_settings()
    database = open_database(settings, pool_size=settings.worker_database_pool_size)
    tracing = open_tracing(settings)
    vector_index = open_vector_index(settings)
    embedding = open_embedding_provider(settings)
    queue = open_job_queue(settings, tracing)
    objects = open_object_storage(settings)
    ingestion = open_ingestion(
        settings,
        database=database,
        objects=objects,
        index=vector_index,
        parsers=open_parsers(settings),
        embedding=embedding,
    )
    queue.supply_stage_runner(_stage_runner(ingestion))
    return WorkerRuntime(
        settings=settings,
        ingestion=ingestion,
        dispatch=IngestionDispatch(
            documents=open_ingestion_store(database, settings),
            dispatcher=queue,
            republish_seconds=settings.job_republish_seconds,
        ),
        cleanup=open_cleanup_lane(
            settings,
            database=database,
            objects=objects,
            index=vector_index,
        ),
        job_queue=queue,
        database=database,
        vector_index=vector_index,
        tracing=tracing,
        embedding=embedding,
    )


def _stage_runner(ingestion: DocumentIngestion) -> StageRunner:
    async def run(
        stage: IngestionStage,
        document_version_id: UUID,
        job_id: UUID,
    ) -> IngestionJob | None:
        result = await ingestion.run_stage(
            stage=stage,
            document_version_id=document_version_id,
            job_id=job_id,
        )
        return result.next_job

    return run
