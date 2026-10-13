"""业务 Redis 派生能力组装工厂：限流守卫、检索调试缓存与回源锁。"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from application.shared.rate_limit import RateLimitGuard
from infrastructure.redis.cache import DisabledRetrievalCache, RedisRetrievalCache
from infrastructure.redis.locks import DisabledCacheRebuildLock, RedisCacheRebuildLock
from infrastructure.redis.rate_limiter import RedisFixedWindowRateLimiter

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from application.retrieval.cache import CacheRebuildLockPort, RetrievalCachePort
    from infrastructure.config.settings import Settings


def open_rate_limit_guard(settings: Settings, client: Redis | None) -> RateLimitGuard:
    """组装限流守卫，未启用时返回空实现。"""
    if client is None or not settings.redis_rate_limit_enabled:
        return RateLimitGuard(limiter=None)
    return RateLimitGuard(
        limiter=RedisFixedWindowRateLimiter(client=client, prefix=keyspace(settings, "rl"))
    )


def open_retrieval_cache(settings: Settings, client: Redis | None) -> RetrievalCachePort:
    """组装检索调试缓存，未启用时返回空实现。"""
    if client is None or not settings.redis_cache_enabled:
        return DisabledRetrievalCache()
    return RedisRetrievalCache(
        client=client,
        prefix=keyspace(settings, "cache"),
        ttl_seconds=settings.redis_cache_ttl_seconds,
        ttl_jitter_seconds=settings.redis_cache_ttl_jitter_seconds,
        max_value_bytes=settings.redis_max_cache_value_bytes,
    )


def open_cache_rebuild_lock(settings: Settings, client: Redis | None) -> CacheRebuildLockPort:
    """组装缓存回源互斥锁，未启用时返回空实现。"""
    if client is None or not settings.redis_cache_enabled:
        return DisabledCacheRebuildLock()
    return RedisCacheRebuildLock(
        client=client,
        prefix=keyspace(settings, "lock:cache-rebuild"),
        timeout_seconds=settings.redis_cache_lock_timeout_seconds,
        blocking_timeout_seconds=settings.redis_cache_lock_blocking_timeout_seconds,
    )


def retrieval_config_revision(settings: Settings) -> str:
    """生成检索运行时配置哈希摘要作为版本指纹。"""
    digest = hashlib.sha256(settings.model_dump_json().encode())
    return digest.hexdigest()[:16]


def keyspace(settings: Settings, purpose: str) -> str:
    """生成规范化的业务 Redis 键前缀。"""
    return f"{settings.redis_key_prefix}:{purpose}:v1"
