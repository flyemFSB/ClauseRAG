"""基于 SQLAlchemy 实现分块存储仓储（支持关键字搜索与分块批量加载）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from domain.chunks.model import BlockType, ChildChunk, ChunkArtifact, ParentChunk
from domain.knowledge import DocumentVersionStatus
from domain.retrieval import ChannelMatch, ChunkRecord
from infrastructure.db.models.chunks import ChildChunkRow, ChunkArtifactRow, ParentChunkRow
from infrastructure.db.models.documents import DocumentRow, DocumentVersionRow

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_LIKE_ESCAPE = "\\"


def like_pattern(query: str) -> str:
    """转义查询文本中的通配符并构造用于 LIKE 的模式字符串。"""
    escaped = query.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
    for wildcard in ("%", "_"):
        escaped = escaped.replace(wildcard, f"{_LIKE_ESCAPE}{wildcard}")
    return f"%{escaped}%"


class SqlAlchemyChunkStore:
    """分块存储仓储 SQLAlchemy 异步实现。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def keyword_search(
        self,
        *,
        knowledge_base_id: UUID,
        query: str,
        limit: int,
    ) -> Sequence[ChannelMatch]:
        """执行基于 pg_trgm 的三元组关键字相似度检索。"""
        if limit <= 0 or not query.strip():
            return ()
        similarity = func.similarity(ChildChunkRow.content, query)
        statement = (
            select(
                ChildChunkRow.child_id,
                ChildChunkRow.parent_id,
                ChildChunkRow.document_version_id,
                similarity.label("score"),
            )
            .join(
                DocumentVersionRow,
                DocumentVersionRow.id == ChildChunkRow.document_version_id,
            )
            .join(DocumentRow, DocumentRow.id == DocumentVersionRow.document_id)
            .where(
                DocumentRow.knowledge_base_id == knowledge_base_id,
                DocumentVersionRow.status == DocumentVersionStatus.READY.value,
                ChildChunkRow.content.like(like_pattern(query), escape=_LIKE_ESCAPE),
            )
            .order_by(sa.desc("score"), ChildChunkRow.child_id)
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return tuple(
            ChannelMatch(
                child_id=row.child_id,
                parent_id=row.parent_id,
                document_version_id=row.document_version_id,
                score=float(row.score),
            )
            for row in rows
        )

    async def load_records(
        self,
        *,
        knowledge_base_id: UUID,
        child_ids: Sequence[UUID],
    ) -> Mapping[UUID, ChunkRecord]:
        """根据子分块 ID 列表批量加载已就绪分块、父块上下文与文档元数据。"""
        if not child_ids:
            return {}
        statement = (
            select(
                ChildChunkRow.child_id,
                ChildChunkRow.parent_id,
                ChildChunkRow.document_version_id,
                ChildChunkRow.heading_path,
                ChildChunkRow.block_type,
                ChildChunkRow.ordinal,
                ChildChunkRow.line_start,
                ChildChunkRow.line_end,
                ChildChunkRow.content,
                ChildChunkRow.token_count,
                ParentChunkRow.content.label("parent_content"),
                ParentChunkRow.token_count.label("parent_token_count"),
                DocumentRow.id.label("document_id"),
                DocumentRow.knowledge_base_id,
                DocumentRow.title.label("document_name"),
            )
            .join(
                DocumentVersionRow,
                DocumentVersionRow.id == ChildChunkRow.document_version_id,
            )
            .join(DocumentRow, DocumentRow.id == DocumentVersionRow.document_id)
            .join(ParentChunkRow, ParentChunkRow.parent_id == ChildChunkRow.parent_id)
            .where(
                ChildChunkRow.child_id.in_(list(child_ids)),
                DocumentRow.knowledge_base_id == knowledge_base_id,
                DocumentVersionRow.status == DocumentVersionStatus.READY.value,
            )
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return {
            row.child_id: ChunkRecord(
                child_id=row.child_id,
                parent_id=row.parent_id,
                document_version_id=row.document_version_id,
                document_id=row.document_id,
                knowledge_base_id=row.knowledge_base_id,
                document_name=row.document_name,
                heading_path=tuple(row.heading_path),
                block_type=BlockType(row.block_type),
                ordinal=row.ordinal,
                line_start=row.line_start,
                line_end=row.line_end,
                content=row.content,
                token_count=row.token_count,
                parent_content=row.parent_content,
                parent_token_count=row.parent_token_count,
            )
            for row in rows
        }

    async def replace_version_chunks(
        self,
        session: AsyncSession,
        *,
        artifact: ChunkArtifact,
        parents: Sequence[ParentChunk],
        children: Sequence[ChildChunk],
        at: datetime,
    ) -> None:
        """在外部传入会话中替换指定文档版本的全部分块与分块产物记录。"""
        await session.execute(
            delete(ChildChunkRow).where(
                ChildChunkRow.document_version_id == artifact.document_version_id
            )
        )
        await session.execute(
            delete(ParentChunkRow).where(
                ParentChunkRow.document_version_id == artifact.document_version_id
            )
        )
        session.add_all(
            ParentChunkRow(
                parent_id=parent.parent_id,
                document_version_id=parent.document_version_id,
                heading_path=list(parent.heading_path),
                ordinal=parent.ordinal,
                content=parent.content,
                token_count=parent.token_count,
            )
            for parent in parents
        )
        await session.flush()
        session.add_all(
            ChildChunkRow(
                child_id=child.child_id,
                parent_id=child.parent_id,
                document_version_id=child.document_version_id,
                heading_path=list(child.heading_path),
                block_type=child.block_type.value,
                ordinal=child.ordinal,
                line_start=child.line_start,
                line_end=child.line_end,
                content=child.content,
                token_count=child.token_count,
            )
            for child in children
        )
        await session.execute(
            postgres_insert(ChunkArtifactRow)
            .values(
                document_version_id=artifact.document_version_id,
                object_key=artifact.object_key,
                checksum=artifact.checksum,
                size_bytes=artifact.size_bytes,
                parent_count=artifact.parent_count,
                child_count=artifact.child_count,
                warnings=list(artifact.warnings) or None,
                created_at=at,
                updated_at=at,
            )
            .on_conflict_do_update(
                index_elements=[ChunkArtifactRow.document_version_id],
                set_={
                    "object_key": artifact.object_key,
                    "checksum": artifact.checksum,
                    "size_bytes": artifact.size_bytes,
                    "parent_count": artifact.parent_count,
                    "child_count": artifact.child_count,
                    "warnings": list(artifact.warnings) or None,
                    "updated_at": at,
                },
            )
        )
