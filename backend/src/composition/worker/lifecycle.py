"""Worker 优雅停机信号监听辅助函数。"""

from __future__ import annotations

import asyncio
import signal


def shutdown_event() -> asyncio.Event:
    """监听 SIGINT 与 SIGTERM 信号并返回异步停机事件（兼容 Windows 与 Unix）。"""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop(_signum: int, _frame: object) -> None:
        loop.call_soon_threadsafe(stop.set)

    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(handled_signal, stop.set)
        except NotImplementedError:
            signal.signal(handled_signal, request_stop)

    return stop
