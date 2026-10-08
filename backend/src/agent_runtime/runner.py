"""Agent 单次会话执行器：驱动图运行、处理流式事件与状态持久化。"""

from __future__ import annotations

import asyncio
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import uuid4

import structlog

from agent_runtime.events import (
    AnswerDelta,
    ServerSentEvent,
    answer_delta,
    citation,
    run_completed,
    run_failed,
    run_started,
)
from agent_runtime.graph import recursion_limit
from agent_runtime.state import RetrievalScope, initial_state
from domain.conversation import MessageStatus
from domain.retrieval import EvidenceStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from uuid import UUID

    from langchain_core.runnables import RunnableConfig
    from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]

    from agent_runtime.state import AgentState, RunContext
    from domain.conversation import Conversation


class RunTracing(Protocol):
    """单次运行的链路追踪协议。"""

    def start(
        self,
        *,
        name: str,
        metadata: Mapping[str, object],
        trace_id: str | None = None,
        input_text: str | None = None,
    ) -> Any | None: ...

    def finish(
        self,
        observation: Any | None,
        *,
        output_text: str | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> None: ...


log = structlog.get_logger(__name__)

# 单帧携带的最大错误消息字符数
_MAX_ERROR_CHARS = 500

# 日志携带的最大异常调用栈字符数
_MAX_ERROR_STACK_CHARS = 4000


def _error_stack(error: BaseException) -> str:
    """提取截断后的异常调用栈摘要。"""
    formatted = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    return formatted[-_MAX_ERROR_STACK_CHARS:]


@dataclass(frozen=True, slots=True)
class ConversationAgent:
    """会话 Agent 运行时封装。"""

    graph: CompiledStateGraph[AgentState, RunContext, AgentState, AgentState]
    context: RunContext
    run_timeout_seconds: int
    tracing: RunTracing

    async def run(
        self,
        *,
        conversation_id: UUID,
        user_id: UUID,
        question: str,
    ) -> AsyncIterator[ServerSentEvent]:
        """校验会话归属权并返回该运行的事件流。"""
        conversation = await self.context.conversations.find(
            owner_id=user_id,
            conversation_id=conversation_id,
        )
        return self._stream(conversation=conversation, question=question)

    async def _stream(
        self,
        *,
        conversation: Conversation,
        question: str,
    ) -> AsyncIterator[ServerSentEvent]:
        """驱动图流程并产出 SSE 事件流。"""
        thread_id = str(conversation.id)
        run_id = uuid4().hex
        structlog.contextvars.bind_contextvars(run_id=run_id, conversation_id=thread_id)
        terminal = "cancelled"
        answer = ""
        message_id: UUID | None = None
        # 运行链路跟踪记录
        observation = self.tracing.start(
            name="agent.run",
            trace_id=run_id,
            input_text=question,
            metadata={
                "run_id": run_id,
                "conversation_id": str(conversation.id),
                "knowledge_base_id": str(conversation.knowledge_base_id),
                "user_id": str(conversation.owner_id),
                "max_retrieval_rounds": (self.context.retrieval.budget.max_retrieval_rounds),
            },
        )
        try:
            try:
                user_message, assistant_message = await self.context.conversations.append_turn(
                    conversation_id=conversation.id,
                    question=question,
                )
                message_id = assistant_message.id
                log.info(
                    "智能体运行开始",
                    user_message_id=str(user_message.id),
                    question_chars=len(question),
                )
                yield run_started(
                    run_id=run_id,
                    conversation_id=conversation.id,
                    user_message_id=user_message.id,
                    assistant_message_id=assistant_message.id,
                )
                async for mode, payload in self._stream_graph(
                    conversation=conversation,
                    question=question,
                    thread_id=thread_id,
                    run_id=run_id,
                ):
                    if mode == "custom" and isinstance(payload, AnswerDelta):
                        answer += payload.text
                        yield answer_delta(payload.text)
            except asyncio.CancelledError:
                # 客户端断开连接，使用 shield 保护部分回答的持久化，不吞掉取消异常
                if message_id is not None:
                    await self._persist_cancelled(message_id, answer)
                raise
            except Exception as error:
                terminal = "failed"
                await self._persist_failed(message_id, answer, error)
                self.tracing.finish(
                    observation,
                    output_text=answer,
                    error_class=type(error).__name__,
                    error_message=str(error),
                )
                yield run_failed(
                    message_id=message_id,
                    error_class=type(error).__name__,
                    message=str(error)[:_MAX_ERROR_CHARS],
                )
                return

            final = await self._final_state(thread_id)
            answer_text = str(final.get("answer") or answer)
            # 读取检索结果记录与证据状态
            record = final.get("retrieval")
            evidence_status = (
                record.evidence.status if record is not None else EvidenceStatus.INSUFFICIENT
            )
            rounds = int(final.get("rounds") or 0)
            citations = tuple(final.get("citations") or ())
            await self.context.conversations.finish_turn(
                message_id=message_id,
                content=answer_text,
                status=MessageStatus.COMPLETED,
                evidence_status=evidence_status,
                retrieval_rounds=rounds,
                intent=final.get("intent"),
                finish_reason=final.get("finish_reason"),
                citations=citations,
            )
            stored = await self.context.conversations.citations_for_message(message_id)
            for stored_citation in stored:
                yield citation(stored_citation)
            terminal = "completed"
            self.tracing.finish(
                observation,
                output_text=answer_text,
            )
            yield run_completed(
                message_id=message_id,
                answer=answer_text,
                citations=stored,
                evidence_status=evidence_status,
                retrieval_rounds=rounds,
                intent=final.get("intent"),
                finish_reason=final.get("finish_reason"),
                removed_citation_ids=tuple(final.get("removed_citation_ids") or ()),
            )
        finally:
            if terminal == "cancelled":
                self.tracing.finish(
                    observation,
                    output_text=answer,
                    error_class="CancelledError",
                    error_message="客户端主动断开连接",
                )
            log.info(
                "智能体运行结束",
                terminal=terminal,
                answer_chars=len(answer),
                message_id=str(message_id) if message_id is not None else None,
            )
            structlog.contextvars.unbind_contextvars("run_id", "conversation_id")

    async def _stream_graph(
        self,
        *,
        conversation: Conversation,
        question: str,
        thread_id: str,
        run_id: str,
    ) -> AsyncIterator[tuple[str, object]]:
        """执行图并以 (mode, payload) 形式输出流式片元。"""
        scope = RetrievalScope(
            knowledge_base_id=conversation.knowledge_base_id,
            budget=self.context.retrieval.budget,
        )
        state = initial_state(
            request_id=run_id,
            conversation_id=conversation.id,
            user_id=conversation.owner_id,
            question=question,
            scope=scope,
        )
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": recursion_limit(scope.budget.max_retrieval_rounds),
        }
        async with asyncio.timeout(self.run_timeout_seconds):
            async for chunk in self._stream_chunks(state, config=config):
                pair = cast(
                    "tuple[object, object] | None",
                    chunk if isinstance(chunk, tuple) else None,
                )
                if pair is None:
                    continue
                mode, payload = pair
                yield str(mode), payload

    def _stream_chunks(
        self,
        state: AgentState,
        *,
        config: RunnableConfig,
    ) -> AsyncIterator[Any]:
        """获取状态图执行流。"""
        return self.graph.astream(  # pyright: ignore[reportUnknownMemberType]
            state,
            config=config,
            context=self.context,
            stream_mode=["custom", "updates"],
        )

    async def _final_state(self, thread_id: str) -> AgentState:
        """从检查点读取最终状态。"""
        snapshot = await self.graph.aget_state(  # pyright: ignore[reportUnknownMemberType]
            {"configurable": {"thread_id": thread_id}}
        )
        return cast("AgentState", snapshot.values)

    async def _persist_cancelled(self, message_id: UUID, answer: str) -> None:
        """持久化取消状态下的部分文本输出。"""
        try:
            await asyncio.shield(
                self.context.conversations.finish_turn(
                    message_id=message_id,
                    content=answer,
                    status=MessageStatus.CANCELLED,
                )
            )
        except asyncio.CancelledError:
            # 规避二次取消打断持久化
            log.warning("智能体取消状态已独立持久化", message_id=str(message_id))
        except Exception as error:
            log.error(
                "智能体取消状态持久化失败",
                message_id=str(message_id),
                error_class=type(error).__name__,
            )

    async def _persist_failed(
        self,
        message_id: UUID | None,
        answer: str,
        error: BaseException,
    ) -> None:
        """持久化运行失败状态及已有片元。"""
        log.error(
            "智能体运行失败",
            message_id=str(message_id) if message_id is not None else None,
            error_class=type(error).__name__,
            error=str(error)[:_MAX_ERROR_CHARS],
            error_stack=_error_stack(error),
        )
        if message_id is None:
            return
        try:
            await self.context.conversations.finish_turn(
                message_id=message_id,
                content=answer,
                status=MessageStatus.FAILED,
                error_class=type(error).__name__,
            )
        except Exception as persist_error:
            log.error(
                "智能体失败状态持久化失败",
                message_id=str(message_id),
                error_class=type(persist_error).__name__,
            )
