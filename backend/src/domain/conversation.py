"""对话会话、消息与引用持久化实体模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from uuid import UUID

    from domain.retrieval import EvidenceStatus


class MessageRole(StrEnum):
    """消息发送方角色"""

    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(StrEnum):
    """消息处理生命周期状态"""

    STREAMING = "streaming"
    """流式生成中"""

    COMPLETED = "completed"
    """已正常完成"""

    FAILED = "failed"
    """生成失败"""

    CANCELLED = "cancelled"
    """已取消中断"""


@dataclass(frozen=True, slots=True)
class Conversation:
    """对话会话实体"""

    id: UUID
    owner_id: UUID
    knowledge_base_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CitationRecord:
    """持久化引用记录"""

    citation_id: str
    child_id: UUID
    parent_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_name: str
    heading_path: tuple[str, ...]
    line_start: int
    line_end: int
    quote: str


@dataclass(frozen=True, slots=True)
class Message:
    """对话轮次消息实体"""

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    status: MessageStatus
    created_at: datetime
    updated_at: datetime
    evidence_status: EvidenceStatus | None = None
    retrieval_rounds: int | None = None
    intent: str | None = None
    finish_reason: str | None = None
    error_class: str | None = None
    citations: Sequence[CitationRecord] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ConversationDetail:
    """包含历史消息与引用的完整会话详情"""

    conversation: Conversation
    messages: Sequence[Message]
