"""文档解析阶段：读取原始文件、解析、规范化并持久化 Markdown 产物。"""

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
from domain.knowledge import IngestionJob, IngestionStage, KnowledgeNotFoundError
from domain.normalization import normalize_parsed_document
from domain.parsing import (
    PARSE_FAILED_STATE,
    DocumentParseError,
    OcrRequiredError,
    ParseArtifact,
    ParseClaim,
    ParsedDocument,
    ParseRoute,
    ParseTarget,
    TransientParseError,
    UnparseableDocumentError,
    failure_state_for,
    parse_route_for_extension,
    parsed_object_key,
)
from domain.uploads import extension_of

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from application.ingestion.parsers import DocumentParser
    from application.ingestion.store import IngestionStore
    from application.shared.storage import ObjectStorage

log = structlog.get_logger(__name__)

_ARTIFACT_CONTENT_TYPE = "text/markdown"


@dataclass(frozen=True, slots=True)
class ParseOutcome:
    """解析阶段输出结果：产物元数据及后续分块任务。"""

    artifact: ParseArtifact
    next_job: IngestionJob | None


class ParseDocumentVersion:
    """执行单个文档版本的解析阶段任务。"""

    def __init__(
        self,
        *,
        documents: IngestionStore,
        objects: ObjectStorage,
        parsers: Mapping[ParseRoute, DocumentParser],
        max_parse_bytes: int,
        parse_timeout_seconds: int,
    ) -> None:
        self._documents = documents
        self._objects = objects
        self._parsers = parsers
        self._max_parse_bytes = max_parse_bytes
        self._parse_timeout_seconds = parse_timeout_seconds

    async def run(self, version_id: UUID) -> ParseOutcome:
        """运维路径执行单次解析，失败直接抛出归类异常。"""
        target = await self._documents.begin_parse(version_id, at=datetime.now(UTC))
        if target is None:
            raise KnowledgeNotFoundError("document_version", version_id)
        return await self.attempt(target)

    async def attempt(self, claim: ParseClaim) -> ParseOutcome:
        """执行已认领的解析任务尝试，并在事务中记录结果。"""
        try:
            return await self._parse_and_store(claim)
        except DocumentParseError as error:
            await self._record_failure(claim, error)
            raise
        except ObjectStorageError as error:
            failure = TransientParseError(f"解析阶段对象存储调用失败: {error}")
            await self._record_failure(claim, failure)
            raise failure from error
        except TimeoutError as error:
            failure = TransientParseError(f"解析阶段超时 (超过 {self._parse_timeout_seconds} 秒)")
            await self._record_failure(claim, failure)
            raise failure from error
        except Exception as error:
            await record_stage_failure(
                self._documents,
                stage=IngestionStage.PARSE,
                claim=claim,
                error=error,
                retryable=False,
                state=PARSE_FAILED_STATE,
            )
            raise

    async def _parse_and_store(self, claim: ParseClaim) -> ParseOutcome:
        """执行下载、解析、规范化并在短事务中落库。"""
        target = claim.target
        version_id = target.document_version_id
        route = parse_route_for_extension(extension_of(target.source_object_key))
        async with asyncio.timeout(self._parse_timeout_seconds):
            data = await self._read_source(target)
            parsed = await self._parse(route, data, target)
            normalized = normalize_parsed_document(parsed)
            body = normalized.markdown.encode("utf-8")
            if not body:
                raise UnparseableDocumentError(
                    f"{route.value} 解析器未从 {target.source_object_key} 提取出任何有效文本"
                )
            artifact = await self._store(claim, normalized, body)
        completion = await self._documents.complete_parse(
            artifact,
            job_id=claim.job_id,
            attempt=claim.attempt,
            at=datetime.now(UTC),
        )
        if completion.write is StageWrite.VANISHED:
            log.warning("解析阶段版本记录已删除", document_version_id=str(version_id))
            await delete_artifacts(
                self._objects,
                [artifact.markdown_object_key],
                resource="document_version",
                resource_id=version_id,
                reason="rows_deleted",
            )
        elif completion.write is StageWrite.SUPERSEDED:
            log.warning(
                "解析任务尝试被取代",
                document_version_id=str(version_id),
                job_id=str(claim.job_id),
            )
            await delete_artifacts(
                self._objects,
                [artifact.markdown_object_key],
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
        next_job = completion.next_job
        log.info(
            "文档解析阶段完成",
            document_version_id=str(version_id),
            parser_name=artifact.parser_name,
            parser_version=artifact.parser_version,
            markdown_object_key=artifact.markdown_object_key,
            checksum=artifact.checksum,
            size_bytes=artifact.size_bytes,
            page_count=artifact.page_count,
            next_stage=next_job.stage.value if next_job is not None else None,
            next_job_id=str(next_job.id) if next_job is not None else None,
        )
        return ParseOutcome(artifact=artifact, next_job=next_job)

    async def _read_source(self, target: ParseTarget) -> bytes:
        data = await self._objects.get_bytes(
            target.source_object_key,
            max_bytes=self._max_parse_bytes,
        )
        if data is None:
            raise UnparseableDocumentError(
                f"对象存储中不存在待解析的源文件: {target.source_object_key}"
            )
        return data

    async def _parse(
        self,
        route: ParseRoute,
        data: bytes,
        target: ParseTarget,
    ) -> ParsedDocument:
        parser = self._parsers[route]
        filename = target.source_object_key.rsplit("/", 1)[-1]
        try:
            return await parser.parse(data, filename=filename, mime_type=target.mime_type)
        except OcrRequiredError as escalation:
            ocr = self._parsers[ParseRoute.OCR]
            if ocr is parser:
                raise
            log.info(
                "文档解析升级至OCR解析器",
                document_version_id=str(target.document_version_id),
                route=route.value,
                reason=str(escalation),
            )
            return await ocr.parse(data, filename=filename, mime_type=target.mime_type)

    async def _store(
        self,
        claim: ParseClaim,
        parsed: ParsedDocument,
        body: bytes,
    ) -> ParseArtifact:
        version_id = claim.target.document_version_id
        key = parsed_object_key(version_id, claim.job_id, claim.attempt)
        written = hashlib.sha256(body).hexdigest()
        await self._objects.put_stream(
            BytesIO(body),
            key=key,
            content_type=_ARTIFACT_CONTENT_TYPE,
            sha256=written,
        )
        stored = await self._objects.head(key)
        if stored is None:
            raise TransientParseError(f"解析制品写入后未在对象存储中找到: {key}")
        if stored.size_bytes != len(body):
            raise TransientParseError(
                f"解析制品 {key} 存储大小 ({stored.size_bytes} 字节) "
                f"与写入大小 ({len(body)} 字节) 不符"
            )
        read_back = await self._objects.get_bytes(key, max_bytes=len(body))
        if read_back is None:
            raise TransientParseError(f"解析制品写入后无法回读: {key}")
        checksum = hashlib.sha256(read_back).hexdigest()
        if checksum != written:
            raise TransientParseError(
                f"解析制品 {key} 回读校验和 ({checksum}) 与写入校验和 ({written}) 不符"
            )
        return ParseArtifact(
            document_version_id=version_id,
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
            markdown_object_key=key,
            checksum=checksum,
            size_bytes=len(read_back),
            page_count=parsed.page_count,
            warnings=parsed.warnings,
        )

    async def _record_failure(self, claim: ParseClaim, error: Exception) -> None:
        await record_stage_failure(
            self._documents,
            stage=IngestionStage.PARSE,
            claim=claim,
            error=error,
            retryable=isinstance(error, TransientParseError),
            state=(
                failure_state_for(error)
                if isinstance(error, DocumentParseError)
                else PARSE_FAILED_STATE
            ),
        )
