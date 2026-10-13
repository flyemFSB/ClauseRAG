"""对话、流式智能体执行与检索调试路由。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from agent_runtime.runner import ConversationAgent
from api.agent_schemas import (
    AskRequest,
    CachedRetrievalDebug,
    ConversationDetailResponse,
    ConversationResponse,
    CreateConversationRequest,
    RenameConversationRequest,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
)
from api.request_limits import RateLimitGuardDependency, client_host
from application.agent.query_understanding import QueryUnderstandingService
from application.conversations.service import ConversationService
from application.knowledge.contracts import CorpusRevision
from application.knowledge.knowledge_bases import KnowledgeBaseService
from application.retrieval.cache import (
    CACHE_SCHEMA_VERSION,
    CacheRebuildLockPort,
    RetrievalCachePort,
    RetrievalCacheScope,
    cache_key,
)
from application.retrieval.service import RetrievalService
from domain.identity import PLATFORM_OWNER_ID
from domain.retrieval import ChannelStatus, RerankStatus


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


def get_retrieval_cache() -> RetrievalCachePort:
    """获取检索调试缓存"""
    raise RuntimeError("检索调试缓存未绑定至当前应用实例")


def get_cache_rebuild_lock() -> CacheRebuildLockPort:
    """获取检索缓存回源锁"""
    raise RuntimeError("检索缓存回源锁未绑定至当前应用实例")


def get_corpus_revision() -> CorpusRevision:
    """获取可检索语料版本读取器"""
    raise RuntimeError("语料版本读取器未绑定至当前应用实例")


def get_retrieval_config_revision() -> str:
    """获取本进程生效的检索配置指纹"""
    raise RuntimeError("检索配置指纹未绑定至当前应用实例")


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
RetrievalCacheDependency = Annotated[RetrievalCachePort, Depends(get_retrieval_cache)]
CacheRebuildLockDependency = Annotated[CacheRebuildLockPort, Depends(get_cache_rebuild_lock)]
CorpusRevisionDependency = Annotated[CorpusRevision, Depends(get_corpus_revision)]
RetrievalConfigRevisionDependency = Annotated[str, Depends(get_retrieval_config_revision)]


async def cached_debug_response(
    cache: RetrievalCachePort,
    key: str,
    scope: RetrievalCacheScope,
) -> RetrievalDebugResponse | None:
    """读取并校验缓存信封，解析失败或版本不一致时删除缓存并返回 None。"""
    payload = await cache.get(key)
    if payload is None:
        return None
    try:
        envelope = CachedRetrievalDebug.model_validate_json(payload)
    except ValidationError:
        await cache.discard(key)
        return None
    if (
        envelope.schema_version != CACHE_SCHEMA_VERSION
        or envelope.corpus_revision != scope.corpus_revision
    ):
        await cache.discard(key)
        return None
    return envelope.response


def is_cacheable(response: RetrievalDebugResponse) -> bool:
    """判断检索响应是否可缓存，跳过通道失败或重排降级的响应。"""
    if any(channel.status == ChannelStatus.FAILED.value for channel in response.channels):
        return False
    return response.rerank.status != RerankStatus.DEGRADED.value


def cached_debug_payload(response: RetrievalDebugResponse, scope: RetrievalCacheScope) -> bytes:
    """将检索调试响应序列化为包含语料版本的缓存数据。"""
    envelope = CachedRetrievalDebug(corpus_revision=scope.corpus_revision, response=response)
    return envelope.model_dump_json().encode()


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
        request: Request,
        conversations: ConversationServiceDependency,
        limits: RateLimitGuardDependency,
    ) -> ConversationResponse:
        """在指定知识库下创建新对话"""
        await limits.enforce(
            route="conversations.create",
            principal=client_host(request),
            limit=30,
        )
        conversation = await conversations.create(
            owner_id=PLATFORM_OWNER_ID,
            knowledge_base_id=knowledge_base_id,
            title=payload.title,
        )
        return ConversationResponse.from_conversation(conversation)

    @router.get("/conversations")
    async def list_conversations(
        request: Request,
        conversations: ConversationServiceDependency,
        limits: RateLimitGuardDependency,
    ) -> list[ConversationResponse]:
        """获取全部对话列表"""
        await limits.enforce(
            route="conversations.list",
            principal=client_host(request),
            limit=300,
            failure="open",
        )
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
        request: Request,
        agent: ConversationAgentDependency,
        limits: RateLimitGuardDependency,
    ) -> StreamingResponse:
        """流式提问并返回 SSE 事件流"""
        await limits.enforce(
            route="conversations.ask",
            principal=client_host(request),
            limit=30,
        )
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
        request: Request,
        knowledge_bases: KnowledgeBaseServiceDependency,
        understanding: UnderstandingDependency,
        retrieval: RetrievalDependency,
        cache: RetrievalCacheDependency,
        rebuild_lock: CacheRebuildLockDependency,
        revisions: CorpusRevisionDependency,
        config_revision: RetrievalConfigRevisionDependency,
        limits: RateLimitGuardDependency,
    ) -> RetrievalDebugResponse:
        """单次检索调试探针（返回各渠道召回、融合、重排与门控详情）"""
        await limits.enforce(
            route="retrieval-debug.query",
            principal=client_host(request),
            limit=30,
        )
        await knowledge_bases.get(
            owner_id=PLATFORM_OWNER_ID,
            knowledge_base_id=payload.knowledge_base_id,
        )

        async def rebuild() -> RetrievalDebugResponse:
            """回源执行检索并构建调试响应。"""
            classified = await understanding.understand(question=payload.query)
            # 无改写查询时兜底使用原始问题执行检索
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

        if not cache.enabled:
            return await rebuild()

        scope = RetrievalCacheScope(
            owner_id=PLATFORM_OWNER_ID,
            knowledge_base_id=payload.knowledge_base_id,
            corpus_revision=await revisions.revision_for_knowledge_base(payload.knowledge_base_id),
            query=payload.query,
            config_revision=config_revision,
        )
        key = cache_key(scope)
        cached = await cached_debug_response(cache, key, scope)
        if cached is not None:
            return cached
        async with rebuild_lock.hold(key) as held:
            if not held:
                cached = await cached_debug_response(cache, key, scope)
                return cached if cached is not None else await rebuild()
            response = await rebuild()
            if is_cacheable(response):
                await cache.put(key, cached_debug_payload(response, scope))
            return response

    return router
