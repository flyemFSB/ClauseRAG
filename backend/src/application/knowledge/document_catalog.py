"""文档目录应用服务：文档上传、版本查询、解析重试与删除管理。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from application.ingestion.dispatch import dispatch_committed_job
from application.knowledge.document_uploads import DocumentUploads
from domain.knowledge import (
    DocumentDetail,
    DocumentSummary,
    DocumentUpload,
    DocumentVersion,
    IngestionJob,
    IngestionJobStatus,
    KnowledgeNotFoundError,
)
from domain.parsing import (
    RETRYABLE_PARSE_STATUSES,
    ParseRetry,
    ParseRetryOutcome,
    RetryNotAllowedError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import BinaryIO
    from uuid import UUID

    from application.ingestion.dispatch import JobDispatcher
    from application.knowledge.contracts import DocumentStore, ParseRetryStore
    from application.knowledge.knowledge_bases import KnowledgeBaseStore
    from application.shared.storage import ObjectStorage
    from domain.parsing import ParseArtifact

log = structlog.get_logger(__name__)


class DocumentCatalog:
    """文档生命周期目录服务"""

    def __init__(
        self,
        *,
        knowledge_bases: KnowledgeBaseStore,
        documents: DocumentStore,
        ingestion: ParseRetryStore,
        objects: ObjectStorage,
        dispatcher: JobDispatcher,
        max_upload_bytes: int,
        job_stale_after: timedelta,
    ) -> None:
        self._knowledge_bases = knowledge_bases
        self._documents = documents
        self._ingestion = ingestion
        self._objects = objects
        self._dispatcher = dispatcher
        self._max_upload_bytes = max_upload_bytes
        self._job_stale_after = job_stale_after
        self._uploads = DocumentUploads(
            knowledge_bases=knowledge_bases,
            documents=documents,
            objects=objects,
            dispatcher=dispatcher,
            max_upload_bytes=max_upload_bytes,
        )

    async def retry_parse(
        self,
        *,
        owner_id: UUID,
        document_version_id: UUID,
    ) -> ParseRetry:
        """手动触发文档版本的解析阶段重试"""
        retry = await self._ingestion.start_parse_retry(
            owner_id,
            document_version_id,
            retryable_statuses=RETRYABLE_PARSE_STATUSES,
            stale_after=self._job_stale_after,
            at=datetime.now(UTC),
        )
        if retry is None:
            raise KnowledgeNotFoundError("document_version", document_version_id)
        if retry.outcome is ParseRetryOutcome.NOT_RETRYABLE:
            raise RetryNotAllowedError(document_version_id, retry.version_status)
        if retry.job.status is IngestionJobStatus.PENDING:
            await dispatch_committed_job(
                self._dispatcher,
                retry.job,
                event="文档解析任务分发失败",
            )
        return retry

    async def upload(
        self,
        *,
        owner_id: UUID,
        knowledge_base_id: UUID,
        document_id: UUID | None,
        filename: str,
        source: BinaryIO,
    ) -> DocumentUpload:
        """保存上传文档版本并分发解析流水线任务"""
        return await self._uploads.upload(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            filename=filename,
            source=source,
        )

    async def list_documents(
        self,
        *,
        owner_id: UUID,
        knowledge_base_id: UUID,
    ) -> Sequence[DocumentSummary]:
        """获取知识库下的文档列表（含最新版本）"""
        summaries = await self._documents.list_summaries(owner_id, knowledge_base_id)
        if summaries is None:
            raise KnowledgeNotFoundError("knowledge_base", knowledge_base_id)
        return summaries

    async def get_document(self, *, owner_id: UUID, document_id: UUID) -> DocumentDetail:
        """获取单个文档详情及其完整版本历史"""
        detail = await self._documents.find_detail(owner_id, document_id)
        if detail is None:
            raise KnowledgeNotFoundError("document", document_id)
        return detail

    async def list_versions(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
    ) -> Sequence[DocumentVersion]:
        """获取文档的所有历史版本"""
        return (await self.get_document(owner_id=owner_id, document_id=document_id)).versions

    async def get_version(self, *, owner_id: UUID, version_id: UUID) -> DocumentVersion:
        """获取单个文档版本信息"""
        version = await self._documents.find_version(owner_id, version_id)
        if version is None:
            raise KnowledgeNotFoundError("document_version", version_id)
        return version

    async def get_version_artifact(
        self,
        *,
        owner_id: UUID,
        version_id: UUID,
    ) -> ParseArtifact | None:
        """获取文档版本最近一次解析成功的产物元数据"""
        return await self._documents.find_parse_artifact(owner_id, version_id)

    async def list_version_jobs(
        self,
        *,
        owner_id: UUID,
        version_id: UUID,
    ) -> Sequence[IngestionJob]:
        """获取文档版本的摄取阶段任务列表"""
        jobs = await self._documents.list_jobs_for_version(owner_id, version_id)
        if jobs is None:
            raise KnowledgeNotFoundError("document_version", version_id)
        return jobs

    async def get_job(self, *, owner_id: UUID, job_id: UUID) -> IngestionJob:
        """获取指定摄取阶段任务"""
        job = await self._documents.find_job(owner_id, job_id)
        if job is None:
            raise KnowledgeNotFoundError("ingestion_job", job_id)
        return job

    async def delete(self, *, owner_id: UUID, document_id: UUID) -> None:
        """删除文档及其所有历史版本，并提交外部存储与索引异步清理意图"""
        if not await self._documents.delete(owner_id, document_id):
            raise KnowledgeNotFoundError("document", document_id)
