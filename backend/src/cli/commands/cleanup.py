"""cleanup-pending 命令：手动触发执行待处理清理意图。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from composition.cli.runtime import CleanupRuntime


DEFAULT_CLEANUP_LIMIT = 20


def cleanup_pending(runtime: CleanupRuntime, limit: int) -> int:
    """执行待处理清理意图并报告处理次数。"""
    attempts = asyncio.run(cleanup_async(runtime, limit))
    print(f"cleanup attempts {attempts}")
    return 0


async def cleanup_async(runtime: CleanupRuntime, limit: int) -> int:
    """在独立生命周期中执行清理并释放资源。"""
    try:
        return await runtime.lane.run_pending(limit=limit)
    finally:
        await runtime.close()
