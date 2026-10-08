"""Agent 运行时组合装配：检索流水线、对话上下文与追踪组件。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_runtime.state import RunContext
from application.agent.answer import AnswerService
from application.agent.query_understanding import QueryUnderstandingService
from application.conversations.service import ConversationService
from application.knowledge.knowledge_bases import KnowledgeBaseService
from application.retrieval.citations import CitationService
from application.retrieval.service import RetrievalService
from composition.shared.database import open_database
from composition.shared.health import open_health
from composition.shared.providers import open_chat, open_embedding_provider, open_reranker
from composition.shared.qdrant import open_vector_index
from composition.shared.retrieval import retrieval_budget
from composition.shared.stores import (
    open_chunk_store,
    open_knowledge_bases,
)
from composition.shared.tracing import open_tracing
from domain.citation import CitationPolicy
from infrastructure.config.settings import Settings, libpq_dsn, load_settings
from infrastructure.db.stores.conversation_store import SqlAlchemyConversationStore
from infrastructure.parsing.token_counter import TiktokenTokenCounter
from infrastructure.retrieval.dense_channel import DenseChannel
from infrastructure.retrieval.keyword_channel import KeywordChannel

if TYPE_CHECKING:
    from application.retrieval.channels import RetrievalChannel
    from application.shared.health import HealthService
    from infrastructure.db.engine import Database
    from infrastructure.observability.langfuse_tracing import Tracing
    from infrastructure.providers.siliconflow_chat import SiliconFlowChat
    from infrastructure.providers.siliconflow_embeddings import SiliconFlowEmbeddingProvider
    from infrastructure.providers.siliconflow_rerank import SiliconFlowReranker
    from infrastructure.retrieval.qdrant_index import QdrantChildChunkIndex


@dataclass(frozen=True, slots=True)
class AgentRuntime:
    """Agent 运行时容器持有的全部生命周期托管组件。"""

    settings: Settings
    health: HealthService
    knowledge_bases: KnowledgeBaseService
    context: RunContext
    tracing: Tracing
    database: Database
    vector_index: QdrantChildChunkIndex
    embedding: SiliconFlowEmbeddingProvider
    chat: SiliconFlowChat
    reranker: SiliconFlowReranker
    checkpoints_dsn: str
    checkpoints_pool_size: int

    async def close(self) -> None:
        """依序安全释放向量索引、模型适配器与数据库连接池。"""
        await self.vector_index.close()
        await self.embedding.close()
        await self.chat.close()
        await self.reranker.close()
        self.tracing.shutdown()
        await self.database.dispose()


def build_agent_runtime() -> AgentRuntime:
    """加载配置并装配 Agent 运行时各层依赖。"""
    settings = load_settings()
    database = open_database(settings, pool_size=settings.agent_database_pool_size)
    tracing = open_tracing(settings)
    vector_index = open_vector_index(settings)
    embedding = open_embedding_provider(settings)
    chat = open_chat(settings)
    reranker = open_reranker(settings)
    knowledge_bases_store = open_knowledge_bases(database)
    chunk_store = open_chunk_store(database)
    counter = TiktokenTokenCounter()

    channels: tuple[RetrievalChannel, ...] = (
        DenseChannel(provider=embedding, index=vector_index),
        KeywordChannel(chunks=chunk_store),
    )
    retrieval = RetrievalService(
        channels=channels,
        chunks=chunk_store,
        reranker=reranker,
        budget=retrieval_budget(settings),
        counter=counter,
        channel_timeout_seconds=settings.retrieval_channel_timeout_seconds,
        rerank_timeout_seconds=settings.rerank_timeout_seconds,
        rerank_limit=settings.rerank_limit,
        rerank_max_documents=settings.rerank_max_documents,
        min_rerank_score=settings.min_rerank_score,
        citation_quote_chars=settings.citation_quote_chars,
    )
    query_understanding = QueryUnderstandingService(
        chat=chat,
        max_tokens=settings.query_understanding_max_tokens,
        temperature=0.0,
    )
    answers = AnswerService(
        chat=chat,
        counter=counter,
        max_tokens=settings.chat_max_tokens,
        temperature=settings.chat_temperature,
    )
    knowledge_bases = KnowledgeBaseService(knowledge_bases=knowledge_bases_store)
    return AgentRuntime(
        settings=settings,
        health=open_health(settings),
        knowledge_bases=knowledge_bases,
        context=RunContext(
            conversations=ConversationService(
                conversations=SqlAlchemyConversationStore(database.sessions),
                knowledge_bases=knowledge_bases_store,
            ),
            understanding=query_understanding,
            retrieval=retrieval,
            answers=answers,
            citations=CitationService(
                chunks=chunk_store,
                policy=CitationPolicy(settings.citation_invalid_id_policy),
                quote_chars=settings.citation_quote_chars,
            ),
            history_messages=settings.chat_history_messages,
        ),
        tracing=tracing,
        database=database,
        vector_index=vector_index,
        embedding=embedding,
        chat=chat,
        reranker=reranker,
        checkpoints_dsn=libpq_dsn(settings.database_url.get_secret_value()),
        checkpoints_pool_size=settings.checkpoint_pool_size,
    )
