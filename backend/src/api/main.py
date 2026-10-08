"""业务 API 服务入口进程。"""

from __future__ import annotations

import uvicorn

from composition.api.app import create_app
from composition.api.runtime import build_api_runtime
from composition.startup import start_process


def main() -> None:
    """初始化 API 运行时并启动 Web 服务"""
    runtime = start_process("api", build_api_runtime)
    uvicorn.run(
        create_app(runtime),
        host=runtime.settings.api_host,
        port=runtime.settings.api_port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
