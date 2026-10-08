"""外部大模型与算法服务客户端装配（Embedding、Chat、Rerank）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrastructure.providers.siliconflow_chat import SiliconFlowChat
from infrastructure.providers.siliconflow_embeddings import SiliconFlowEmbeddingProvider
from infrastructure.providers.siliconflow_rerank import SiliconFlowReranker

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings


def open_embedding_provider(settings: Settings) -> SiliconFlowEmbeddingProvider:
    """构建 SiliconFlow 文本向量嵌入客户端实例。"""
    return SiliconFlowEmbeddingProvider(
        api_key=settings.siliconflow_api_key.get_secret_value(),
        base_url=settings.siliconflow_base_url,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        timeout_seconds=settings.embedding_timeout_seconds,
        max_connections=settings.provider_max_connections,
    )


def open_chat(settings: Settings) -> SiliconFlowChat:
    """构建对话大模型客户端实例。

    对话模型可以与向量/重排指向不同服务商：`CHAT_BASE_URL` / `CHAT_API_KEY` 未设置时沿用
    SiliconFlow 的端点与凭据（默认行为不变）；指向 SenseNova 这类 OpenAI-compatible 服务时只换
    这两项加 `CHAT_MODEL`，向量与重排仍在 SiliconFlow，无需重建索引。
    """
    api_key = settings.chat_api_key or settings.siliconflow_api_key
    return SiliconFlowChat(
        api_key=api_key.get_secret_value(),
        base_url=settings.chat_base_url or settings.siliconflow_base_url,
        model=settings.chat_model,
        timeout_seconds=settings.chat_timeout_seconds,
        max_connections=settings.provider_max_connections,
    )


def open_reranker(settings: Settings) -> SiliconFlowReranker:
    """构建 SiliconFlow 语义重排客户端实例。"""
    return SiliconFlowReranker(
        api_key=settings.siliconflow_api_key.get_secret_value(),
        base_url=settings.siliconflow_base_url,
        model=settings.rerank_model,
        timeout_seconds=settings.rerank_timeout_seconds,
        max_connections=settings.provider_max_connections,
    )
