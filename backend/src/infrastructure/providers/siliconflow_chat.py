"""SiliconFlow 对话大模型客户端适配器（支持流式与非流式调用）。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from domain.chat import (
    ChatCompletion,
    ChatDelta,
    ChatRejectedError,
    ChatShapeError,
    ChatStreamInterruptedError,
    TransientChatError,
)
from infrastructure.providers.http_client import ProcessHttpClient
from infrastructure.providers.siliconflow_errors import provider_message

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from domain.chat import ChatMessage

_CHAT_PATH = "/chat/completions"
_OK_STATUS = 200
_TRANSIENT_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_STREAM_DONE = "[DONE]"


class _Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str | None = None


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: _Message
    finish_reason: str | None = None


class _Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class _CompletionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    choices: list[_Choice]
    usage: _Usage | None = None


class _Delta(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str | None = None


class _StreamChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    delta: _Delta | None = None
    finish_reason: str | None = None


class _StreamChunk(BaseModel):
    model_config = ConfigDict(extra="ignore")
    choices: list[_StreamChoice] = []


class SiliconFlowChat:
    """SiliconFlow 对话大模型客户端实现。"""

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

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        json_object: bool = False,
    ) -> ChatCompletion:
        """非流式调用大模型，返回完整回复结果。"""
        body = self._body(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False,
            json_object=json_object,
        )
        client = await self._http.connection()
        try:
            response = await client.post(_CHAT_PATH, json=body, headers=self._headers())
        except httpx.HTTPError as error:
            raise TransientChatError(f"对话模型服务不可达: {type(error).__name__}") from error
        if response.status_code != _OK_STATUS:
            raise self._failure(response.status_code, response)
        return self._completion(response)

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[ChatDelta]:
        """流式调用大模型，按 SSE 帧产出 ChatDelta。"""
        body = self._body(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            json_object=False,
        )
        client = await self._http.connection()
        try:
            async with client.stream(
                "POST",
                _CHAT_PATH,
                json=body,
                headers=self._headers(),
            ) as response:
                if response.status_code != _OK_STATUS:
                    await response.aread()
                    raise self._failure(response.status_code, response)
                async for delta in self._deltas(response):
                    yield delta
        except httpx.HTTPError as error:
            raise TransientChatError(f"对话流式传输异常: {type(error).__name__}") from error

    def _deltas(self, response: httpx.Response) -> AsyncIterator[ChatDelta]:
        terminal = False

        async def _iterate() -> AsyncIterator[ChatDelta]:
            nonlocal terminal
            async for line in response.aiter_lines():
                frame = line.strip()
                if not frame or frame.startswith(":"):
                    continue
                if not frame.startswith("data:"):
                    continue
                data = frame[len("data:") :].strip()
                if data == _STREAM_DONE:
                    terminal = True
                    return
                chunk = _parse_frame(data)
                for choice in chunk.choices:
                    if choice.finish_reason is not None:
                        terminal = True
                        yield ChatDelta(finish_reason=choice.finish_reason)
                    text = choice.delta.content if choice.delta is not None else None
                    if text:
                        yield ChatDelta(text=text)

        async def _checked() -> AsyncIterator[ChatDelta]:
            async for delta in _iterate():
                yield delta
            if not terminal:
                raise ChatStreamInterruptedError(
                    f"模型 {self.model} 对话流在未收到终止帧的情况下意外结束"
                )

        return _checked()

    def _completion(self, response: httpx.Response) -> ChatCompletion:
        try:
            payload = _CompletionResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise ChatShapeError(
                "对话模型服务返回 HTTP 200，但响应体格式不符合补全结果协议"
            ) from error
        if not payload.choices:
            raise ChatShapeError("对话模型服务返回的 choices 列表为空")
        choice = payload.choices[0]
        return ChatCompletion(
            text=choice.message.content or "",
            finish_reason=choice.finish_reason,
            prompt_tokens=payload.usage.prompt_tokens if payload.usage else None,
            completion_tokens=payload.usage.completion_tokens if payload.usage else None,
        )

    def _body(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        stream: bool,
        json_object: bool,
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": message.role.value, "content": message.content} for message in messages
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if json_object:
            body["response_format"] = {"type": "json_object"}
        return body

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _failure(self, status_code: int, response: httpx.Response) -> Exception:
        detail = f"HTTP {status_code}: {provider_message(response)}"
        if status_code in _TRANSIENT_STATUSES:
            return TransientChatError(f"对话模型服务返回临时错误: {detail}")
        return ChatRejectedError(f"模型 {self.model} 拒绝了对话请求: {detail}")

    async def close(self) -> None:
        await self._http.close()


def _parse_frame(data: str) -> _StreamChunk:
    try:
        return _StreamChunk.model_validate(json.loads(data))
    except (ValueError, ValidationError) as error:
        raise ChatShapeError("对话流包含非法数据帧，无法解析为流式分块") from error
