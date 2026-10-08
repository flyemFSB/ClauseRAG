"""文档、版本与摄取任务相关路由。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.knowledge_schemas import (
    DocumentDetailResponse,
    DocumentVersionDetailResponse,
    DocumentVersionResponse,
    IngestionJobResponse,
    ParseRetryResponse,
)
from application.knowledge.document_catalog import DocumentCatalog
from domain.identity import PLATFORM_OWNER_ID
from domain.parsing import ParseRetryOutcome, RetryNotAllowedError


def get_document_catalog() -> DocumentCatalog:
    """获取文档目录服务（依赖注入容器提供）"""
    raise RuntimeError("文档用例服务未绑定至当前应用实例")


DocumentCatalogDependency = Annotated[DocumentCatalog, Depends(get_document_catalog)]


def create_documents_router() -> APIRouter:
    """构建文档、版本与任务管理路由"""
    router = APIRouter(prefix="/api/v1", tags=["documents"])

    @router.get("/documents/{document_id}")
    async def get_document(
        document_id: UUID,
        catalog: DocumentCatalogDependency,
    ) -> DocumentDetailResponse:
        """获取文档详情及其版本列表"""
        detail = await catalog.get_document(owner_id=PLATFORM_OWNER_ID, document_id=document_id)
        return DocumentDetailResponse.from_detail(detail)

    @router.get("/documents/{document_id}/versions")
    async def list_document_versions(
        document_id: UUID,
        catalog: DocumentCatalogDependency,
    ) -> list[DocumentVersionResponse]:
        """获取文档的所有历史版本"""
        return [
            DocumentVersionResponse.from_version(version)
            for version in await catalog.list_versions(
                owner_id=PLATFORM_OWNER_ID,
                document_id=document_id,
            )
        ]

    @router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_document(
        document_id: UUID,
        catalog: DocumentCatalogDependency,
    ) -> None:
        """删除文档及其所有版本、任务和关联存储对象"""
        await catalog.delete(owner_id=PLATFORM_OWNER_ID, document_id=document_id)

    @router.get("/document-versions/{version_id}")
    async def get_document_version(
        version_id: UUID,
        catalog: DocumentCatalogDependency,
    ) -> DocumentVersionDetailResponse:
        """获取文档版本详情与最近一次成功解析的产物元数据"""
        version = await catalog.get_version(owner_id=PLATFORM_OWNER_ID, version_id=version_id)
        artifact = await catalog.get_version_artifact(
            owner_id=PLATFORM_OWNER_ID,
            version_id=version_id,
        )
        return DocumentVersionDetailResponse.from_version_and_artifact(version, artifact)

    @router.get("/document-versions/{version_id}/jobs")
    async def list_version_jobs(
        version_id: UUID,
        catalog: DocumentCatalogDependency,
    ) -> list[IngestionJobResponse]:
        """获取指定文档版本关联的所有摄取流水线任务"""
        return [
            IngestionJobResponse.from_job(job)
            for job in await catalog.list_version_jobs(
                owner_id=PLATFORM_OWNER_ID,
                version_id=version_id,
            )
        ]

    @router.post(
        "/document-versions/{version_id}/retry",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def retry_document_version(
        version_id: UUID,
        response: Response,
        catalog: DocumentCatalogDependency,
    ) -> ParseRetryResponse:
        """手动触发文档版本的解析重试"""
        try:
            retry = await catalog.retry_parse(
                owner_id=PLATFORM_OWNER_ID,
                document_version_id=version_id,
            )
        except RetryNotAllowedError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        if retry.outcome in (ParseRetryOutcome.QUEUED, ParseRetryOutcome.RUNNING):
            response.status_code = status.HTTP_200_OK
        return ParseRetryResponse.from_retry(retry)

    @router.get("/ingestion-jobs/{job_id}")
    async def get_ingestion_job(
        job_id: UUID,
        catalog: DocumentCatalogDependency,
    ) -> IngestionJobResponse:
        """获取指定摄取任务的执行状态"""
        job = await catalog.get_job(owner_id=PLATFORM_OWNER_ID, job_id=job_id)
        return IngestionJobResponse.from_job(job)

    return router
