"""查询意图分类与检索语句改写服务。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, ValidationError

from domain.chat import ChatError, ChatMessage, ChatRole
from domain.query import (
    MAX_REWRITTEN_QUERIES,
    QueryIntent,
    QueryUnderstanding,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.shared.providers import ChatModel
    from domain.conversation import Message

log = structlog.get_logger(__name__)

_CLASSIFIER_PROMPT = """你是 ClauseRAG 商业合同审查系统的意图分类与检索路由引擎。

根据对话历史与用户最新问题，判断意图并输出检索用的改写查询，只输出一个 JSON 对象：
{"intent": "...", "queries": ["..."], "reason": "..."}

intent 只能取以下三个值之一：
- "retrieval"：需要检索合同知识库中的条款、协议或定义才能回答
  （默认选择，绝大多数合同审查问题都属于这一类）
- "direct_response"：问候、寒暄、纯功能咨询或与合同法律审查无关的通用对话
- "ask_clarification"：问题过于模糊，未指明合同对象或条款范围，无法准确定位条款

queries：用于条款检索的查询语句，最多 2 条，保持原问题的语言与关键法律术语
（如 Limitation of Liability, Indemnification, Governing Law 等）不变；
仅在 intent 为 "retrieval" 时给出，可以是原问题的同义改写或提取核心条款关键词，
但不得改变问题所指。
reason：一句话说明判断依据，可以为空。

只输出 JSON，不要输出解释、代码块标记或任何其他文本。"""

_HISTORY_CHARS = 400

_REWRITE_PROMPT = """你是 ClauseRAG 商业合同审查系统的检索查询改写器。

上一轮检索没有在合同知识库中找到足够相关的条款或资料。
请从法律条款同义词、上下位概念或不同表述角度，为同一个问题给出新的检索查询，
只输出一个 JSON 对象：
{"queries": ["..."]}

要求：
- 最多 2 条查询，保持原问题的语言、关键法律实体与核心术语不变；
- 不要重复已经尝试过的查询，可以是法律同义表述改写
  （例如：“违约责任”可关联“Breach of Contract / Remedies”）、补充条款限定词或拆分问题；
- 不要改变问题所指，不要引入问题中没有的合同实体。

只输出 JSON，不要输出解释或代码块标记。"""


class _Classification(BaseModel):
    """意图分类响应 JSON 解析模型"""

    model_config = ConfigDict(extra="ignore")

    intent: str
    queries: list[str] = []
    reason: str | None = None


class _Rewrite(BaseModel):
    """查询改写响应 JSON 解析模型"""

    model_config = ConfigDict(extra="ignore")

    queries: list[str] = []


class QueryUnderstandingService:
    """用户意图判定与多路检索改写服务"""

    def __init__(
        self,
        *,
        chat: ChatModel,
        max_tokens: int,
        temperature: float,
        json_object: bool = True,
    ) -> None:
        self._chat = chat
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._json_object = json_object

    async def understand(
        self,
        *,
        question: str,
        history: Sequence[Message] = (),
    ) -> QueryUnderstanding:
        """识别用户问题意图与检索词，异常时安全降级"""
        messages = [ChatMessage(role=ChatRole.SYSTEM, content=_CLASSIFIER_PROMPT)]
        if history:
            messages.append(
                ChatMessage(role=ChatRole.USER, content=_render_history(history)),
            )
        messages.append(ChatMessage(role=ChatRole.USER, content=f"用户最新问题：{question}"))
        try:
            completion = await self._chat.complete(
                messages,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                json_object=self._json_object,
            )
        except ChatError as error:
            log.warning("查询意图分类失败，降级回退", error_type=type(error).__name__)
            return QueryUnderstanding.fallback(question, reason=type(error).__name__)
        return self._read(completion.text, question=question)

    async def rewrite(
        self,
        *,
        question: str,
        history: Sequence[Message] = (),
        previous: Sequence[str] = (),
    ) -> tuple[str, ...]:
        """针对召回不充分的问题进行查询语句二次改写"""
        messages = [ChatMessage(role=ChatRole.SYSTEM, content=_REWRITE_PROMPT)]
        if history:
            messages.append(
                ChatMessage(role=ChatRole.USER, content=_render_history(history)),
            )
        messages.append(
            ChatMessage(
                role=ChatRole.USER,
                content=(
                    f"用户问题：{question}\n"
                    f"已尝试的检索查询：{' / '.join(previous) if previous else '(无)'}"
                ),
            )
        )
        try:
            completion = await self._chat.complete(
                messages,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                json_object=self._json_object,
            )
        except ChatError as error:
            log.warning("查询改写失败，沿用原查询", error_type=type(error).__name__)
            return tuple(previous)
        try:
            rewritten = _Rewrite.model_validate_json(_strip_fence(completion.text))
        except (ValueError, ValidationError):
            log.warning(
                "查询改写输出解析失败",
                answer_chars=len(completion.text),
            )
            return tuple(previous)
        queries = tuple(
            query.strip() for query in rewritten.queries[:MAX_REWRITTEN_QUERIES] if query.strip()
        )
        return queries or tuple(previous)

    def _read(self, answer: str, *, question: str) -> QueryUnderstanding:
        """解析模型输出的分类 JSON，格式不符时降级回退"""
        try:
            classification = _Classification.model_validate_json(_strip_fence(answer))
        except (ValueError, ValidationError):
            log.warning("查询意图输出解析失败，降级回退", answer_chars=len(answer))
            return QueryUnderstanding.fallback(question, reason="the classifier answered no JSON")
        try:
            intent = QueryIntent(classification.intent.strip())
        except ValueError:
            log.warning("未知查询意图，降级回退", intent=classification.intent[:64])
            return QueryUnderstanding.fallback(
                question,
                reason=f"unknown intent {classification.intent[:64]}",
            )
        queries = tuple(
            query.strip()
            for query in classification.queries[:MAX_REWRITTEN_QUERIES]
            if query.strip()
        )
        if intent is QueryIntent.RETRIEVAL and not queries:
            queries = (question,)
        return QueryUnderstanding(
            intent=intent,
            queries=queries,
            reason=classification.reason,
        )


def _render_history(history: Sequence[Message]) -> str:
    """截断并渲染多轮历史对话"""
    lines = [
        f"{'用户' if message.role.value == 'user' else '助手'}：{message.content[:_HISTORY_CHARS]}"
        for message in history
    ]
    return "对话历史：\n" + "\n".join(lines)


def _strip_fence(answer: str) -> str:
    """去除输出外层的 Markdown 代码块包裹标记"""
    text = answer.strip()
    if not text.startswith("```"):
        return text
    body = text.split("\n", 1)[1] if "\n" in text else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[: -len("```")]
    return body.strip()
