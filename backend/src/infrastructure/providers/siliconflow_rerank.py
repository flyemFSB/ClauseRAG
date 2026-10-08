"""SiliconFlow 语义重排客户端适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from domain.retrieval import RerankRejectedError, TransientRerankError
from infrastructure.providers.http_client import ProcessHttpClient
from infrastructure.providers.siliconflow_errors import provider_message

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_RERANK_PATH = "/rerank"
_OK_STATUS = 200
_TRANSIENT_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class _Result(BaseModel):
    model_config = ConfigDict(extra="ignore")
    index: int
    relevance_score: float


class _RerankResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    results: list[_Result]


class SiliconFlowReranker:
    """SiliconFlow 语义重排服务适配器。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int,
        max_connections: int,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._http = ProcessHttpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_connections=max_connections,
        )

    async def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> Mapping[int, float]:
        """对候选文本列表进行语义相关性打分并返回序号映射。"""
        if not documents:
            return {}
        body: dict[str, object] = {
            "model": self.model,
            "query": query,
            "documents": list(documents),
            "top_n": min(top_n, len(documents)),
            "return_documents": False,
        }
        client = await self._http.connection()
        try:
            response = await client.post(_RERANK_PATH, json=body, headers=self._headers())
        except httpx.HTTPError as error:
            raise TransientRerankError(f"语义重排服务不可达: {type(error).__name__}") from error
        if response.status_code in _TRANSIENT_STATUSES:
            raise TransientRerankError(
                f"语义重排服务返回临时错误 HTTP {response.status_code}: "
                f"{provider_message(response)}"
            )
        if response.status_code != _OK_STATUS:
            raise RerankRejectedError(
                f"重排模型 {self.model} 调用失败 HTTP {response.status_code}: "
                f"{provider_message(response)}"
            )
        return self._scores(response, expected=len(documents))

    def _scores(self, response: httpx.Response, *, expected: int) -> Mapping[int, float]:
        try:
            payload = _RerankResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise RerankRejectedError(
                "语义重排服务返回 HTTP 200，但响应体格式不符合重排结果协议"
            ) from error
        scores: dict[int, float] = {}
        for result in payload.results:
            if not 0 <= result.index < expected:
                raise RerankRejectedError(
                    f"重排服务返回文档序号 ({result.index}) 超出输入文档范围 (0..{expected - 1})"
                )
            scores[result.index] = result.relevance_score
        return scores

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def close(self) -> None:
        await self._http.close()
