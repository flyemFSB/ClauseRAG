"""检索调试缓存键空间契约与接口协议。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from uuid import UUID

CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class RetrievalCacheScope:
    """检索调试缓存作用域，包含租户、语料版本、查询与配置指纹。"""

    owner_id: UUID
    knowledge_base_id: UUID
    corpus_revision: str
    query: str
    config_revision: str


def cache_key(scope: RetrievalCacheScope) -> str:
    """生成检索调试缓存键，查询文本采用 SHA-256 摘要标识。"""
    query_hash = hashlib.sha256(scope.query.encode()).hexdigest()[:32]
    return (
        f"retrieval:{scope.owner_id}:{scope.knowledge_base_id}"
        f":{scope.corpus_revision}:{query_hash}:{scope.config_revision}"
    )


class RetrievalCachePort(Protocol):
    """检索调试缓存读写接口协议。"""

    enabled: bool
    """缓存是否可用；关闭时跳过版本查询与缓存读写。"""

    async def get(self, key: str) -> bytes | None:
        """读取缓存原始内容，未命中或异常时返回 None。"""
        ...

    async def put(self, key: str, payload: bytes) -> None:
        """写入带过期时间的缓存数据，异常时降级忽略。"""
        ...

    async def discard(self, key: str) -> None:
        """删除指定键的缓存数据。"""
        ...


class CacheRebuildLockPort(Protocol):
    """缓存回源并发控制锁接口协议。"""

    def hold(self, key: str) -> AbstractAsyncContextManager[bool]:
        """获取回源互斥锁上下文，未获取到时旁路回源。"""
        ...
