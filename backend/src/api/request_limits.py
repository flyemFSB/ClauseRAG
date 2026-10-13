"""请求限流依赖注入声明与调用主体识别。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from application.shared.rate_limit import RateLimitGuard


def get_rate_limit_guard() -> RateLimitGuard:
    """获取速率限制守卫。"""
    raise RuntimeError("速率限制守卫未绑定至当前应用实例")


RateLimitGuardDependency = Annotated[RateLimitGuard, Depends(get_rate_limit_guard)]


def client_host(request: Request) -> str:
    """获取反向代理连接的客户端地址作为限流主体。"""
    # 未接入鉴权体系前以对端 IP 标识限流主体
    return request.client.host if request.client is not None else "unknown"
