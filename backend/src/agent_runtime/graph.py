"""LangGraph Agent 拓扑构建与节点路由。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

# 忽略 LangGraph 内部缺失的类型存根
from langgraph.graph import END, START, StateGraph  # pyright: ignore[reportMissingTypeStubs]

from agent_runtime.events import AnswerDelta
from agent_runtime.state import AgentState, RunContext
from domain.query import QueryIntent, QueryRoute, route_for
from domain.retrieval import EvidenceStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from typing import Any

    from langgraph.checkpoint.base import (
        BaseCheckpointSaver,  # pyright: ignore[reportMissingTypeStubs]
    )
    from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
    from langgraph.runtime import Runtime  # pyright: ignore[reportMissingTypeStubs]

    from application.retrieval.models import RetrievalRecord
    from domain.chat import ChatDelta


def _record(state: AgentState) -> RetrievalRecord:
    """获取当前轮次的检索结果记录。"""
    record = state["retrieval"]
    if record is None:
        raise RuntimeError("检索节点尚未运行")
    return record


async def load_context(state: AgentState, runtime: Runtime[RunContext]) -> dict[str, object]:
    """加载历史对话上下文。"""
    history = await runtime.context.conversations.history(
        owner_id=state["user_id"],
        conversation_id=state["conversation_id"],
        limit=runtime.context.history_messages,
    )
    return {"history": tuple(history)}


async def understand_query(state: AgentState, runtime: Runtime[RunContext]) -> dict[str, object]:
    """分析用户意图并生成多路检索查询词。"""
    understanding = await runtime.context.understanding.understand(
        question=state["original_query"],
        history=state["history"],
    )
    return {
        "intent": understanding.intent.value,
        "rewritten_queries": understanding.queries,
    }


async def route_query(state: AgentState, runtime: Runtime[RunContext]) -> dict[str, object]:
    """根据意图分类判定后续执行路由。"""
    del runtime
    intent = state["intent"]
    if intent is None:
        return {"route": QueryRoute.PLAN_RETRIEVAL.value}
    return {"route": route_for(QueryIntent(intent)).value}


async def plan_retrieval(state: AgentState, runtime: Runtime[RunContext]) -> dict[str, object]:
    """累加检索轮次计数器。"""
    del runtime
    return {"rounds": state["rounds"] + 1}


async def retrieve(state: AgentState, runtime: Runtime[RunContext]) -> dict[str, object]:
    """执行混合检索并暂存检索上下文。"""
    scope = state["retrieval_scope"]
    queries = state["rewritten_queries"] or (state["original_query"],)
    result = await runtime.context.retrieval.retrieve(
        knowledge_base_id=scope.knowledge_base_id,
        query=queries[0],
        rewritten_queries=queries,
    )
    return {"retrieval": result.record}


async def rewrite_once(state: AgentState, runtime: Runtime[RunContext]) -> dict[str, object]:
    """证据不足时改写查询并准备重试检索。"""
    queries = await runtime.context.understanding.rewrite(
        question=state["original_query"],
        history=state["history"],
        previous=state["rewritten_queries"],
    )
    return {"rewritten_queries": queries}


async def generate(state: AgentState, runtime: Runtime[RunContext]) -> dict[str, object]:
    """基于检索上下文流式生成带引用的回答。"""
    return await _stream_answer(
        runtime,
        stream=runtime.context.answers.stream_grounded(
            question=state["original_query"],
            context=_record(state).context,
            history=state["history"],
        ),
    )


async def direct_response(state: AgentState, runtime: Runtime[RunContext]) -> dict[str, object]:
    """闲聊或通用问题直接流式回复。"""
    return await _stream_answer(
        runtime,
        stream=runtime.context.answers.stream_direct(
            question=state["original_query"],
            history=state["history"],
        ),
    )


async def ask_clarification(state: AgentState, runtime: Runtime[RunContext]) -> dict[str, object]:
    """问题歧义时流式输出追问澄清信息。"""
    return await _stream_answer(
        runtime,
        stream=runtime.context.answers.stream_clarification(
            question=state["original_query"],
            history=state["history"],
        ),
    )


async def abstain(state: AgentState, runtime: Runtime[RunContext]) -> dict[str, object]:
    """无匹配内容或证据质量不可核验时的确定性拒答。"""
    status = _record(state).evidence.status
    return {"answer": runtime.context.answers.abstention(status)}


async def validate_citations(
    state: AgentState,
    runtime: Runtime[RunContext],
) -> dict[str, object]:
    """校验回答中的引用标记并绑定切块元数据，无引用时把证据判定降为未验证。"""
    record = _record(state)
    resolved = await runtime.context.citations.resolve(
        knowledge_base_id=state["retrieval_scope"].knowledge_base_id,
        answer=state["answer"],
        sources=record.sources,
    )
    retrieval = record
    if not resolved.covered:
        retrieval = replace(
            record,
            evidence=replace(
                record.evidence,
                status=EvidenceStatus.UNVERIFIED,
                reason="the answer carried no verifiable citation",
            ),
        )
    return {
        "answer": resolved.text,
        "citations": resolved.citations,
        "removed_citation_ids": resolved.removed_ids,
        "retrieval": retrieval,
    }


async def _stream_answer(
    runtime: Runtime[RunContext],
    *,
    stream: AsyncIterator[ChatDelta],
) -> dict[str, object]:
    """读取模型流式片元并转发至自定义事件流。"""
    text = ""
    finish_reason: str | None = None
    async for delta in stream:
        if delta.text:
            text += delta.text
            runtime.stream_writer(AnswerDelta(text=delta.text))
        if delta.finish_reason is not None:
            finish_reason = delta.finish_reason
    return {"answer": text, "finish_reason": finish_reason}


def route_after_route_query(state: AgentState) -> str:
    """根据意图路由结果决定跳转目标节点。"""
    route = state["route"]
    return route if route else QueryRoute.PLAN_RETRIEVAL.value


def route_after_retrieve(state: AgentState) -> str:
    """评估检索证据：核验不可用直接拒答，证据不足改写重试，核验通过则生成。"""
    evidence = _record(state).evidence
    # 重排故障不是证据不足：改写查询会重复打到同一个不可用的供应商，直接拒答
    if evidence.status is EvidenceStatus.DEGRADED:
        return "abstain"
    if evidence.grounded:
        return "generate"
    if state["rounds"] < state["retrieval_scope"].budget.max_retrieval_rounds:
        return "rewrite_once"
    return "abstain"


def recursion_limit(max_retrieval_rounds: int) -> int:
    """根据最大检索轮次计算 LangGraph 递归上限深度。"""
    return 6 + 3 * max_retrieval_rounds


def _register(
    graph: StateGraph[AgentState, RunContext, AgentState, AgentState],
    name: str,
    node: Callable[..., Any],
) -> None:
    graph.add_node(name, node)  # pyright: ignore[reportUnknownMemberType]


def build_agent_graph(
    *,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> CompiledStateGraph[AgentState, RunContext, AgentState, AgentState]:
    """编译 Agent 状态执行图，可选择性绑定检查点存储。"""
    graph: StateGraph[AgentState, RunContext, AgentState, AgentState] = StateGraph(
        AgentState,
        context_schema=RunContext,
    )
    _register(graph, "load_context", load_context)
    _register(graph, "understand_query", understand_query)
    _register(graph, "route_query", route_query)
    _register(graph, "plan_retrieval", plan_retrieval)
    _register(graph, "retrieve", retrieve)
    _register(graph, "rewrite_once", rewrite_once)
    _register(graph, "generate", generate)
    _register(graph, "validate_citations", validate_citations)
    _register(graph, "direct_response", direct_response)
    _register(graph, "ask_clarification", ask_clarification)
    _register(graph, "abstain", abstain)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "understand_query")
    graph.add_edge("understand_query", "route_query")
    graph.add_conditional_edges(
        "route_query",
        route_after_route_query,
        {
            QueryRoute.DIRECT_RESPONSE.value: "direct_response",
            QueryRoute.ASK_CLARIFICATION.value: "ask_clarification",
            QueryRoute.PLAN_RETRIEVAL.value: "plan_retrieval",
        },
    )
    graph.add_edge("plan_retrieval", "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {
            "generate": "generate",
            "rewrite_once": "rewrite_once",
            "abstain": "abstain",
        },
    )
    graph.add_edge("rewrite_once", "plan_retrieval")
    graph.add_edge("generate", "validate_citations")
    graph.add_edge("validate_citations", END)
    graph.add_edge("direct_response", END)
    graph.add_edge("ask_clarification", END)
    graph.add_edge("abstain", END)

    return graph.compile(checkpointer=checkpointer)  # pyright: ignore[reportUnknownMemberType]
