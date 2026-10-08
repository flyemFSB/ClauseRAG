"""文档上传入库事务与解析任务分发服务。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

from application.ingestion.dispatch import dispatch_committed_job
from application.knowledge.uploads import (
    EmptyUploadError,
    UnsupportedFileTypeError,
    UploadVerificationError,
    measure_upload,
)
from application.shared.artifacts import delete_artifacts
from application.shared.storage import ObjectStorageError
from domain.knowledge import DocumentUpload, KnowledgeNotFoundError
from domain.uploads import mime_type_for_filename, original_object_key

if TYPE_CHECKING:
    from typing import BinaryIO
    from uuid import UUID

    from application.ingestion.dispatch import JobDispatcher
    from application.knowledge.contracts import DocumentStore
    from application.knowledge.knowledge_bases import KnowledgeBaseStore
    from application.shared.storage import ObjectStorage

log = structlog.get_logger(__name__)


class DocumentUploads:
    """文档文件上传事务协调器"""

    def __init__(
        self,
        *,
        knowledge_bases: KnowledgeBaseStore,
        documents: DocumentStore,
        objects: ObjectStorage,
        dispatcher: JobDispatcher,
        max_upload_bytes: int,
    ) -> None:
        self._knowledge_bases = knowledge_bases
        self._documents = documents
        self._objects = objects
        self._dispatcher = dispatcher
        self._max_upload_bytes = max_upload_bytes

    async def upload(
        self,
        *,
        owner_id: UUID,
        knowledge_base_id: UUID,
        document_id: UUID | None,
        filename: str,
        source: BinaryIO,
    ) -> DocumentUpload:
        """存储上传文件、校验哈希、持久化版本记录并触发解析任务"""
        mime_type = mime_type_for_filename(filename)
        if mime_type is None:
            raise UnsupportedFileTypeError(filename)
        if await self._knowledge_bases.find_for_owner(owner_id, knowledge_base_id) is None:
            raise KnowledgeNotFoundError("knowledge_base", knowledge_base_id)

        checksum, size_bytes = await asyncio.to_thread(
            measure_upload,
            source,
            self._max_upload_bytes,
        )
        if size_bytes == 0:
            raise EmptyUploadError(filename)

        version_id = uuid4()
        object_key = original_object_key(version_id, filename)
        try:
            await self._objects.put_stream(
                source,
                key=object_key,
                content_type=mime_type,
                sha256=checksum,
            )
            stored = await self._objects.head(object_key)
        except ObjectStorageError:
            await self.discard(object_key, version_id, reason="upload_failed")
            raise
        if stored is None or stored.size_bytes != size_bytes or stored.sha256 != checksum:
            await self.discard(object_key, version_id, reason="verification_failed")
            raise UploadVerificationError(object_key)

        try:
            upload = await self._documents.add_version(
                owner_id=owner_id,
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                title=filename,
                version_id=version_id,
                source_object_key=object_key,
                mime_type=mime_type,
                checksum=checksum,
                size_bytes=size_bytes,
                at=datetime.now(UTC),
            )
        except Exception as error:
            await self.discard(
                object_key,
                version_id,
                reason="rows_not_written",
                error=error,
            )
            raise
        if upload is None:
            await self.discard(object_key, version_id, reason="rows_not_written")
            if document_id is None:
                raise KnowledgeNotFoundError("knowledge_base", knowledge_base_id)
            raise KnowledgeNotFoundError("document", document_id)
        log.info(
            "文档上传完成并已入库",
            document_id=str(upload.document.id),
            document_version_id=str(upload.version.id),
            version_ordinal=upload.version.version_ordinal,
            size_bytes=upload.version.size_bytes,
        )
        await dispatch_committed_job(
            self._dispatcher,
            upload.job,
            event="文档解析任务分发失败",
        )
        return upload

    async def discard(
        self,
        object_key: str,
        version_id: UUID,
        *,
        reason: str,
        error: Exception | None = None,
    ) -> None:
        """放弃未成功入库的上传产物并记录告警日志"""
        log.error(
            "上传产物已废弃并清理",
            object_key=object_key,
            document_version_id=str(version_id),
            reason=reason,
            error=None if error is None else str(error),
        )
        await delete_artifacts(
            self._objects,
            [object_key],
            resource="document_version",
            resource_id=version_id,
            reason=reason,
        )
