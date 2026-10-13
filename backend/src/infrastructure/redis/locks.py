"""基于 Redis 分布式锁协调缓存回源并发请求。"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from types import TracebackType

    from redis.asyncio import Redis
    from redis.asyncio.lock import Lock

log = structlog.get_logger(__name__)


class RedisCacheRebuildLock:
    """基于 Redis 的缓存回源互斥锁管理器。"""

    def __init__(
        self,
        *,
        client: Redis,
        prefix: str,
        timeout_seconds: int,
        blocking_timeout_seconds: float,
    ) -> None:
        self._client = client
        self._prefix = prefix
        self._timeout_seconds = timeout_seconds
        self._blocking_timeout_seconds = blocking_timeout_seconds

    def hold(self, key: str) -> RebuildHold:
        """获取指定缓存键的回源互斥锁上下文。"""
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return RebuildHold(
            lock=self._client.lock(
                name=f"{self._prefix}:{digest}",
                timeout=self._timeout_seconds,
                blocking_timeout=self._blocking_timeout_seconds,
                thread_local=False,
            )
        )


class DisabledCacheRebuildLock:
    """回源锁未启用时的空实现。"""

    def hold(self, key: str) -> RebuildHold:
        """返回不持有锁的上下文句柄。"""
        return RebuildHold(lock=None)


class RebuildHold:
    """缓存回源互斥锁上下文管理器。"""

    def __init__(self, *, lock: Lock | None) -> None:
        self._lock = lock
        self._held = False

    async def __aenter__(self) -> bool:
        if self._lock is None:
            return False
        try:
            self._held = await self._lock.acquire()
        except Exception as error:
            log.warning(
                "缓存回源锁获取失败，降级为直接回源",
                error_type=type(error).__name__,
            )
            return False
        return self._held

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._held or self._lock is None:
            return
        self._held = False
        try:
            await self._lock.release()
        except Exception as error:
            log.warning(
                "缓存回源锁释放失败，等待锁自动过期",
                error_type=type(error).__name__,
            )
