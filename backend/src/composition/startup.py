"""进程启动生命周期辅助函数：组装运行时并初始化日志配置。"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Protocol

from infrastructure.config.settings import ConfigurationError
from infrastructure.observability.logging import configure_logging

if TYPE_CHECKING:
    from collections.abc import Callable

    from infrastructure.config.settings import Settings


class ProcessRuntime(Protocol):
    """进程运行时协议：持有配置并在关闭时释放资源。"""

    @property
    def settings(self) -> Settings: ...

    async def close(self) -> None: ...


def start_process[RuntimeT: ProcessRuntime](
    service: str, build: Callable[[], RuntimeT]
) -> RuntimeT:
    """初始化构建进程运行时并配置日志系统；配置异常时标准错误输出并退出。"""
    try:
        runtime = build()
    except ConfigurationError as error:
        print(f"配置错误: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    configure_logging(service=service, level=runtime.settings.log_level)
    return runtime
