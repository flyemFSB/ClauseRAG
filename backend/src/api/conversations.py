"""对话、流式智能体执行与检索调试路由。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from agent_runtime.runner import ConversationAgent
from api.agent_schemas import (
    AskRequest,
    ConversationDetailResponse,
    ConversationResponse,
    CreateConversationRequest,
    RenameConversationRequest,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
)
from application.agent.query_understanding import QueryUnderstandingService
from application.conversations.service import ConversationService
from application.knowledge.knowledge_bases import KnowledgeBaseService
from application.retrieval.service import RetrievalService
from domain.identity import PLATFORM_OWNER_ID


def get_conversation_service() -> ConversationService:
    """获取对话应用服务"""
    raise RuntimeError("会话服务未绑定至当前应用实例")


def get_knowledge_base_service() -> KnowledgeBaseService:
    """获取知识库应用服务"""
    raise RuntimeError("知识库服务未绑定至当前应用实例")


def get_query_understanding_service() -> QueryUnderstandingService:
    """获取查询理解服务"""
    raise RuntimeError("查询意图分类器未绑定至当前应用实例")


def get_retrieval_service() -> RetrievalService:
    """获取检索应用服务"""
    raise RuntimeError("检索服务未绑定至当前应用实例")


def get_conversation_agent() -> ConversationAgent:
    """获取对话智能体执行引擎"""
    raise RuntimeError("会话智能体未绑定至当前应用实例")


ConversationServiceDependency = Annotated[ConversationService, Depends(get_conversation_service)]
KnowledgeBaseServiceDependency = Annotated[
    KnowledgeBaseService, Depends(get_knowledge_base_service)
]
UnderstandingDependency = Annotated[
    QueryUnderstandingService,
    Depends(get_query_understanding_service),
]
RetrievalDependency = Annotated[RetrievalService, Depends(get_retrieval_service)]
ConversationAgentDependency = Annotated[ConversationAgent, Depends(get_conversation_agent)]


def create_conversations_router() -> APIRouter:
    """构建对话与问答路由"""
    router = APIRouter(prefix="/api/v1", tags=["chat"])

    @router.post(
        "/knowledge-bases/{knowledge_base_id}/conversations",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_conversation(
        knowledge_base_id: UUID,
        payload: CreateConversationRequest,
        conversations: ConversationServiceDependency,
    ) -> ConversationResponse:
        """在指定知识库下创建新对话"""
        conversation = await conversations.create(
            owner_id=PLATFORM_OWNER_ID,
            knowledge_base_id=knowledge_base_id,
            title=payload.title,
        )
        return ConversationResponse.from_conversation(conversation)

    @router.get("/conversations")
    async def list_conversations(
        conversations: ConversationServiceDependency,
    ) -> list[ConversationResponse]:
        """获取全部对话列表"""
        return [
            ConversationResponse.from_conversation(conversation)
            for conversation in await conversations.list_for_owner(owner_id=PLATFORM_OWNER_ID)
        ]

    @router.get("/conversations/{conversation_id}")
    async def get_conversation(
        conversation_id: UUID,
        conversations: ConversationServiceDependency,
    ) -> ConversationDetailResponse:
        """获取对话详情（包含历史消息及引用信息）"""
        detail = await conversations.get(
            owner_id=PLATFORM_OWNER_ID,
            conversation_id=conversation_id,
        )
        return ConversationDetailResponse.from_detail(detail)

    @router.patch("/conversations/{conversation_id}")
    async def rename_conversation(
        conversation_id: UUID,
        payload: RenameConversationRequest,
        conversations: ConversationServiceDependency,
    ) -> ConversationResponse:
        """重命名对话标题"""
        renamed = await conversations.rename(
            owner_id=PLATFORM_OWNER_ID,
            conversation_id=conversation_id,
            title=payload.title,
        )
        return ConversationResponse.from_conversation(renamed)

    @router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_conversation(
        conversation_id: UUID,
        conversations: ConversationServiceDependency,
    ) -> None:
        """删除对话及其历史消息与引用"""
        await conversations.delete(owner_id=PLATFORM_OWNER_ID, conversation_id=conversation_id)

    @router.post("/conversations/{conversation_id}/messages")
    async def ask(
        conversation_id: UUID,
        payload: AskRequest,
        agent: ConversationAgentDependency,
    ) -> StreamingResponse:
        """流式提问并返回 SSE 事件流"""
        events = await agent.run(
            conversation_id=conversation_id,
            user_id=PLATFORM_OWNER_ID,
            question=payload.content,
        )

        async def frames() -> AsyncIterator[bytes]:
            async for event in events:
                yield event.encode()

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/retrieval-debug/query")
    async def retrieval_debug(
        payload: RetrievalDebugRequest,
        knowledge_bases: KnowledgeBaseServiceDependency,
        understanding: UnderstandingDependency,
        retrieval: RetrievalDependency,
    ) -> RetrievalDebugResponse:
        """单次检索调试探针（返回各渠道召回、融合、重排与门控详情）"""
        await knowledge_bases.get(
            owner_id=PLATFORM_OWNER_ID,
            knowledge_base_id=payload.knowledge_base_id,
        )
        classified = await understanding.understand(question=payload.query)
        # 非检索意图下分类器不做改写，查询列表可以为空；这个端点始终要跑一轮真实检索，所以和
        # agent 的 retrieve 节点用同一条兜底：没有改写就用原问题。
        queries = classified.queries or (payload.query,)
        result = await retrieval.retrieve(
            knowledge_base_id=payload.knowledge_base_id,
            query=queries[0],
            rewritten_queries=queries,
        )
        return RetrievalDebugResponse.from_result(
            result,
            query=payload.query,
            queries=list(queries),
            intent=classified.intent.value,
        )

    return router
