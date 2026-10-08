"""Worker 后台进程入口：消费任务队列、对账投递摄取任务并定期轮询清理孤立产物。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from composition.startup import start_process
from composition.worker.lifecycle import shutdown_event
from composition.worker.runtime import build_worker_runtime

if TYPE_CHECKING:
    from composition.worker.runtime import WorkerRuntime

# 孤立产物轮询扫描间隔（秒）与单批处理上限
_SWEEP_INTERVAL_SECONDS = 15.0
_SWEEP_LIMIT = 20


def main() -> None:
    """初始化运行时并启动工作循环。"""
    runtime = start_process("worker", build_worker_runtime)
    log = structlog.get_logger(__name__)
    log.info("Worker工作进程已启动")
    asyncio.run(_consume(runtime))
    log.info("Worker工作进程已停止")


async def _consume(runtime: WorkerRuntime) -> None:
    """消费任务队列并执行对账与清理循环，接收终止信号后释放资源。"""
    stop = shutdown_event()
    background = (
        asyncio.create_task(_sweep(runtime, stop)),
        asyncio.create_task(_dispatch(runtime, stop)),
    )
    try:
        await runtime.job_queue.consume(
            stop=stop,
            max_async_tasks=runtime.settings.worker_max_async_tasks,
        )
    finally:
        for task in background:
            task.cancel()
        # 取消后台协程，未完结的意图与作业在租约过期后由后续扫描接管
        await asyncio.gather(*background, return_exceptions=True)
        await runtime.close()


async def _dispatch(runtime: WorkerRuntime, stop: asyncio.Event) -> None:
    """周期性接管过期租约并投递每一个到点的等待中作业。"""
    log = structlog.get_logger(__name__)
    interval = runtime.settings.job_dispatch_interval_seconds
    while not stop.is_set():
        try:
            await runtime.dispatch.reconcile()
        except Exception as error:
            log.error("摄取任务对账异常", error_class=type(error).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue


async def _sweep(runtime: WorkerRuntime, stop: asyncio.Event) -> None:
    """周期性扫描待清理的孤立产物。"""
    log = structlog.get_logger(__name__)
    while not stop.is_set():
        try:
            await runtime.cleanup.run_pending(limit=_SWEEP_LIMIT)
        except Exception as error:
            log.error("后台清理轮询异常", error_class=type(error).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=_SWEEP_INTERVAL_SECONDS)
        except TimeoutError:
            continue


if __name__ == "__main__":
    main()
