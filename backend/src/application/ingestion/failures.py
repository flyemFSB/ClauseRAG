"""摄取阶段失败状态记录。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from application.ingestion.store import FailureWrite

if TYPE_CHECKING:
    from application.ingestion.store import IngestionStore
    from domain.chunks.model import ChunkClaim
    from domain.embedding import EmbeddingClaim, IndexClaim
    from domain.knowledge import IngestionStage, StageFailureState
    from domain.parsing import ParseClaim

    StageAttempt = ParseClaim | ChunkClaim | EmbeddingClaim | IndexClaim

log = structlog.get_logger(__name__)


async def record_stage_failure(
    documents: IngestionStore,
    *,
    stage: IngestionStage,
    claim: StageAttempt,
    error: BaseException,
    retryable: bool,
    state: StageFailureState,
) -> FailureWrite:
    """在独立短事务中记录单次摄取阶段尝试失败，并把重试决策交给仓储。"""
    at = datetime.now(UTC)
    error_class = type(error).__name__
    error_message = str(error)
    write = await documents.fail_attempt(
        version_id=claim.target.document_version_id,
        job_id=claim.job_id,
        attempt=claim.attempt,
        stage=stage,
        error_class=error_class,
        error_message=error_message,
        retryable=retryable,
        state=state,
        at=at,
    )
    if write is FailureWrite.RETRY_SCHEDULED:
        log.info(
            "摄取任务已调度重试",
            stage=stage.value,
            document_version_id=str(claim.target.document_version_id),
            job_id=str(claim.job_id),
            attempt=claim.attempt,
            error_class=error_class,
        )
    elif write is FailureWrite.FAILED:
        log.warning(
            "摄取任务已终结失败",
            stage=stage.value,
            document_version_id=str(claim.target.document_version_id),
            job_id=str(claim.job_id),
            attempt=claim.attempt,
            error_class=error_class,
            error_message=error_message,
        )
    else:
        log.warning(
            "摄取失败状态未写入",
            stage=stage.value,
            document_version_id=str(claim.target.document_version_id),
            job_id=str(claim.job_id),
            attempt=claim.attempt,
            write=write.value,
            error_class=error_class,
        )
    return write
