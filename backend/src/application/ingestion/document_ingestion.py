# ruff: noqa: TC001, TC003
"""文档摄取门面服务：处理队列消息派发与运维单步执行。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

import structlog

from application.ingestion.chunk import ChunkDocumentVersion, ChunkOutcome
from application.ingestion.embed import EmbedDocumentVersion, EmbedOutcome
from application.ingestion.index import IndexDocumentVersion, IndexOutcome
from application.ingestion.parse import ParseDocumentVersion, ParseOutcome
from application.ingestion.store import IngestionStore
from domain.knowledge import (
    IngestionJob,
    IngestionStage,
)

log = structlog.get_logger(__name__)


def _elapsed_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)


def _wired[StageClient](wired: StageClient | None, stage: IngestionStage) -> StageClient:
    if wired is None:
        raise RuntimeError(f"当前进程未装配 {stage.value} 阶段执行器")
    return wired


StageOutcome = ParseOutcome | ChunkOutcome | EmbedOutcome | IndexOutcome


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """摄取投递执行结果：下一阶段待执行任务。"""

    next_job: IngestionJob | None


class DocumentIngestion:
    """文档摄取服务：统一调度解析、分块、向量化与索引核验。"""

    def __init__(
        self,
        *,
        parse: ParseDocumentVersion | None = None,
        chunk: ChunkDocumentVersion | None = None,
        embed: EmbedDocumentVersion | None = None,
        index: IndexDocumentVersion | None = None,
        documents: IngestionStore,
    ) -> None:
        self._parse_stage = parse
        self._chunk_stage = chunk
        self._embed_stage = embed
        self._index_stage = index
        self._documents = documents

    async def run_stage(
        self,
        *,
        stage: IngestionStage,
        document_version_id: UUID,
        job_id: UUID,
    ) -> IngestionResult:
        """认领并执行指定阶段的单次任务尝试，返回下一阶段任务。"""
        if stage is IngestionStage.PARSE:
            return IngestionResult(next_job=await self._parse(document_version_id, job_id))
        if stage is IngestionStage.CHUNK:
            return IngestionResult(next_job=await self._chunk(document_version_id, job_id))
        if stage is IngestionStage.EMBED:
            return IngestionResult(next_job=await self._embed(document_version_id, job_id))
        if stage is IngestionStage.INDEX:
            return IngestionResult(next_job=await self._index(document_version_id, job_id))
        raise RuntimeError(f"未实现 {stage.value} 阶段的执行处理器")

    async def run_once(
        self,
        *,
        stage: IngestionStage,
        document_version_id: UUID,
    ) -> StageOutcome:
        """运维路径单次直接执行指定阶段。"""
        if stage is IngestionStage.PARSE:
            return await _wired(self._parse_stage, stage).run(document_version_id)
        if stage is IngestionStage.CHUNK:
            return await _wired(self._chunk_stage, stage).run(document_version_id)
        if stage is IngestionStage.EMBED:
            return await _wired(self._embed_stage, stage).run(document_version_id)
        if stage is IngestionStage.INDEX:
            return await _wired(self._index_stage, stage).run(document_version_id)
        raise RuntimeError(f"{stage.value} 阶段不支持运维单步执行")

    async def _parse(self, document_version_id: UUID, job_id: UUID) -> IngestionJob | None:
        claim = await self._documents.claim_parse_job(
            document_version_id,
            job_id,
            at=datetime.now(UTC),
        )
        if claim is None:
            self._log_skipped(IngestionStage.PARSE, document_version_id, job_id)
            return None
        self._log_attempt(IngestionStage.PARSE, document_version_id, job_id, claim.attempt)
        started = perf_counter()
        outcome = await _wired(self._parse_stage, IngestionStage.PARSE).attempt(claim)
        log.info(
            "解析任务单次完成",
            document_version_id=str(document_version_id),
            job_id=str(job_id),
            attempt=claim.attempt,
            duration_ms=_elapsed_ms(started),
            markdown_object_key=outcome.artifact.markdown_object_key,
            checksum=outcome.artifact.checksum,
        )
        return outcome.next_job

    async def _chunk(self, document_version_id: UUID, job_id: UUID) -> IngestionJob | None:
        claim = await self._documents.claim_chunk_job(
            document_version_id,
            job_id,
            at=datetime.now(UTC),
        )
        if claim is None:
            self._log_skipped(IngestionStage.CHUNK, document_version_id, job_id)
            return None
        self._log_attempt(IngestionStage.CHUNK, document_version_id, job_id, claim.attempt)
        started = perf_counter()
        outcome = await _wired(self._chunk_stage, IngestionStage.CHUNK).attempt(claim)
        log.info(
            "分块任务单次完成",
            document_version_id=str(document_version_id),
            job_id=str(job_id),
            attempt=claim.attempt,
            duration_ms=_elapsed_ms(started),
            object_key=outcome.artifact.object_key,
            checksum=outcome.artifact.checksum,
            child_count=outcome.artifact.child_count,
        )
        return outcome.next_job

    async def _embed(self, document_version_id: UUID, job_id: UUID) -> IngestionJob | None:
        claim = await self._documents.claim_embed_job(
            document_version_id,
            job_id,
            at=datetime.now(UTC),
        )
        if claim is None:
            self._log_skipped(IngestionStage.EMBED, document_version_id, job_id)
            return None
        self._log_attempt(IngestionStage.EMBED, document_version_id, job_id, claim.attempt)
        started = perf_counter()
        outcome = await _wired(self._embed_stage, IngestionStage.EMBED).attempt(claim)
        log.info(
            "向量化任务单次完成",
            document_version_id=str(document_version_id),
            job_id=str(job_id),
            attempt=claim.attempt,
            duration_ms=_elapsed_ms(started),
            child_count=outcome.embedded.child_count,
            batch_count=outcome.embedded.batch_count,
            model=outcome.embedded.model,
            dimension=outcome.embedded.dimension,
        )
        return outcome.next_job

    async def _index(self, document_version_id: UUID, job_id: UUID) -> IngestionJob | None:
        claim = await self._documents.claim_index_job(
            document_version_id,
            job_id,
            at=datetime.now(UTC),
        )
        if claim is None:
            self._log_skipped(IngestionStage.INDEX, document_version_id, job_id)
            return None
        self._log_attempt(IngestionStage.INDEX, document_version_id, job_id, claim.attempt)
        started = perf_counter()
        outcome = await _wired(self._index_stage, IngestionStage.INDEX).attempt(claim)
        log.info(
            "索引校验任务单次完成",
            document_version_id=str(document_version_id),
            job_id=str(job_id),
            attempt=claim.attempt,
            duration_ms=_elapsed_ms(started),
            point_count=outcome.indexed.point_count,
            child_count=outcome.indexed.child_count,
        )
        return None

    def _log_attempt(
        self,
        stage: IngestionStage,
        document_version_id: UUID,
        job_id: UUID,
        attempt: int,
    ) -> None:
        log.info(
            "摄取任务尝试开始",
            stage=stage.value,
            document_version_id=str(document_version_id),
            job_id=str(job_id),
            attempt=attempt,
        )

    def _log_skipped(
        self,
        stage: IngestionStage,
        document_version_id: UUID,
        job_id: UUID,
    ) -> None:
        log.info(
            "摄取任务重复，已跳过",
            stage=stage.value,
            document_version_id=str(document_version_id),
            job_id=str(job_id),
        )
