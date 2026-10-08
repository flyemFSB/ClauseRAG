"""对话管理与轮次持久化应用服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from domain.conversation import (
    Conversation,
    Message,
    MessageRole,
    MessageStatus,
)
from domain.knowledge import KnowledgeNotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from application.knowledge.knowledge_bases import KnowledgeBaseStore
    from domain.conversation import CitationRecord, ConversationDetail
    from domain.retrieval import EvidenceStatus

DEFAULT_TITLE = "新对话"
MAX_TITLE_CHARS = 200


class ConversationStore(Protocol):
    """对话与消息存储持久化协议"""

    async def create(self, conversation: Conversation) -> None: ...

    async def list_for_owner(self, owner_id: UUID) -> Sequence[Conversation]:
        """按更新时间倒序列出指定用户的所有对话"""
        ...

    async def find_for_owner(
        self,
        owner_id: UUID,
        conversation_id: UUID,
    ) -> Conversation | None: ...

    async def rename(
        self,
        owner_id: UUID,
        conversation_id: UUID,
        *,
        title: str,
        at: datetime,
    ) -> Conversation | None:
        """重命名对话标题"""
        ...

    async def find_detail(
        self,
        owner_id: UUID,
        conversation_id: UUID,
    ) -> ConversationDetail | None:
        """获取包含历史消息及引用详情的完整对话"""
        ...

    async def history(
        self,
        owner_id: UUID,
        conversation_id: UUID,
        *,
        limit: int,
    ) -> Sequence[Message]:
        """获取指定数量的最近已完成历史消息（用于提示词组装）"""
        ...

    async def delete(self, owner_id: UUID, conversation_id: UUID) -> bool:
        """删除指定对话"""
        ...

    async def append_turn(self, user_message: Message, assistant_message: Message) -> None:
        """单事务追加用户提问消息与流式占位助手消息"""
        ...

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
        """在生成结束时更新助手消息的终态、执行诊断与引用记录"""
        ...

    async def citations_for_message(self, message_id: UUID) -> Sequence[CitationRecord]:
        """查询指定消息关联的持久化引用列表"""
        ...


class ConversationService:
    """对话生命周期与会话轮次应用服务"""

    def __init__(
        self,
        *,
        conversations: ConversationStore,
        knowledge_bases: KnowledgeBaseStore,
    ) -> None:
        self._conversations = conversations
        self._knowledge_bases = knowledge_bases

    async def create(
        self,
        *,
        owner_id: UUID,
        knowledge_base_id: UUID,
        title: str | None = None,
    ) -> Conversation:
        """在指定知识库下创建新对话"""
        knowledge_base = await self._knowledge_bases.find_for_owner(owner_id, knowledge_base_id)
        if knowledge_base is None:
            raise KnowledgeNotFoundError("knowledge_base", knowledge_base_id)
        now = datetime.now(UTC)
        conversation = Conversation(
            id=uuid4(),
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            title=self._title(title),
            created_at=now,
            updated_at=now,
        )
        await self._conversations.create(conversation)
        return conversation

    async def list_for_owner(self, *, owner_id: UUID) -> Sequence[Conversation]:
        """获取当前用户的全部对话列表"""
        return await self._conversations.list_for_owner(owner_id)

    async def find(self, *, owner_id: UUID, conversation_id: UUID) -> Conversation:
        """查找指定对话概览（不加载历史消息）"""
        conversation = await self._conversations.find_for_owner(owner_id, conversation_id)
        if conversation is None:
            raise KnowledgeNotFoundError("conversation", conversation_id)
        return conversation

    async def get(self, *, owner_id: UUID, conversation_id: UUID) -> ConversationDetail:
        """获取对话详情（包含历史消息及引用）"""
        detail = await self._conversations.find_detail(owner_id, conversation_id)
        if detail is None:
            raise KnowledgeNotFoundError("conversation", conversation_id)
        return detail

    async def rename(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID,
        title: str,
    ) -> Conversation:
        """更新对话标题"""
        renamed = await self._conversations.rename(
            owner_id,
            conversation_id,
            title=self._title(title),
            at=datetime.now(UTC),
        )
        if renamed is None:
            raise KnowledgeNotFoundError("conversation", conversation_id)
        return renamed

    async def delete(self, *, owner_id: UUID, conversation_id: UUID) -> None:
        """删除对话"""
        if not await self._conversations.delete(owner_id, conversation_id):
            raise KnowledgeNotFoundError("conversation", conversation_id)

    async def history(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID,
        limit: int,
    ) -> Sequence[Message]:
        """获取最近的历史对话消息"""
        return await self._conversations.history(owner_id, conversation_id, limit=limit)

    async def append_turn(
        self,
        *,
        conversation_id: UUID,
        question: str,
    ) -> tuple[Message, Message]:
        """开启新轮次提问，持久化用户消息并创建流式待处理助手消息"""
        now = datetime.now(UTC)
        user_message = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=question,
            status=MessageStatus.COMPLETED,
            created_at=now,
            updated_at=now,
        )
        assistant_message = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content="",
            status=MessageStatus.STREAMING,
            created_at=now,
            updated_at=now,
        )
        await self._conversations.append_turn(user_message, assistant_message)
        return user_message, assistant_message

    async def finish_turn(
        self,
        *,
        message_id: UUID,
        content: str,
        status: MessageStatus,
        evidence_status: EvidenceStatus | None = None,
        retrieval_rounds: int | None = None,
        intent: str | None = None,
        finish_reason: str | None = None,
        error_class: str | None = None,
        citations: Sequence[CitationRecord] = (),
    ) -> bool:
        """结束提问轮次，结算助手消息与引用记录"""
        return await self._conversations.finish_message(
            message_id,
            content=content,
            status=status,
            evidence_status=evidence_status,
            retrieval_rounds=retrieval_rounds,
            intent=intent,
            finish_reason=finish_reason,
            error_class=error_class,
            citations=citations,
            at=datetime.now(UTC),
        )

    async def citations_for_message(self, message_id: UUID) -> Sequence[CitationRecord]:
        """读取指定消息的引用记录"""
        return await self._conversations.citations_for_message(message_id)

    @staticmethod
    def _title(title: str | None) -> str:
        """处理标题字符串（修剪空白与超长字符，空值设为默认标题）"""
        if title is None:
            return DEFAULT_TITLE
        trimmed = title.strip()[:MAX_TITLE_CHARS]
        return trimmed or DEFAULT_TITLE
