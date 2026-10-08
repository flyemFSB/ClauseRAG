"""Agent 运行时进程入口。"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import uvicorn

from composition.agent.app import create_agent_app
from composition.agent.runtime import build_agent_runtime
from composition.startup import start_process

if TYPE_CHECKING:
    from collections.abc import Callable


def main() -> None:
    """启动 Agent 运行时并提供对话服务。"""
    runtime = start_process("agent-runtime", build_agent_runtime)
    config = uvicorn.Config(
        create_agent_app(runtime),
        host=runtime.settings.agent_runtime_host,
        port=runtime.settings.agent_runtime_port,
        log_config=None,
    )
    # Windows 下 psycopg 异步驱动要求 SelectorEventLoop
    asyncio.run(uvicorn.Server(config).serve(), loop_factory=_loop_factory())


def _loop_factory() -> Callable[[], asyncio.AbstractEventLoop] | None:
    """返回当前平台适配的事件循环工厂。"""
    if sys.platform != "win32":
        return None
    return asyncio.SelectorEventLoop


if __name__ == "__main__":
    main()
