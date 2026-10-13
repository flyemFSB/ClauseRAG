"""基于 Redis 的检索调试结果缓存实现。"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from redis.asyncio import Redis

log = structlog.get_logger(__name__)


class RedisRetrievalCache:
    """检索调试缓存实现，支持 TTL 抖动与异常自动降级。"""

    enabled = True

    def __init__(
        self,
        *,
        client: Redis,
        prefix: str,
        ttl_seconds: int,
        ttl_jitter_seconds: int,
        max_value_bytes: int,
    ) -> None:
        self._client = client
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds
        self._ttl_jitter_seconds = ttl_jitter_seconds
        self._max_value_bytes = max_value_bytes

    async def get(self, key: str) -> bytes | None:
        """读取缓存原始内容，未命中或异常时返回 None。"""
        try:
            value = await self._client.get(self._name(key))
        except Exception as error:
            log.warning("检索缓存读取失败，降级为未命中", error_type=type(error).__name__)
            return None
        return value if isinstance(value, bytes) else None

    async def put(self, key: str, payload: bytes) -> None:
        """写入缓存数据，超过单值上限或写入异常时跳过。"""
        if len(payload) > self._max_value_bytes:
            log.warning("检索缓存数据超出体积上限，跳过缓存", value_bytes=len(payload))
            return
        try:
            await self._client.set(self._name(key), payload, ex=self._ttl())
        except Exception as error:
            log.warning("检索缓存写入失败，跳过写入", error_type=type(error).__name__)

    async def discard(self, key: str) -> None:
        """删除指定键的缓存数据。"""
        try:
            await self._client.delete(self._name(key))
        except Exception as error:
            log.warning("检索缓存删除失败，等待自然过期", error_type=type(error).__name__)

    def _name(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def _ttl(self) -> int:
        return self._ttl_seconds + random.randint(0, self._ttl_jitter_seconds)


class DisabledRetrievalCache:
    """检索缓存未启用时的空实现。"""

    enabled = False

    async def get(self, key: str) -> bytes | None:
        """空实现：固定返回未命中。"""
        return None

    async def put(self, key: str, payload: bytes) -> None:
        """空实现：忽略写入。"""

    async def discard(self, key: str) -> None:
        """空实现：忽略删除。"""
