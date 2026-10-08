"""知识库 CRUD 管理应用服务。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from domain.knowledge import KnowledgeBase, KnowledgeNotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID


class KnowledgeBaseStore(Protocol):
    """知识库存储持久化协议"""

    async def create(self, knowledge_base: KnowledgeBase) -> None: ...

    async def list_for_owner(self, owner_id: UUID) -> Sequence[KnowledgeBase]: ...

    async def find_for_owner(
        self,
        owner_id: UUID,
        knowledge_base_id: UUID,
    ) -> KnowledgeBase | None: ...

    async def replace(self, knowledge_base: KnowledgeBase) -> KnowledgeBase | None:
        """更新知识库实体"""
        ...

    async def delete(self, owner_id: UUID, knowledge_base_id: UUID) -> bool:
        """删除知识库并在同一事务中记录衍生资源清理意图"""
        ...


@dataclass(frozen=True, slots=True)
class KnowledgeBaseChanges:
    """知识库部分更新字段变更载荷"""

    name: str | None = None
    description: str | None = None
    sets_name: bool = False
    sets_description: bool = False


class KnowledgeBaseService:
    """知识库业务管理服务"""

    def __init__(
        self,
        *,
        knowledge_bases: KnowledgeBaseStore,
    ) -> None:
        self._knowledge_bases = knowledge_bases

    async def create(
        self,
        *,
        owner_id: UUID,
        name: str,
        description: str | None,
    ) -> KnowledgeBase:
        """创建新知识库"""
        now = datetime.now(UTC)
        knowledge_base = KnowledgeBase(
            id=uuid4(),
            owner_id=owner_id,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
        )
        await self._knowledge_bases.create(knowledge_base)
        return knowledge_base

    async def list_for_owner(self, owner_id: UUID) -> Sequence[KnowledgeBase]:
        """按更新时间倒序获取用户拥有的知识库列表"""
        return await self._knowledge_bases.list_for_owner(owner_id)

    async def get(self, *, owner_id: UUID, knowledge_base_id: UUID) -> KnowledgeBase:
        """获取单个知识库详情"""
        knowledge_base = await self._knowledge_bases.find_for_owner(owner_id, knowledge_base_id)
        if knowledge_base is None:
            raise KnowledgeNotFoundError("knowledge_base", knowledge_base_id)
        return knowledge_base

    async def update(
        self,
        *,
        owner_id: UUID,
        knowledge_base_id: UUID,
        changes: KnowledgeBaseChanges,
    ) -> KnowledgeBase:
        """按变更载荷更新知识库字段"""
        current = await self.get(owner_id=owner_id, knowledge_base_id=knowledge_base_id)
        updated = replace(
            current,
            name=changes.name if changes.sets_name and changes.name is not None else current.name,
            description=(changes.description if changes.sets_description else current.description),
            updated_at=datetime.now(UTC),
        )
        stored = await self._knowledge_bases.replace(updated)
        if stored is None:
            raise KnowledgeNotFoundError("knowledge_base", knowledge_base_id)
        return stored

    async def delete(self, *, owner_id: UUID, knowledge_base_id: UUID) -> None:
        """删除指定知识库及其全部关联文档与资源"""
        if not await self._knowledge_bases.delete(owner_id, knowledge_base_id):
            raise KnowledgeNotFoundError("knowledge_base", knowledge_base_id)
