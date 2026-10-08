"""长连接 HTTP 客户端连接池管理（按进程单例复用连接）。"""

from __future__ import annotations

import asyncio

import httpx


class ProcessHttpClient:
    """提供单进程长生命周期的异步 HTTP 客户端连接池。"""

    def __init__(self, *, base_url: str, timeout_seconds: int, max_connections: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_connections = max_connections
        self._lock = asyncio.Lock()
        self._client: httpx.AsyncClient | None = None

    async def connection(self) -> httpx.AsyncClient:
        """获取或懒加载当前进程的 HTTP 客户端实例。"""
        async with self._lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=httpx.Timeout(self._timeout_seconds),
                    limits=httpx.Limits(max_connections=self._max_connections),
                )
            return self._client

    async def close(self) -> None:
        """关闭客户端及底层连接池（支持幂等重复调用）。"""
        async with self._lock:
            client, self._client = self._client, None
        if client is not None:
            await client.aclose()
