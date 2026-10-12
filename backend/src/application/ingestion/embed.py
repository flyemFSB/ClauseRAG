"""文档向量化阶段：批量调用 Embedding 服务并将向量写入向量数据库。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from application.ingestion.failures import record_stage_failure
from application.ingestion.store import StageWrite
from application.shared.vectors import VectorIndexError, VectorIndexRejectedError
from domain.embedding import (
    EMBEDDING_FAILED_STATE,
    EmbeddedVersion,
    EmbeddingClaim,
    EmbeddingError,
    EmbeddingProviderError,
    EmbeddingTarget,
    EmbeddingWriteGuard,
    TransientEmbeddingError,
    UnembeddableChunksError,
    embedding_failure_state_for,
    plan_points,
)
from domain.knowledge import IngestionStage, KnowledgeNotFoundError

if TYPE_CHECKING:
    from uuid import UUID

    from application.ingestion.store import IngestionStore
    from application.shared.providers import EmbeddingProvider
    from application.shared.vectors import VectorIndex
    from domain.chunks.model import ChildChunk
    from domain.knowledge import IngestionJob

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EmbedOutcome:
    """向量化阶段输出结果：写入统计及后续索引门控任务。"""

    embedded: EmbeddedVersion
    next_job: IngestionJob | None


class EmbedDocumentVersion:
    """执行单个文档版本的向量化阶段任务。"""

    def __init__(
        self,
        *,
        documents: IngestionStore,
        provider: EmbeddingProvider,
        index: VectorIndex,
        batch_size: int,
        embed_timeout_seconds: int,
    ) -> None:
        self._documents = documents
        self._provider = provider
        self._index = index
        self._batch_size = batch_size
        self._embed_timeout_seconds = embed_timeout_seconds

    async def run(self, version_id: UUID) -> EmbedOutcome:
        """运维路径执行单次向量化，失败直接抛出归类异常。"""
        target = await self._documents.begin_embed(version_id, at=datetime.now(UTC))
        if target is None:
            raise KnowledgeNotFoundError("document_version", version_id)
        return await self.attempt(target)

    async def attempt(self, claim: EmbeddingClaim) -> EmbedOutcome:
        """执行已认领的向量化任务尝试，并在事务中记录结果。"""
        try:
            return await self._embed_and_store(claim)
        except EmbeddingError as error:
            await self._record(
                claim,
                error,
                retryable=isinstance(error, TransientEmbeddingError),
            )
            raise
        except VectorIndexError as error:
            failure = self._index_failure(error)
            await self._record(
                claim,
                failure,
                retryable=isinstance(failure, TransientEmbeddingError),
            )
            raise failure from error
        except TimeoutError as error:
            failure = TransientEmbeddingError(
                f"the embed stage exceeded {self._embed_timeout_seconds} s"
            )
            await self._record(claim, failure, retryable=True)
            raise failure from error
        except Exception as error:
            await record_stage_failure(
                self._documents,
                stage=IngestionStage.EMBED,
                claim=claim,
                error=error,
                retryable=False,
                state=EMBEDDING_FAILED_STATE,
            )
            raise

    async def _record(
        self,
        claim: EmbeddingClaim,
        error: EmbeddingError,
        *,
        retryable: bool,
    ) -> None:
        await record_stage_failure(
            self._documents,
            stage=IngestionStage.EMBED,
            claim=claim,
            error=error,
            retryable=retryable,
            state=embedding_failure_state_for(error),
        )

    @staticmethod
    def _index_failure(error: VectorIndexError) -> EmbeddingError:
        if isinstance(error, VectorIndexRejectedError):
            return EmbeddingProviderError(
                f"the vector index refused the write during the embed stage: {error}"
            )
        return TransientEmbeddingError(
            f"the vector index could not be written during the embed stage: {error}"
        )

    async def _embed_and_store(self, claim: EmbeddingClaim) -> EmbedOutcome:
        """分批计算子块向量并写入向量索引，最后落库事务状态。"""
        target = claim.target
        version_id = target.document_version_id
        if not target.children:
            raise UnembeddableChunksError(
                f"document version {version_id} has no child chunk to embed"
            )
        guard = EmbeddingWriteGuard(
            document_version_id=version_id,
            job_id=claim.job_id,
            attempt=claim.attempt,
        )
        batches = _batches(target, self._batch_size)
        async with asyncio.timeout(self._embed_timeout_seconds):
            await self._index.ensure_ready()
            for batch in batches:
                vectors = await self._provider.embed([child.content for child in batch])
                points = plan_points(batch, vectors)
                await self._index.upsert(points, guard=guard)
        completion = await self._documents.complete_embed(
            version_id,
            job_id=claim.job_id,
            attempt=claim.attempt,
            at=datetime.now(UTC),
        )
        if completion.write is StageWrite.VANISHED:
            # 向量随子块级联删除，无需额外清理。
            log.warning("向量化阶段版本记录已删除", document_version_id=str(version_id))
        elif completion.write is StageWrite.SUPERSEDED:
            log.warning(
                "向量化任务尝试被取代",
                document_version_id=str(version_id),
                job_id=str(claim.job_id),
            )
        embedded = EmbeddedVersion(
            document_version_id=version_id,
            child_count=len(target.children),
            model=self._provider.model,
            dimension=self._provider.dimension,
            batch_count=len(batches),
        )
        log.info(
            "向量化阶段执行完成",
            document_version_id=str(version_id),
            child_count=embedded.child_count,
            batch_count=embedded.batch_count,
            model=embedded.model,
            dimension=embedded.dimension,
        )
        return EmbedOutcome(embedded=embedded, next_job=completion.next_job)


def _batches(target: EmbeddingTarget, batch_size: int) -> tuple[tuple[ChildChunk, ...], ...]:
    children = target.children
    return tuple(
        tuple(children[start : start + batch_size]) for start in range(0, len(children), batch_size)
    )
