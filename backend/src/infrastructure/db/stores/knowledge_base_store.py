"""基于 SQLAlchemy 实现知识库目录仓储。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select, update

from domain.cleanup import CleanupKind
from infrastructure.db.mappers.knowledge import to_knowledge_base
from infrastructure.db.models.documents import DocumentRow
from infrastructure.db.models.knowledge_bases import KnowledgeBaseRow
from infrastructure.db.stores.purge import purge_document_versions

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from domain.knowledge import KnowledgeBase


class SqlAlchemyKnowledgeBaseStore:
    """知识库仓储 SQLAlchemy 异步实现。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, knowledge_base: KnowledgeBase) -> None:
        """创建新知识库记录。"""
        async with self._sessions.begin() as session:
            session.add(
                KnowledgeBaseRow(
                    id=knowledge_base.id,
                    owner_id=knowledge_base.owner_id,
                    name=knowledge_base.name,
                    description=knowledge_base.description,
                    created_at=knowledge_base.created_at,
                    updated_at=knowledge_base.updated_at,
                )
            )

    async def list_for_owner(self, owner_id: UUID) -> Sequence[KnowledgeBase]:
        """获取指定用户拥有的所有知识库列表。"""
        async with self._sessions() as session:
            rows = await session.scalars(
                select(KnowledgeBaseRow)
                .where(KnowledgeBaseRow.owner_id == owner_id)
                .order_by(KnowledgeBaseRow.created_at.desc(), KnowledgeBaseRow.id)
            )
        return [to_knowledge_base(row) for row in rows]

    async def find_for_owner(
        self,
        owner_id: UUID,
        knowledge_base_id: UUID,
    ) -> KnowledgeBase | None:
        """查询指定用户拥有的单个知识库。"""
        async with self._sessions() as session:
            row = await session.scalar(
                select(KnowledgeBaseRow).where(
                    KnowledgeBaseRow.id == knowledge_base_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
        return None if row is None else to_knowledge_base(row)

    async def replace(self, knowledge_base: KnowledgeBase) -> KnowledgeBase | None:
        """更新知识库的名称和描述信息。"""
        statement = (
            update(KnowledgeBaseRow)
            .where(
                KnowledgeBaseRow.id == knowledge_base.id,
                KnowledgeBaseRow.owner_id == knowledge_base.owner_id,
            )
            .values(
                name=knowledge_base.name,
                description=knowledge_base.description,
                updated_at=knowledge_base.updated_at,
            )
            .returning(KnowledgeBaseRow)
        )
        async with self._sessions.begin() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        return None if row is None else to_knowledge_base(row)

    async def delete(self, owner_id: UUID, knowledge_base_id: UUID) -> bool:
        """删除知识库及其全部文档、版本与分块，并同步记录待清理意向。"""
        async with self._sessions.begin() as session:
            owned = await session.scalar(
                select(KnowledgeBaseRow.id).where(
                    KnowledgeBaseRow.id == knowledge_base_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
            if owned is None:
                return False
            document_ids = list(
                await session.scalars(
                    select(DocumentRow.id).where(DocumentRow.knowledge_base_id == knowledge_base_id)
                )
            )
            await purge_document_versions(
                session,
                document_ids=document_ids,
                knowledge_base_id=knowledge_base_id,
                kind=CleanupKind.KNOWLEDGE_BASE,
                document_id=None,
            )
            # 文档行由外键的 CASCADE 跟随知识库行一起删除。
            await session.execute(
                delete(KnowledgeBaseRow).where(
                    KnowledgeBaseRow.id == knowledge_base_id,
                    KnowledgeBaseRow.owner_id == owner_id,
                )
            )
            return True
