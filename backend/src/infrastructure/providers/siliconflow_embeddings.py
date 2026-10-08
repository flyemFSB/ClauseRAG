"""SiliconFlow 文本向量嵌入客户端适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from domain.embedding import EmbeddingProviderError, TransientEmbeddingError
from infrastructure.providers.http_client import ProcessHttpClient
from infrastructure.providers.siliconflow_errors import provider_message

if TYPE_CHECKING:
    from collections.abc import Sequence

_EMBEDDINGS_PATH = "/embeddings"
_OK_STATUS = 200
_TRANSIENT_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class _EmbeddingEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    embedding: list[float]
    index: int


class _EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    data: list[_EmbeddingEntry]


class SiliconFlowEmbeddingProvider:
    """SiliconFlow 文本向量嵌入服务适配器。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimension: int,
        timeout_seconds: int,
        max_connections: int,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.dimension = dimension
        self._http = ProcessHttpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_connections=max_connections,
        )

    async def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        """批量计算输入文本列表的向量嵌入。"""
        if not texts:
            return ()
        return await self._request(await self._http.connection(), texts)

    async def close(self) -> None:
        await self._http.close()

    async def _request(
        self,
        client: httpx.AsyncClient,
        texts: Sequence[str],
    ) -> tuple[tuple[float, ...], ...]:
        body = {"model": self.model, "input": list(texts), "encoding_format": "float"}
        try:
            response = await client.post(
                _EMBEDDINGS_PATH,
                json=body,
                headers=self._authorization(),
            )
        except httpx.HTTPError as error:
            raise TransientEmbeddingError(
                f"向量嵌入服务不可达: {type(error).__name__}: {error}"
            ) from error
        if response.status_code in _TRANSIENT_STATUSES:
            raise TransientEmbeddingError(
                f"向量嵌入服务返回临时错误 HTTP {response.status_code}: "
                f"{provider_message(response)}"
            )
        if response.status_code != _OK_STATUS:
            raise EmbeddingProviderError(
                f"向量嵌入模型 {self.model} 调用失败 HTTP {response.status_code}: "
                f"{provider_message(response)}"
            )
        try:
            payload = _EmbeddingResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise EmbeddingProviderError(
                "向量嵌入服务返回 HTTP 200，但响应体格式不符合嵌入结果协议"
            ) from error
        return self._vectors(payload, expected=len(texts))

    def _vectors(
        self, payload: _EmbeddingResponse, *, expected: int
    ) -> tuple[tuple[float, ...], ...]:
        entries: list[tuple[int, tuple[float, ...]]] = []
        for entry in payload.data:
            vector = tuple(entry.embedding)
            if len(vector) != self.dimension:
                raise EmbeddingProviderError(
                    f"向量嵌入模型 {self.model} 返回向量维度 ({len(vector)}) "
                    f"与系统配置索引维度 ({self.dimension}) 不符"
                )
            entries.append((entry.index, vector))
        if len(entries) != expected:
            raise EmbeddingProviderError(
                f"向量嵌入服务返回向量数量 ({len(entries)}) 与输入文本数量 ({expected}) 不符"
            )
        ordered = sorted(entries, key=lambda entry: entry[0])
        if [index for index, _ in ordered] != list(range(expected)):
            raise EmbeddingProviderError(
                f"向量嵌入服务返回索引顺序与预期 (0..{expected - 1}) 不一致"
            )
        return tuple(vector for _, vector in ordered)

    def _authorization(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
