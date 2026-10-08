"""文档分块阶段：读取 Markdown 规范产物、分块切分并持久化父子块元数据。"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import TYPE_CHECKING

import structlog

from application.ingestion.failures import record_stage_failure
from application.ingestion.store import StageWrite
from application.shared.artifacts import delete_artifacts
from application.shared.storage import ObjectStorageError
from domain.chunks.errors import (
    CHUNK_FAILED_STATE,
    ChunkError,
    TransientChunkError,
    UnchunkableDocumentError,
    failure_state_for,
)
from domain.chunks.keys import chunks_object_key
from domain.chunks.model import ChunkArtifact, ChunkClaim, ChunkPlan, ChunkTarget
from domain.chunks.planning import plan_chunks, render_chunks_jsonl
from domain.knowledge import IngestionStage, KnowledgeNotFoundError

if TYPE_CHECKING:
    from uuid import UUID

    from application.ingestion.store import IngestionStore
    from application.shared.storage import ObjectStorage
    from domain.chunks.model import TokenCounter
    from domain.knowledge import IngestionJob

log = structlog.get_logger(__name__)

_ARTIFACT_CONTENT_TYPE = "application/x-ndjson"


@dataclass(frozen=True, slots=True)
class ChunkOutcome:
    """分块阶段输出结果：产物元数据及后续向量化任务。"""

    artifact: ChunkArtifact
    next_job: IngestionJob | None


class ChunkDocumentVersion:
    """执行单个文档版本的分块阶段任务。"""

    def __init__(
        self,
        *,
        documents: IngestionStore,
        objects: ObjectStorage,
        counter: TokenCounter,
        max_markdown_bytes: int,
        chunk_timeout_seconds: int,
    ) -> None:
        self._documents = documents
        self._objects = objects
        self._counter = counter
        self._max_markdown_bytes = max_markdown_bytes
        self._chunk_timeout_seconds = chunk_timeout_seconds

    async def run(self, version_id: UUID) -> ChunkOutcome:
        """运维路径执行单次分块，失败直接抛出归类异常。"""
        target = await self._documents.begin_chunk(version_id, at=datetime.now(UTC))
        if target is None:
            raise KnowledgeNotFoundError("document_version", version_id)
        return await self.attempt(target)

    async def attempt(self, claim: ChunkClaim) -> ChunkOutcome:
        """执行已认领的分块任务尝试，并在事务中记录结果。"""
        try:
            return await self._chunk_and_store(claim)
        except ChunkError as error:
            await self._record_failure(
                claim,
                error,
                retryable=isinstance(error, TransientChunkError),
            )
            raise
        except ObjectStorageError as error:
            failure = TransientChunkError(f"分块阶段对象存储调用失败: {error}")
            await self._record_failure(claim, failure, retryable=True)
            raise failure from error
        except TimeoutError as error:
            failure = TransientChunkError(f"分块阶段超时 (超过 {self._chunk_timeout_seconds} 秒)")
            await self._record_failure(claim, failure, retryable=True)
            raise failure from error
        except Exception as error:
            await record_stage_failure(
                self._documents,
                stage=IngestionStage.CHUNK,
                claim=claim,
                error=error,
                retryable=False,
                state=CHUNK_FAILED_STATE,
            )
            raise

    async def _record_failure(
        self,
        claim: ChunkClaim,
        error: ChunkError,
        *,
        retryable: bool,
    ) -> None:
        await record_stage_failure(
            self._documents,
            stage=IngestionStage.CHUNK,
            claim=claim,
            error=error,
            retryable=retryable,
            state=failure_state_for(error),
        )

    async def _chunk_and_store(self, claim: ChunkClaim) -> ChunkOutcome:
        """读取 Markdown 产物、切分文本并在单次事务中写入块数据。"""
        target = claim.target
        version_id = target.document_version_id
        async with asyncio.timeout(self._chunk_timeout_seconds):
            markdown = await self._read_markdown(target)
            plan = plan_chunks(
                markdown,
                document_version_id=version_id,
                counter=self._counter,
            )
            artifact = await self._store(claim, plan)
        completion = await self._documents.complete_chunk(
            artifact,
            job_id=claim.job_id,
            attempt=claim.attempt,
            parents=plan.parents,
            children=plan.children,
            at=datetime.now(UTC),
        )
        if completion.write is StageWrite.VANISHED:
            log.warning("分块阶段版本记录已删除", document_version_id=str(version_id))
            await delete_artifacts(
                self._objects,
                [artifact.object_key],
                resource="document_version",
                resource_id=version_id,
                reason="rows_deleted",
            )
        elif completion.write is StageWrite.SUPERSEDED:
            log.warning(
                "分块任务尝试被取代",
                document_version_id=str(version_id),
                job_id=str(claim.job_id),
            )
            await delete_artifacts(
                self._objects,
                [artifact.object_key],
                resource="document_version",
                resource_id=version_id,
                reason="attempt_superseded",
            )
        if completion.replaced_object_key is not None:
            await delete_artifacts(
                self._objects,
                [completion.replaced_object_key],
                resource="document_version",
                resource_id=version_id,
                reason="artifact_replaced",
            )
        for warning in plan.warnings:
            log.warning("分块文本块拆分告警", document_version_id=str(version_id), warning=warning)
        log.info(
            "分块阶段执行完成",
            document_version_id=str(version_id),
            object_key=artifact.object_key,
            checksum=artifact.checksum,
            size_bytes=artifact.size_bytes,
            parent_count=artifact.parent_count,
            child_count=artifact.child_count,
            warning_count=len(plan.warnings),
        )
        return ChunkOutcome(artifact=artifact, next_job=completion.next_job)

    async def _read_markdown(self, target: ChunkTarget) -> str:
        data = await self._objects.get_bytes(
            target.markdown_object_key,
            max_bytes=self._max_markdown_bytes,
        )
        if data is None:
            raise UnchunkableDocumentError(
                f"对象存储中不存在 Markdown 制品: {target.markdown_object_key}"
            )
        if len(data) != target.markdown_size_bytes:
            raise UnchunkableDocumentError(
                f"Markdown 制品 {target.markdown_object_key} 实际大小 ({len(data)} 字节) "
                f"与解析记录 ({target.markdown_size_bytes} 字节) 不符"
            )
        checksum = hashlib.sha256(data).hexdigest()
        if checksum != target.markdown_checksum:
            raise UnchunkableDocumentError(
                f"Markdown 制品 {target.markdown_object_key} 校验和 ({checksum}) "
                f"与解析记录 ({target.markdown_checksum}) 不符"
            )
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise UnchunkableDocumentError(
                f"Markdown 制品 {target.markdown_object_key} 并非有效的 UTF-8 编码"
            ) from error

    async def _store(self, claim: ChunkClaim, plan: ChunkPlan) -> ChunkArtifact:
        version_id = claim.target.document_version_id
        key = chunks_object_key(version_id, claim.job_id, claim.attempt)
        body = render_chunks_jsonl(plan)
        written = hashlib.sha256(body).hexdigest()
        await self._objects.put_stream(
            BytesIO(body),
            key=key,
            content_type=_ARTIFACT_CONTENT_TYPE,
            sha256=written,
        )
        stored = await self._objects.head(key)
        if stored is None:
            raise TransientChunkError(f"分块制品写入后未在对象存储中找到: {key}")
        if stored.size_bytes != len(body):
            raise TransientChunkError(
                f"分块制品 {key} 存储大小 ({stored.size_bytes} 字节) "
                f"与写入大小 ({len(body)} 字节) 不符"
            )
        read_back = await self._objects.get_bytes(key, max_bytes=len(body))
        if read_back is None:
            raise TransientChunkError(f"分块制品写入后无法回读: {key}")
        checksum = hashlib.sha256(read_back).hexdigest()
        if checksum != written:
            raise TransientChunkError(
                f"分块制品 {key} 回读校验和 ({checksum}) 与写入校验和 ({written}) 不符"
            )
        return ChunkArtifact(
            document_version_id=version_id,
            object_key=key,
            checksum=checksum,
            size_bytes=len(read_back),
            parent_count=len(plan.parents),
            child_count=len(plan.children),
            warnings=plan.warnings,
        )
