"""RabbitMQ 任务队列适配器装配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrastructure.queue.job_queue import IngestionJobQueue

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings
    from infrastructure.observability.langfuse_tracing import Tracing


def open_job_queue(settings: Settings, tracing: Tracing) -> IngestionJobQueue:
    """初始化基于 Taskiq 和 RabbitMQ 的摄取任务队列适配器。"""
    return IngestionJobQueue(
        rabbitmq_url=settings.rabbitmq_url.get_secret_value(),
        tracing=tracing,
        prefetch_count=settings.worker_max_async_tasks,
        dispatch_timeout_seconds=settings.job_dispatch_timeout_seconds,
    )
