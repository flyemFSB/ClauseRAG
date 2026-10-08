"""Agent 运行时状态机模型定义。"""

from __future__ import annotations

# ruff: noqa: TC001, TC003
# LangGraph 需反射类型注解构建 Schema，必须保留运行时导入
from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID

from application.agent.answer import AnswerService
from application.agent.query_understanding import QueryUnderstandingService
from application.conversations.service import ConversationService
from application.retrieval.citations import CitationService
from application.retrieval.models import RetrievalRecord
from application.retrieval.service import RetrievalService
from domain.conversation import CitationRecord, Message
from domain.retrieval import RetrievalBudget


@dataclass(frozen=True, slots=True)
class RetrievalScope:
    """检索范围与轮次预算配置。"""

    knowledge_base_id: UUID
    budget: RetrievalBudget


@dataclass(frozen=True, slots=True)
class RunContext:
    """单次运行的外部依赖协作上下文。"""

    conversations: ConversationService
    understanding: QueryUnderstandingService
    retrieval: RetrievalService
    answers: AnswerService
    citations: CitationService
    history_messages: int


class AgentState(TypedDict):
    """LangGraph 状态字典模型。"""

    # 会话与请求标识
    request_id: str
    conversation_id: UUID
    user_id: UUID

    # 查询与意图识别
    original_query: str
    history: tuple[Message, ...]
    intent: str | None
    route: str | None
    rewritten_queries: tuple[str, ...]

    # 检索轮次与结果上下文
    retrieval_scope: RetrievalScope
    rounds: int
    retrieval: RetrievalRecord | None

    # 回答与引用结果
    answer: str
    finish_reason: str | None
    citations: tuple[CitationRecord, ...]
    removed_citation_ids: tuple[str, ...]


def initial_state(
    *,
    request_id: str,
    conversation_id: UUID,
    user_id: UUID,
    question: str,
    scope: RetrievalScope,
) -> AgentState:
    """构造状态机初始状态字典。"""
    return AgentState(
        request_id=request_id,
        conversation_id=conversation_id,
        user_id=user_id,
        original_query=question,
        history=(),
        intent=None,
        route=None,
        rewritten_queries=(),
        retrieval_scope=scope,
        rounds=0,
        retrieval=None,
        answer="",
        finish_reason=None,
        citations=(),
        removed_citation_ids=(),
    )
