"""请求速率限制接口协议与限额执行策略。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol

import structlog

log = structlog.get_logger(__name__)

FailureMode = Literal["closed", "open"]


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """固定窗口限流判定结果。"""

    allowed: bool
    count: int
    limit: int
    retry_after_seconds: int


class RateLimiterPort(Protocol):
    """固定窗口计数器接口协议。"""

    async def hit(self, *, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        """记录一次请求并返回限流判定结果。"""
        ...


class RateLimitExceededError(Exception):
    """请求超出限额异常。"""

    def __init__(self, *, route: str, retry_after_seconds: int) -> None:
        super().__init__(f"路由 {route} 超出速率限制，请在 {retry_after_seconds} 秒后重试")
        self.route = route
        self.retry_after_seconds = retry_after_seconds


class RateLimitUnavailableError(Exception):
    """限流服务不可用异常。"""

    def __init__(self, *, route: str) -> None:
        super().__init__(f"路由 {route} 的限流后端不可用，已按 fail-closed 拒绝请求")
        self.route = route


class RateLimitGuard:
    """路由级请求速率限制守卫。"""

    def __init__(self, *, limiter: RateLimiterPort | None) -> None:
        self._limiter = limiter

    async def enforce(
        self,
        *,
        route: str,
        principal: str,
        limit: int,
        window_seconds: int = 60,
        failure: FailureMode = "closed",
    ) -> None:
        """执行限流校验，超限或依赖不可用时按策略阻断或降级。"""
        if self._limiter is None:
            return
        try:
            decision = await self._limiter.hit(
                key=f"{principal_digest(principal)}:{route}:{window_seconds}",
                limit=limit,
                window_seconds=window_seconds,
            )
        except Exception as error:
            log.warning(
                "速率限制后端不可用",
                route=route,
                failure=failure,
                error_type=type(error).__name__,
            )
            if failure == "closed":
                raise RateLimitUnavailableError(route=route) from error
            return
        if not decision.allowed:
            log.warning(
                "请求超出速率限制",
                route=route,
                count=decision.count,
                limit=limit,
            )
            raise RateLimitExceededError(
                route=route,
                retry_after_seconds=decision.retry_after_seconds,
            )


def principal_digest(principal: str) -> str:
    """计算主体哈希摘要，避免原始来源标识直接入库或打日志。"""
    return hashlib.sha256(principal.encode()).hexdigest()[:16]
