"""文档子树的删除与清理意向登记：文档级删除与知识库级删除共用的唯一实现。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from infrastructure.db.models.chunks import ChildChunkRow, ChunkArtifactRow
from infrastructure.db.models.documents import DocumentVersionRow
from infrastructure.db.models.ingestion import ParseArtifactRow
from infrastructure.db.stores.cleanup_store import add_cleanup_intent

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from domain.cleanup import CleanupKind


async def purge_document_versions(
    session: AsyncSession,
    *,
    document_ids: Sequence[UUID],
    knowledge_base_id: UUID,
    kind: CleanupKind,
    document_id: UUID | None,
) -> None:
    """删除这批文档的全部版本行，并登记对象存储与向量索引需要清理的键。

    派生对象的键必须在本事务内、在版本行删除之前读出来：版本行一删，键就只存在于这次登记的
    清理意向里。两个调用方的作用域不同（一个文档 vs 整个知识库），但登记的内容必须完全一致，
    否则知识库级删除会漏掉向量索引里的子块。
    """
    version_ids = select(DocumentVersionRow.id).where(
        DocumentVersionRow.document_id.in_(document_ids)
    )
    parse_keys = list(
        await session.scalars(
            select(ParseArtifactRow.markdown_object_key).where(
                ParseArtifactRow.document_version_id.in_(version_ids)
            )
        )
    )
    chunk_keys = list(
        await session.scalars(
            select(ChunkArtifactRow.object_key).where(
                ChunkArtifactRow.document_version_id.in_(version_ids)
            )
        )
    )
    child_ids = list(
        await session.scalars(
            select(ChildChunkRow.child_id).where(ChildChunkRow.document_version_id.in_(version_ids))
        )
    )
    deleted = await session.execute(
        delete(DocumentVersionRow)
        .where(DocumentVersionRow.document_id.in_(document_ids))
        .returning(DocumentVersionRow.id, DocumentVersionRow.source_object_key)
    )
    rows = list(deleted)
    keys = [row.source_object_key for row in rows]
    keys.extend(parse_keys)
    keys.extend(chunk_keys)
    add_cleanup_intent(
        session,
        kind=kind,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
        object_keys=keys,
        document_version_ids=tuple(row.id for row in rows),
        child_ids=child_ids,
        at=datetime.now(UTC),
    )
