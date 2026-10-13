"""基于 SQLAlchemy 实现文档与文档版本管理仓储。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Text, cast, delete, func, select

from domain.cleanup import CleanupKind
from domain.knowledge import (
    DocumentDetail,
    DocumentSummary,
    DocumentUpload,
    DocumentVersion,
    DocumentVersionStatus,
    IngestionJob,
    IngestionJobStatus,
    IngestionStage,
)
from infrastructure.db.mappers.ingestion import (
    to_ingestion_job,
    to_parse_artifact,
)
from infrastructure.db.mappers.knowledge import to_document, to_document_version
from infrastructure.db.models.documents import DocumentRow, DocumentVersionRow
from infrastructure.db.models.ingestion import IngestionJobRow, ParseArtifactRow
from infrastructure.db.models.knowledge_bases import KnowledgeBaseRow
from infrastructure.db.stores.purge import purge_document_versions

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from domain.parsing import ParseArtifact


class SqlAlchemyDocumentStore:
    """文档仓储 SQLAlchemy 异步实现。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add_version(
        self,
        *,
        owner_id: UUID,
        knowledge_base_id: UUID,
        document_id: UUID | None,
        title: str,
        version_id: UUID,
        source_object_key: str,
        mime_type: str,
        checksum: str,
        size_bytes: int,
        at: datetime,
    ) -> DocumentUpload | None:
        """新增文档上传版本并创建首个待处理解析作业。"""
        async with self._sessions.begin() as session:
            owns_knowledge_base = await session.scalar(
                select(KnowledgeBaseRow.id).where(
                    KnowledgeBaseRow.id == knowledge_base_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
            if owns_knowledge_base is None:
                return None

            if document_id is None:
                document_row = DocumentRow(
                    id=uuid4(),
                    knowledge_base_id=knowledge_base_id,
                    title=title,
                    created_at=at,
                    updated_at=at,
                )
                session.add(document_row)
                version_ordinal = 1
            else:
                document_row = await session.scalar(
                    select(DocumentRow)
                    .where(
                        DocumentRow.id == document_id,
                        DocumentRow.knowledge_base_id == knowledge_base_id,
                    )
                    .with_for_update(of=DocumentRow)
                )
                if document_row is None:
                    return None
                highest_ordinal = await session.scalar(
                    select(func.max(DocumentVersionRow.version_ordinal)).where(
                        DocumentVersionRow.document_id == document_id
                    )
                )
                version_ordinal = (highest_ordinal or 0) + 1
                document_row.updated_at = at

            version_row = DocumentVersionRow(
                id=version_id,
                document_id=document_row.id,
                version_ordinal=version_ordinal,
                status=DocumentVersionStatus.UPLOADED.value,
                mime_type=mime_type,
                checksum=checksum,
                size_bytes=size_bytes,
                source_object_key=source_object_key,
                created_at=at,
                updated_at=at,
            )
            job_row = IngestionJobRow(
                id=uuid4(),
                document_version_id=version_id,
                stage=IngestionStage.PARSE.value,
                status=IngestionJobStatus.PENDING.value,
                revision=1,
                attempt=0,
                error_class=None,
                error_message=None,
                created_at=at,
                updated_at=at,
                started_at=None,
                finished_at=None,
            )
            session.add_all([version_row, job_row])
            await session.flush()
            return DocumentUpload(
                document=to_document(document_row),
                version=to_document_version(version_row),
                job=to_ingestion_job(job_row),
            )

    async def list_summaries(
        self,
        owner_id: UUID,
        knowledge_base_id: UUID,
    ) -> Sequence[DocumentSummary] | None:
        """获取知识库下所有文档及其最新版本的摘要信息。"""
        latest_version_id = (
            select(DocumentVersionRow.id)
            .where(DocumentVersionRow.document_id == DocumentRow.id)
            .order_by(DocumentVersionRow.version_ordinal.desc())
            .limit(1)
            .scalar_subquery()
            .label("latest_version_id")
        )
        async with self._sessions() as session:
            owns_knowledge_base = await session.scalar(
                select(KnowledgeBaseRow.id).where(
                    KnowledgeBaseRow.id == knowledge_base_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
            if owns_knowledge_base is None:
                return None
            rows = (
                await session.execute(
                    select(DocumentRow, latest_version_id)
                    .where(DocumentRow.knowledge_base_id == knowledge_base_id)
                    .order_by(DocumentRow.created_at.desc(), DocumentRow.id)
                )
            ).all()
            newest_ids = [row.latest_version_id for row in rows if row.latest_version_id]
            version_rows: Sequence[DocumentVersionRow] = ()
            if newest_ids:
                version_rows = (
                    await session.scalars(
                        select(DocumentVersionRow).where(DocumentVersionRow.id.in_(newest_ids))
                    )
                ).all()
            versions_by_id = {row.id: to_document_version(row) for row in version_rows}
            return [
                DocumentSummary(
                    document=to_document(document_row),
                    latest_version=versions_by_id.get(latest_id),
                )
                for document_row, latest_id in rows
            ]

    async def find_detail(self, owner_id: UUID, document_id: UUID) -> DocumentDetail | None:
        """查询文档详情及所有历史版本列表。"""
        async with self._sessions() as session:
            document_row = await session.scalar(
                select(DocumentRow)
                .join(KnowledgeBaseRow, KnowledgeBaseRow.id == DocumentRow.knowledge_base_id)
                .where(
                    DocumentRow.id == document_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
            if document_row is None:
                return None
            version_rows = await session.scalars(
                select(DocumentVersionRow)
                .where(DocumentVersionRow.document_id == document_id)
                .order_by(DocumentVersionRow.version_ordinal.desc())
            )
            return DocumentDetail(
                document=to_document(document_row),
                versions=[to_document_version(row) for row in version_rows],
            )

    async def find_version(
        self,
        owner_id: UUID,
        version_id: UUID,
    ) -> DocumentVersion | None:
        """查询指定文档版本元数据。"""
        async with self._sessions() as session:
            row = await session.scalar(
                select(DocumentVersionRow)
                .join(DocumentRow, DocumentRow.id == DocumentVersionRow.document_id)
                .join(KnowledgeBaseRow, KnowledgeBaseRow.id == DocumentRow.knowledge_base_id)
                .where(
                    DocumentVersionRow.id == version_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
            return None if row is None else to_document_version(row)

    async def list_jobs_for_version(
        self,
        owner_id: UUID,
        version_id: UUID,
    ) -> Sequence[IngestionJob] | None:
        """查询指定文档版本的所有摄取作业记录。"""
        async with self._sessions() as session:
            owns_version = await session.scalar(
                select(DocumentVersionRow.id)
                .join(DocumentRow, DocumentRow.id == DocumentVersionRow.document_id)
                .join(KnowledgeBaseRow, KnowledgeBaseRow.id == DocumentRow.knowledge_base_id)
                .where(
                    DocumentVersionRow.id == version_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
            if owns_version is None:
                return None
            rows = await session.scalars(
                select(IngestionJobRow)
                .where(IngestionJobRow.document_version_id == version_id)
                .order_by(IngestionJobRow.created_at, IngestionJobRow.id)
            )
            return [to_ingestion_job(row) for row in rows]

    async def find_job(self, owner_id: UUID, job_id: UUID) -> IngestionJob | None:
        """查询单个摄取作业详情。"""
        async with self._sessions() as session:
            row = await session.scalar(
                select(IngestionJobRow)
                .join(
                    DocumentVersionRow,
                    DocumentVersionRow.id == IngestionJobRow.document_version_id,
                )
                .join(DocumentRow, DocumentRow.id == DocumentVersionRow.document_id)
                .join(KnowledgeBaseRow, KnowledgeBaseRow.id == DocumentRow.knowledge_base_id)
                .where(
                    IngestionJobRow.id == job_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
            return None if row is None else to_ingestion_job(row)

    async def find_parse_artifact(
        self,
        owner_id: UUID,
        version_id: UUID,
    ) -> ParseArtifact | None:
        """查询文档版本的解析产物信息。"""
        async with self._sessions() as session:
            row = await session.scalar(
                select(ParseArtifactRow)
                .join(
                    DocumentVersionRow,
                    DocumentVersionRow.id == ParseArtifactRow.document_version_id,
                )
                .join(DocumentRow, DocumentRow.id == DocumentVersionRow.document_id)
                .join(KnowledgeBaseRow, KnowledgeBaseRow.id == DocumentRow.knowledge_base_id)
                .where(
                    ParseArtifactRow.document_version_id == version_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
            return None if row is None else to_parse_artifact(row)

    async def revision_for_knowledge_base(self, knowledge_base_id: UUID) -> str:
        """获取知识库语料版本标识，基于文档版本数量与最近更新时间生成。"""
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(
                        func.count(DocumentVersionRow.id),
                        func.coalesce(
                            cast(func.max(DocumentVersionRow.updated_at), Text),
                            "none",
                        ),
                    )
                    .join(DocumentRow, DocumentRow.id == DocumentVersionRow.document_id)
                    .where(DocumentRow.knowledge_base_id == knowledge_base_id)
                )
            ).one()
        return f"{row[0]}:{row[1]}"

    async def delete(self, owner_id: UUID, document_id: UUID) -> bool:
        """删除文档及其所有版本、作业与分块，并同步记录清理意向。"""
        async with self._sessions.begin() as session:
            knowledge_base_id = await session.scalar(
                select(DocumentRow.knowledge_base_id)
                .join(KnowledgeBaseRow, KnowledgeBaseRow.id == DocumentRow.knowledge_base_id)
                .where(
                    DocumentRow.id == document_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
            if knowledge_base_id is None:
                return False
            await purge_document_versions(
                session,
                document_ids=(document_id,),
                knowledge_base_id=knowledge_base_id,
                kind=CleanupKind.DOCUMENT,
                document_id=document_id,
            )
            await session.execute(delete(DocumentRow).where(DocumentRow.id == document_id))
            return True
