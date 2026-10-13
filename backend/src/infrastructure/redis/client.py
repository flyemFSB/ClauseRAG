"""业务 Redis 异步客户端构建与启动探活。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from redis.asyncio import Redis, from_url
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings

log = structlog.get_logger(__name__)


def open_client(settings: Settings) -> Redis | None:
    """构建业务 Redis 异步客户端，未启用时返回 None。"""
    if not settings.redis_enabled or settings.redis_url is None:
        return None
    return from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
        max_connections=settings.redis_max_connections,
        # 禁用重试，避免连接失败阻塞降级流程
        retry=Retry(backoff=NoBackoff(), retries=0),
        health_check_interval=30,
        decode_responses=False,
    )


async def report_startup(settings: Settings, client: Redis | None) -> None:
    """启动时探测 Redis 连通性并记录功能启用状态。"""
    if client is None:
        log.info(
            "业务 Redis 未启用，限流与检索缓存均处于关闭状态",
            rate_limit=False,
            retrieval_cache=False,
        )
        return
    try:
        async with asyncio.timeout(settings.redis_health_timeout_seconds):
            await client.ping()  # pyright: ignore[reportUnknownMemberType]
    except Exception as error:
        log.warning(
            "业务 Redis 连通性探测失败，相关能力已降级运行",
            error_type=type(error).__name__,
        )
    log.info(
        "业务 Redis 初始化完成",
        rate_limit=settings.redis_rate_limit_enabled,
        retrieval_cache=settings.redis_cache_enabled,
    )
