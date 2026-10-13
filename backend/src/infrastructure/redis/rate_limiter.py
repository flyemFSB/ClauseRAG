"""基于 Redis Lua 脚本的原子固定窗口限流计数器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.shared.rate_limit import RateLimitDecision

if TYPE_CHECKING:
    from redis.asyncio import Redis

# Lua 脚本原子执行递增与过期设置，防止产生无 TTL 的残留键
_FIXED_WINDOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


class RedisFixedWindowRateLimiter:
    """固定窗口限流计数器实现。"""

    def __init__(self, *, client: Redis, prefix: str) -> None:
        self._prefix = prefix
        self._script = client.register_script(_FIXED_WINDOW_SCRIPT)

    async def hit(self, *, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        """记录一次请求并返回限流判定结果。"""
        result = await self._script(keys=[f"{self._prefix}:{key}"], args=[window_seconds])
        count = int(result[0])
        return RateLimitDecision(
            allowed=count <= limit,
            count=count,
            limit=limit,
            retry_after_seconds=max(int(result[1]), 1),
        )
