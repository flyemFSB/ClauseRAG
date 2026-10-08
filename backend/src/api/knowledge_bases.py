"""知识库与文档上传相关路由。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.documents import DocumentCatalogDependency
from api.knowledge_schemas import (
    DocumentSummaryResponse,
    DocumentUploadResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
)
from application.knowledge.knowledge_bases import KnowledgeBaseChanges, KnowledgeBaseService
from application.knowledge.uploads import (
    EmptyUploadError,
    UnsupportedFileTypeError,
    UploadTooLargeError,
    UploadVerificationError,
)
from application.shared.storage import ObjectStorageError
from domain.identity import PLATFORM_OWNER_ID

_NULL_NAME_DETAIL = "name cannot be null"
_STORAGE_PUT_FAILED_DETAIL = "object storage did not store the upload"
_STORAGE_VERIFY_FAILED_DETAIL = "对象存储未能完整保存上传的文件内容"


def get_knowledge_base_service() -> KnowledgeBaseService:
    """获取知识库应用服务（依赖注入容器提供）"""
    raise RuntimeError("知识库用例服务未绑定至当前应用实例")


KnowledgeBaseServiceDependency = Annotated[
    KnowledgeBaseService,
    Depends(get_knowledge_base_service),
]


def create_knowledge_bases_router() -> APIRouter:
    """构建知识库管理路由"""
    router = APIRouter(prefix="/api/v1", tags=["knowledge-bases"])

    @router.post("/knowledge-bases", status_code=status.HTTP_201_CREATED)
    async def create_knowledge_base(
        payload: KnowledgeBaseCreateRequest,
        knowledge_bases: KnowledgeBaseServiceDependency,
    ) -> KnowledgeBaseResponse:
        """创建知识库"""
        knowledge_base = await knowledge_bases.create(
            owner_id=PLATFORM_OWNER_ID,
            name=payload.name,
            description=payload.description,
        )
        return KnowledgeBaseResponse.from_knowledge_base(knowledge_base)

    @router.get("/knowledge-bases")
    async def list_knowledge_bases(
        knowledge_bases: KnowledgeBaseServiceDependency,
    ) -> list[KnowledgeBaseResponse]:
        """获取全部知识库列表"""
        return [
            KnowledgeBaseResponse.from_knowledge_base(knowledge_base)
            for knowledge_base in await knowledge_bases.list_for_owner(PLATFORM_OWNER_ID)
        ]

    @router.get("/knowledge-bases/{knowledge_base_id}")
    async def get_knowledge_base(
        knowledge_base_id: UUID,
        knowledge_bases: KnowledgeBaseServiceDependency,
    ) -> KnowledgeBaseResponse:
        """获取单个知识库详情"""
        knowledge_base = await knowledge_bases.get(
            owner_id=PLATFORM_OWNER_ID,
            knowledge_base_id=knowledge_base_id,
        )
        return KnowledgeBaseResponse.from_knowledge_base(knowledge_base)

    @router.patch("/knowledge-bases/{knowledge_base_id}")
    async def update_knowledge_base(
        knowledge_base_id: UUID,
        payload: KnowledgeBaseUpdateRequest,
        knowledge_bases: KnowledgeBaseServiceDependency,
    ) -> KnowledgeBaseResponse:
        """更新知识库信息"""
        sent = payload.model_fields_set
        if "name" in sent and payload.name is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_NULL_NAME_DETAIL,
            )
        knowledge_base = await knowledge_bases.update(
            owner_id=PLATFORM_OWNER_ID,
            knowledge_base_id=knowledge_base_id,
            changes=KnowledgeBaseChanges(
                name=payload.name,
                description=payload.description,
                sets_name="name" in sent,
                sets_description="description" in sent,
            ),
        )
        return KnowledgeBaseResponse.from_knowledge_base(knowledge_base)

    @router.delete("/knowledge-bases/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_knowledge_base(
        knowledge_base_id: UUID,
        knowledge_bases: KnowledgeBaseServiceDependency,
    ) -> None:
        """删除知识库及其下属所有文档与资源"""
        await knowledge_bases.delete(
            owner_id=PLATFORM_OWNER_ID,
            knowledge_base_id=knowledge_base_id,
        )

    @router.post(
        "/knowledge-bases/{knowledge_base_id}/documents",
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_document(
        knowledge_base_id: UUID,
        catalog: DocumentCatalogDependency,
        file: Annotated[UploadFile, File()],
        document_id: Annotated[UUID | None, Form()] = None,
    ) -> DocumentUploadResponse:
        """上传文档版本并触发解析流水线"""
        try:
            upload = await catalog.upload(
                owner_id=PLATFORM_OWNER_ID,
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                filename=file.filename or "",
                source=file.file,
            )
        except UnsupportedFileTypeError as error:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(error),
            ) from error
        except UploadTooLargeError as error:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=str(error),
            ) from error
        except EmptyUploadError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        except UploadVerificationError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=_STORAGE_VERIFY_FAILED_DETAIL,
            ) from error
        except ObjectStorageError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=_STORAGE_PUT_FAILED_DETAIL,
            ) from error
        return DocumentUploadResponse.from_upload(upload)

    @router.get("/knowledge-bases/{knowledge_base_id}/documents")
    async def list_documents(
        knowledge_base_id: UUID,
        catalog: DocumentCatalogDependency,
    ) -> list[DocumentSummaryResponse]:
        """获取知识库下的文档列表（含最新版本状态）"""
        return [
            DocumentSummaryResponse.from_summary(summary)
            for summary in await catalog.list_documents(
                owner_id=PLATFORM_OWNER_ID,
                knowledge_base_id=knowledge_base_id,
            )
        ]

    return router
