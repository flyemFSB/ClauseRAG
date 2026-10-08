"""知识库与文档数据行到领域实体的转换映射。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.knowledge import Document, DocumentVersion, DocumentVersionStatus, KnowledgeBase

if TYPE_CHECKING:
    from infrastructure.db.models.documents import DocumentRow, DocumentVersionRow
    from infrastructure.db.models.knowledge_bases import KnowledgeBaseRow


def to_knowledge_base(row: KnowledgeBaseRow) -> KnowledgeBase:
    """将知识库数据库行转换为领域实体。"""
    return KnowledgeBase(
        id=row.id,
        owner_id=row.owner_id,
        name=row.name,
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def to_document(row: DocumentRow) -> Document:
    """将文档数据库行转换为领域实体。"""
    return Document(
        id=row.id,
        knowledge_base_id=row.knowledge_base_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def to_document_version(row: DocumentVersionRow) -> DocumentVersion:
    """将文档版本数据库行转换为领域实体。"""
    return DocumentVersion(
        id=row.id,
        document_id=row.document_id,
        version_ordinal=row.version_ordinal,
        status=DocumentVersionStatus(row.status),
        mime_type=row.mime_type,
        checksum=row.checksum,
        size_bytes=row.size_bytes,
        source_object_key=row.source_object_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
