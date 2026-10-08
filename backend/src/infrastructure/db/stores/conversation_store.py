"""基于 SQLAlchemy 实现会话与问答历史仓储。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete, select, update

from domain.conversation import (
    ConversationDetail,
    Message,
    MessageStatus,
)
from infrastructure.db.mappers.conversations import to_citation, to_conversation, to_message
from infrastructure.db.models.conversations import CitationRow, ConversationRow, MessageRow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from domain.conversation import CitationRecord, Conversation
    from domain.retrieval import EvidenceStatus


class SqlAlchemyConversationStore:
    """会话仓储 SQLAlchemy 异步实现。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, conversation: Conversation) -> None:
        """创建新会话记录。"""
        async with self._sessions.begin() as session:
            session.add(
                ConversationRow(
                    id=conversation.id,
                    owner_id=conversation.owner_id,
                    knowledge_base_id=conversation.knowledge_base_id,
                    title=conversation.title,
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                )
            )

    async def list_for_owner(self, owner_id: UUID) -> Sequence[Conversation]:
        """获取指定用户拥有的所有会话列表（按最近活跃时间倒序）。"""
        statement = (
            select(ConversationRow)
            .where(ConversationRow.owner_id == owner_id)
            .order_by(ConversationRow.updated_at.desc(), ConversationRow.id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).scalars().all()
        return tuple(to_conversation(row) for row in rows)

    async def find_for_owner(
        self,
        owner_id: UUID,
        conversation_id: UUID,
    ) -> Conversation | None:
        """查询指定用户拥有的单个会话。"""
        statement = select(ConversationRow).where(
            ConversationRow.id == conversation_id,
            ConversationRow.owner_id == owner_id,
        )
        async with self._sessions() as session:
            row = await session.scalar(statement)
        return None if row is None else to_conversation(row)

    async def find_detail(
        self,
        owner_id: UUID,
        conversation_id: UUID,
    ) -> ConversationDetail | None:
        """查询会话详情及其包含的所有消息和引文。"""
        async with self._sessions() as session:
            conversation_row = await session.scalar(
                select(ConversationRow).where(
                    ConversationRow.id == conversation_id,
                    ConversationRow.owner_id == owner_id,
                )
            )
            if conversation_row is None:
                return None
            message_rows = (
                (
                    await session.execute(
                        select(MessageRow)
                        .where(MessageRow.conversation_id == conversation_id)
                        .order_by(MessageRow.created_at, MessageRow.id)
                    )
                )
                .scalars()
                .all()
            )
            citations_by_message: dict[UUID, list[CitationRow]] = {}
            if message_rows:
                citation_rows = (
                    (
                        await session.execute(
                            select(CitationRow)
                            .where(CitationRow.message_id.in_([row.id for row in message_rows]))
                            .order_by(CitationRow.created_at, CitationRow.citation_id)
                        )
                    )
                    .scalars()
                    .all()
                )
                for citation in citation_rows:
                    citations_by_message.setdefault(citation.message_id, []).append(citation)
        return ConversationDetail(
            conversation=to_conversation(conversation_row),
            messages=tuple(
                to_message(row, citations_by_message.get(row.id, [])) for row in message_rows
            ),
        )

    async def history(
        self,
        owner_id: UUID,
        conversation_id: UUID,
        *,
        limit: int,
    ) -> Sequence[Message]:
        """获取会话最近的非流式消息历史。"""
        if limit <= 0:
            return ()
        statement = (
            select(MessageRow)
            .join(ConversationRow, ConversationRow.id == MessageRow.conversation_id)
            .where(
                MessageRow.conversation_id == conversation_id,
                ConversationRow.owner_id == owner_id,
                MessageRow.status != MessageStatus.STREAMING.value,
                MessageRow.content != "",
            )
            .order_by(MessageRow.created_at.desc(), MessageRow.id.desc())
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).scalars().all()
        return tuple(to_message(row) for row in reversed(rows))

    async def delete(self, owner_id: UUID, conversation_id: UUID) -> bool:
        """删除指定会话及其关联消息和引文。"""
        async with self._sessions.begin() as session:
            result = await session.execute(
                delete(ConversationRow)
                .where(
                    ConversationRow.id == conversation_id,
                    ConversationRow.owner_id == owner_id,
                )
                .returning(ConversationRow.id)
            )
        return result.scalar_one_or_none() is not None

    async def append_turn(self, user_message: Message, assistant_message: Message) -> None:
        """原子写入一轮问答的用户提问与初始回复记录。"""
        async with self._sessions.begin() as session:
            session.add_all(
                [
                    self._message_row(user_message),
                    self._message_row(assistant_message),
                ]
            )
            await session.execute(
                update(ConversationRow)
                .where(ConversationRow.id == user_message.conversation_id)
                .values(updated_at=user_message.updated_at)
            )

    async def rename(
        self,
        owner_id: UUID,
        conversation_id: UUID,
        *,
        title: str,
        at: datetime,
    ) -> Conversation | None:
        """重命名指定会话标题。"""
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(ConversationRow)
                .where(
                    ConversationRow.id == conversation_id,
                    ConversationRow.owner_id == owner_id,
                )
                .values(title=title, updated_at=at)
                .returning(ConversationRow)
            )
            row = result.scalar_one_or_none()
        return None if row is None else to_conversation(row)

    @staticmethod
    def _message_row(message: Message) -> MessageRow:
        """将领域消息实体映射为数据库行对象。"""
        return MessageRow(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role.value,
            content=message.content,
            status=message.status.value,
            evidence_status=message.evidence_status.value if message.evidence_status else None,
            retrieval_rounds=message.retrieval_rounds,
            intent=message.intent,
            finish_reason=message.finish_reason,
            error_class=message.error_class,
            created_at=message.created_at,
            updated_at=message.updated_at,
        )

    async def finish_message(
        self,
        message_id: UUID,
        *,
        content: str,
        status: MessageStatus,
        evidence_status: EvidenceStatus | None,
        retrieval_rounds: int | None,
        intent: str | None,
        finish_reason: str | None,
        error_class: str | None,
        citations: Sequence[CitationRecord],
        at: datetime,
    ) -> bool:
        """记录模型回复的最终完成状态与解析引文。"""
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(MessageRow)
                .where(
                    MessageRow.id == message_id,
                    MessageRow.status == MessageStatus.STREAMING.value,
                )
                .values(
                    content=content,
                    status=status.value,
                    evidence_status=evidence_status.value if evidence_status else None,
                    retrieval_rounds=retrieval_rounds,
                    intent=intent,
                    finish_reason=finish_reason,
                    error_class=error_class,
                    updated_at=at,
                )
                .returning(MessageRow.id)
            )
            if result.scalar_one_or_none() is None:
                return False
            session.add_all(
                CitationRow(
                    id=uuid4(),
                    message_id=message_id,
                    citation_id=citation.citation_id,
                    child_id=citation.child_id,
                    parent_id=citation.parent_id,
                    document_id=citation.document_id,
                    document_version_id=citation.document_version_id,
                    document_name=citation.document_name,
                    heading_path=list(citation.heading_path),
                    line_start=citation.line_start,
                    line_end=citation.line_end,
                    quote=citation.quote,
                    created_at=at,
                )
                for citation in citations
            )
        return True

    async def citations_for_message(self, message_id: UUID) -> Sequence[CitationRecord]:
        """读取单条消息关联的所有已存储引文。"""
        statement = (
            select(CitationRow)
            .where(CitationRow.message_id == message_id)
            .order_by(CitationRow.citation_id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).scalars().all()
        return tuple(to_citation(row) for row in rows)
