"""知识库、文档、版本与摄取任务相关的 HTTP 请求与响应模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, PlainSerializer

from domain.knowledge import (
    Document,
    DocumentDetail,
    DocumentSummary,
    DocumentUpload,
    DocumentVersion,
    DocumentVersionStatus,
    IngestionJob,
    IngestionJobStatus,
    IngestionStage,
    KnowledgeBase,
)
from domain.parsing import ParseArtifact, ParseRetry, ParseRetryOutcome


def _format_timestamp(value: datetime) -> str:
    """格式化时间戳为 UTC ISO-8601 字符串"""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


WireTimestamp = Annotated[
    datetime,
    PlainSerializer(_format_timestamp, return_type=str, when_used="json"),
]


class KnowledgeBaseCreateRequest(BaseModel):
    """创建知识库请求"""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class KnowledgeBaseUpdateRequest(BaseModel):
    """更新知识库请求"""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class KnowledgeBaseResponse(BaseModel):
    """知识库响应"""

    id: UUID
    name: str
    description: str | None
    created_at: WireTimestamp
    updated_at: WireTimestamp

    @classmethod
    def from_knowledge_base(cls, knowledge_base: KnowledgeBase) -> KnowledgeBaseResponse:
        """从领域对象构建响应"""
        return cls(
            id=knowledge_base.id,
            name=knowledge_base.name,
            description=knowledge_base.description,
            created_at=knowledge_base.created_at,
            updated_at=knowledge_base.updated_at,
        )


class DocumentResponse(BaseModel):
    """逻辑文档响应"""

    id: UUID
    knowledge_base_id: UUID
    title: str
    created_at: WireTimestamp
    updated_at: WireTimestamp

    @classmethod
    def from_document(cls, document: Document) -> DocumentResponse:
        """从领域文档对象构建响应"""
        return cls(
            id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            title=document.title,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )


class DocumentVersionResponse(BaseModel):
    """文档版本响应"""

    id: UUID
    document_id: UUID
    version_ordinal: int
    status: DocumentVersionStatus
    mime_type: str
    checksum: str
    size_bytes: int
    created_at: WireTimestamp
    updated_at: WireTimestamp

    @classmethod
    def from_version(cls, version: DocumentVersion) -> DocumentVersionResponse:
        """从领域版本对象构建响应"""
        return cls(
            id=version.id,
            document_id=version.document_id,
            version_ordinal=version.version_ordinal,
            status=version.status,
            mime_type=version.mime_type,
            checksum=version.checksum,
            size_bytes=version.size_bytes,
            created_at=version.created_at,
            updated_at=version.updated_at,
        )


class ParseArtifactResponse(BaseModel):
    """文档解析产物元数据响应"""

    parser_name: str
    parser_version: str
    page_count: int | None
    warnings: list[str]
    checksum: str
    size_bytes: int

    @classmethod
    def from_artifact(cls, artifact: ParseArtifact) -> ParseArtifactResponse:
        """从解析产物领域对象构建响应"""
        return cls(
            parser_name=artifact.parser_name,
            parser_version=artifact.parser_version,
            page_count=artifact.page_count,
            warnings=list(artifact.warnings),
            checksum=artifact.checksum,
            size_bytes=artifact.size_bytes,
        )


class IngestionJobResponse(BaseModel):
    """摄取任务阶段执行状态响应"""

    id: UUID
    document_version_id: UUID
    stage: IngestionStage
    status: IngestionJobStatus
    revision: int
    attempt: int
    error_class: str | None
    error_message: str | None
    created_at: WireTimestamp
    updated_at: WireTimestamp
    started_at: WireTimestamp | None
    finished_at: WireTimestamp | None

    @classmethod
    def from_job(cls, job: IngestionJob) -> IngestionJobResponse:
        """从领域任务对象构建响应"""
        return cls(
            id=job.id,
            document_version_id=job.document_version_id,
            stage=job.stage,
            status=job.status,
            revision=job.revision,
            attempt=job.attempt,
            error_class=job.error_class,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class DocumentSummaryResponse(DocumentResponse):
    """文档概览列表项（附带最新版本信息）"""

    latest_version: DocumentVersionResponse | None

    @classmethod
    def from_summary(cls, summary: DocumentSummary) -> DocumentSummaryResponse:
        """从文档摘要构建响应"""
        return cls(
            id=summary.document.id,
            knowledge_base_id=summary.document.knowledge_base_id,
            title=summary.document.title,
            created_at=summary.document.created_at,
            updated_at=summary.document.updated_at,
            latest_version=(
                None
                if summary.latest_version is None
                else DocumentVersionResponse.from_version(summary.latest_version)
            ),
        )


class DocumentDetailResponse(DocumentResponse):
    """文档详情（包含全量版本历史）"""

    versions: list[DocumentVersionResponse]

    @classmethod
    def from_detail(cls, detail: DocumentDetail) -> DocumentDetailResponse:
        """从文档详情领域对象构建响应"""
        return cls(
            id=detail.document.id,
            knowledge_base_id=detail.document.knowledge_base_id,
            title=detail.document.title,
            created_at=detail.document.created_at,
            updated_at=detail.document.updated_at,
            versions=[DocumentVersionResponse.from_version(version) for version in detail.versions],
        )


class DocumentVersionDetailResponse(DocumentVersionResponse):
    """单版本详情（附带解析产物）"""

    parse_artifact: ParseArtifactResponse | None

    @classmethod
    def from_version_and_artifact(
        cls,
        version: DocumentVersion,
        artifact: ParseArtifact | None,
    ) -> DocumentVersionDetailResponse:
        """从版本与解析产物构建响应"""
        return cls(
            id=version.id,
            document_id=version.document_id,
            version_ordinal=version.version_ordinal,
            status=version.status,
            mime_type=version.mime_type,
            checksum=version.checksum,
            size_bytes=version.size_bytes,
            created_at=version.created_at,
            updated_at=version.updated_at,
            parse_artifact=(
                None if artifact is None else ParseArtifactResponse.from_artifact(artifact)
            ),
        )


class DocumentUploadResponse(BaseModel):
    """文档上传结果响应（新建的文档、版本与摄取任务）"""

    document: DocumentResponse
    version: DocumentVersionResponse
    job: IngestionJobResponse

    @classmethod
    def from_upload(cls, upload: DocumentUpload) -> DocumentUploadResponse:
        """从上传结果构建响应"""
        return cls(
            document=DocumentResponse.from_document(upload.document),
            version=DocumentVersionResponse.from_version(upload.version),
            job=IngestionJobResponse.from_job(upload.job),
        )


class ParseRetryResponse(BaseModel):
    """解析重试触发响应"""

    job: IngestionJobResponse
    version_status: DocumentVersionStatus
    outcome: ParseRetryOutcome
    created: bool

    @classmethod
    def from_retry(cls, retry: ParseRetry) -> ParseRetryResponse:
        """从重试结果构建响应"""
        return cls(
            job=IngestionJobResponse.from_job(retry.job),
            version_status=retry.version_status,
            outcome=retry.outcome,
            created=retry.outcome in (ParseRetryOutcome.CREATED, ParseRetryOutcome.STALE),
        )
