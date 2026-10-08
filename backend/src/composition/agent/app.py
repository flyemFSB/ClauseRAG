"""Agent 运行时 HTTP 服务应用装配。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI

from agent_runtime.checkpointer import GraphCheckpoints
from agent_runtime.graph import build_agent_graph
from agent_runtime.runner import ConversationAgent
from api.conversations import (
    create_conversations_router,
    get_conversation_agent,
    get_conversation_service,
    get_knowledge_base_service,
    get_query_understanding_service,
    get_retrieval_service,
)
from api.health import create_health_router
from composition.api.app import bind, install_shared

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from composition.agent.runtime import AgentRuntime


def create_agent_app(runtime: AgentRuntime) -> FastAPI:
    """构建 Agent 运行时 FastAPI 应用，装配生命周期管理与对话路由。"""
    log = structlog.get_logger(__name__)
    settings = runtime.settings

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        checkpoints = await GraphCheckpoints.open(
            dsn=runtime.checkpoints_dsn,
            max_connections=runtime.checkpoints_pool_size,
        )
        graph = build_agent_graph(checkpointer=checkpoints.saver)
        bind(
            app,
            get_conversation_agent,
            ConversationAgent(
                graph=graph,
                context=runtime.context,
                run_timeout_seconds=settings.answer_timeout_seconds,
                tracing=runtime.tracing,
            ),
        )
        log.info(
            "Agent运行时进程启动",
            nodes=len(graph.get_graph().nodes),
            max_retrieval_rounds=runtime.context.retrieval.budget.max_retrieval_rounds,
        )
        try:
            yield
        finally:
            await checkpoints.close()
            await runtime.close()
            log.info("Agent运行时进程停止")

    app = FastAPI(title="RAG platform agent runtime", version="0.1.0", lifespan=lifespan)
    install_shared(app)
    bind(app, get_conversation_service, runtime.context.conversations)
    bind(app, get_knowledge_base_service, runtime.knowledge_bases)
    bind(app, get_query_understanding_service, runtime.context.understanding)
    bind(app, get_retrieval_service, runtime.context.retrieval)
    app.include_router(create_health_router(runtime.health))
    app.include_router(create_conversations_router())
    return app
