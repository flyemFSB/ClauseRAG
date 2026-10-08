"""Langfuse 可观测性链路追踪客户端装配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrastructure.observability.langfuse_tracing import Tracing

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings


def open_tracing(settings: Settings) -> Tracing:
    """初始化 Langfuse 追踪客户端（未配置密钥时自动退化为 no-op）。"""
    return Tracing(
        public_key=(
            settings.langfuse_public_key.get_secret_value()
            if settings.langfuse_public_key
            else None
        ),
        secret_key=(
            settings.langfuse_secret_key.get_secret_value()
            if settings.langfuse_secret_key
            else None
        ),
        host=settings.langfuse_host,
    )
