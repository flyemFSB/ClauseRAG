"""模型服务适配接口协议（文本嵌入、大模型对话与重排模型）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping, Sequence

    from domain.chat import ChatCompletion, ChatDelta, ChatMessage


class EmbeddingProvider(Protocol):
    """文本向量化模型接口协议"""

    model: str
    dimension: int

    async def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        """批量计算文本的特征向量"""
        ...

    async def close(self) -> None:
        """释放底层网络客户端连接资源"""
        ...


class ChatModel(Protocol):
    """对话大语言模型接口协议"""

    model: str

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        json_object: bool = False,
    ) -> ChatCompletion:
        """非流式调用大模型获取完整回复"""
        ...

    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[ChatDelta]:
        """流式调用大模型获取增量生成数据流"""
        ...

    async def close(self) -> None:
        """关闭客户端连接"""
        ...


class Reranker(Protocol):
    """重排模型接口协议"""

    model: str

    async def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> Mapping[int, float]:
        """对输入文档列表计算与查询的相关性打分，返回输入索引到得分的映射"""
        ...

    async def close(self) -> None:
        """关闭客户端连接"""
        ...
