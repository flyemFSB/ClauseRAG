"""文档索引门控阶段：核对向量索引点数量与子块数量一致性，标记版本就绪。"""

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
    INDEX_FAILED_STATE,
    IndexClaim,
    IndexedVersion,
    IndexingError,
    IndexRejectedError,
    TransientIndexingError,
    UnindexableVersionError,
    VectorCountMismatchError,
    indexing_failure_state_for,
)
from domain.knowledge import IngestionStage, KnowledgeNotFoundError

if TYPE_CHECKING:
    from uuid import UUID

    from application.ingestion.store import IngestionStore
    from application.shared.vectors import VectorIndex

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IndexOutcome:
    """索引门控阶段输出结果：校验统计。"""

    indexed: IndexedVersion


class IndexDocumentVersion:
    """执行单个文档版本的索引门控核验任务。"""

    def __init__(
        self,
        *,
        documents: IngestionStore,
        index: VectorIndex,
        index_timeout_seconds: int,
    ) -> None:
        self._documents = documents
        self._index = index
        self._index_timeout_seconds = index_timeout_seconds

    async def run(self, version_id: UUID) -> IndexOutcome:
        """运维路径执行单次索引门控校验。"""
        target = await self._documents.begin_index(version_id, at=datetime.now(UTC))
        if target is None:
            raise KnowledgeNotFoundError("document_version", version_id)
        return await self.attempt(target)

    async def attempt(self, claim: IndexClaim) -> IndexOutcome:
        """执行已认领的索引门控任务尝试，并在事务中记录结果。"""
        try:
            return await self._verify_and_declare(claim)
        except IndexingError as error:
            await self._record(
                claim,
                error,
                retryable=isinstance(error, TransientIndexingError),
            )
            raise
        except VectorIndexError as error:
            failure = self._index_failure(error)
            await self._record(
                claim,
                failure,
                retryable=isinstance(failure, TransientIndexingError),
            )
            raise failure from error
        except TimeoutError as error:
            failure = TransientIndexingError(
                f"索引门控阶段超时 (超过 {self._index_timeout_seconds} 秒)"
            )
            await self._record(claim, failure, retryable=True)
            raise failure from error
        except Exception as error:
            await record_stage_failure(
                self._documents,
                stage=IngestionStage.INDEX,
                claim=claim,
                error=error,
                retryable=False,
                state=INDEX_FAILED_STATE,
            )
            raise

    async def _record(
        self,
        claim: IndexClaim,
        error: IndexingError,
        *,
        retryable: bool,
    ) -> None:
        await record_stage_failure(
            self._documents,
            stage=IngestionStage.INDEX,
            claim=claim,
            error=error,
            retryable=retryable,
            state=indexing_failure_state_for(error),
        )

    @staticmethod
    def _index_failure(error: VectorIndexError) -> IndexingError:
        if isinstance(error, VectorIndexRejectedError):
            return IndexRejectedError(f"索引门控阶段向量索引拒绝请求: {error}")
        return TransientIndexingError(f"索引门控阶段读取向量索引失败: {error}")

    async def _verify_and_declare(self, claim: IndexClaim) -> IndexOutcome:
        """精确核对向量索引点总数与数据库子块记录数，一致则置为 ready。"""
        target = claim.target
        version_id = target.document_version_id
        if target.child_count == 0:
            raise UnindexableVersionError(f"文档版本 {version_id} 没有可供索引的子文本块")
        async with asyncio.timeout(self._index_timeout_seconds):
            await self._index.ensure_ready()
            point_count = await self._index.count_for_version(version_id)
        if point_count != target.child_count:
            raise VectorCountMismatchError(
                f"文档版本 {version_id} 向量索引点数量 ({point_count}) "
                f"与子文本块数量 ({target.child_count}) 不一致"
            )
        completion = await self._documents.complete_index(
            version_id,
            job_id=claim.job_id,
            attempt=claim.attempt,
            at=datetime.now(UTC),
        )
        if completion.write is StageWrite.VANISHED:
            log.warning("索引门控阶段版本记录已删除", document_version_id=str(version_id))
        elif completion.write is StageWrite.SUPERSEDED:
            log.warning(
                "索引门控任务尝试被取代",
                document_version_id=str(version_id),
                job_id=str(claim.job_id),
            )
        indexed = IndexedVersion(
            document_version_id=version_id,
            point_count=point_count,
            child_count=target.child_count,
        )
        log.info(
            "索引门控阶段校验完成",
            document_version_id=str(version_id),
            point_count=indexed.point_count,
            child_count=indexed.child_count,
        )
        return IndexOutcome(indexed=indexed)
