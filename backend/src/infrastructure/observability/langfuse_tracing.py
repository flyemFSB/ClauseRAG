"""Langfuse 链路追踪适配器封装，网络异常安全降级不阻断业务。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
from langfuse import Langfuse

if TYPE_CHECKING:
    from collections.abc import Mapping

log = structlog.get_logger(__name__)


class Tracing:
    """Langfuse 追踪客户端包装器（未配置密钥时自动退化为 no-op）。"""

    def __init__(
        self,
        *,
        public_key: str | None,
        secret_key: str | None,
        host: str,
    ) -> None:
        self._client: Langfuse | None = None
        if public_key and secret_key:
            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
        self._enabled = self._client is not None

    @property
    def enabled(self) -> bool:
        """当前部署是否启用了追踪。"""
        return self._enabled

    def start(
        self,
        *,
        name: str,
        metadata: Mapping[str, object],
        trace_id: str | None = None,
        input_text: str | None = None,
    ) -> Any | None:
        """开启一次 Observation Span。"""
        if self._client is None:
            return None
        try:
            return self._client.start_observation(
                name=name,
                as_type="span",
                input=input_text,
                metadata=dict(metadata),
                trace_context={"trace_id": trace_id or uuid4().hex},
            )
        except Exception as error:
            log.warning("Langfuse链路开始记录失败", error_class=type(error).__name__)
            return None

    def finish(
        self,
        observation: Any | None,
        *,
        output_text: str | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """结束 Observation Span 并立即刷新缓冲区。"""
        if observation is None:
            return
        try:
            if error_class is not None:
                observation.update(
                    output=output_text,
                    level="ERROR",
                    status_message=f"{error_class}: {error_message or ''}".strip()[:500],
                )
            else:
                observation.update(output=output_text)
            observation.end()
            if self._client is not None:
                self._client.flush()
        except Exception as error:
            log.warning("Langfuse链路完成记录失败", error_class=type(error).__name__)

    def shutdown(self) -> None:
        """刷新挂起数据并停止后台工作线程。"""
        if self._client is None:
            return
        try:
            self._client.shutdown()
        except Exception as error:
            log.warning("Langfuse客户端关闭失败", error_class=type(error).__name__)
