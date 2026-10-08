"""SiliconFlow 错误信封的解码：对话、嵌入与重排三个客户端共用同一份错误体契约。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, ValidationError

if TYPE_CHECKING:
    import httpx


class ErrorBody(BaseModel):
    """SiliconFlow 错误响应体：未知字段忽略，code 与 message 都允许缺失。"""

    model_config = ConfigDict(extra="ignore")
    code: int | None = None
    message: str | None = None


def provider_message(response: httpx.Response) -> str:
    """把一次失败响应渲染成一行可诊断的描述，正文不是错误信封时明确说出来。"""
    try:
        body = ErrorBody.model_validate(response.json())
    except (ValueError, ValidationError):
        return "no JSON error body"
    if body.code is None and body.message is None:
        return "an error body without a code or a message"
    return f"code {body.code}: {body.message}"
