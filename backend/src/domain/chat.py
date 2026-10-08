"""大模型对话领域模型与异常定义。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChatRole(StrEnum):
    """对话角色"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """单条输入消息"""

    role: ChatRole
    content: str


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    """非流式对话响应结果"""

    text: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ChatDelta:
    """流式增量文本块"""

    text: str = ""
    finish_reason: str | None = None


class ChatError(Exception):
    """模型对话基础异常"""


class ChatRejectedError(ChatError):
    """模型服务明确拒绝（鉴权失败、配额不足或请求格式非法等非偶发错误）"""


class TransientChatError(ChatError):
    """模型服务瞬时故障（网络超时、限流或 5xx，可重试）"""


class ChatStreamInterruptedError(TransientChatError):
    """流式传输异常中断（未收到终止帧）"""


class ChatShapeError(ChatRejectedError):
    """模型响应体结构不符合预期"""
