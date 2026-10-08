"""基于 Taskiq 和 RabbitMQ 的文档摄取异步任务队列适配器。

队列只负责把一条消息执行一次：重试预算、退避与终态都是 ``ingestion_jobs`` 行的属性，由
``IngestionDispatch`` 对账投递，所以这里没有重试中间件，异常只会把消息交给死信队列供观测。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from taskiq.receiver import Receiver
from taskiq_aio_pika import AioPikaBroker, Queue

from application.ingestion.dispatch import JobDispatchError
from domain.knowledge import IngestionJob, IngestionStage

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import CoroutineType

    from taskiq import AsyncBroker
    from taskiq.decor import AsyncTaskiqDecoratedTask

    from infrastructure.observability.langfuse_tracing import Tracing

    StageRunner = Callable[[IngestionStage, UUID, UUID], Awaitable[IngestionJob | None]]

log = structlog.get_logger(__name__)

INGESTION_STAGE_TASK_NAME = "rag.run_ingestion_stage"
TASK_QUEUE_NAME = "taskiq"
DEAD_LETTER_QUEUE_NAME = "taskiq.dead_letter"


class IngestionJobQueue:
    """管理 Taskiq RabbitMQ Broker：拓扑结构、重试策略与任务收发。"""

    def __init__(
        self,
        *,
        rabbitmq_url: str,
        tracing: Tracing,
        prefetch_count: int,
        dispatch_timeout_seconds: int,
    ) -> None:
        self._tracing = tracing
        self._dispatch_timeout_seconds = dispatch_timeout_seconds
        self._lock = asyncio.Lock()
        self._started = False
        self._stage_runner: StageRunner | None = None
        self._broker = _create_broker(
            rabbitmq_url=rabbitmq_url,
            prefetch_count=prefetch_count,
        )
        self._task = _declare_ingestion_task(
            self._broker,
            self._run_delivery,
        )

    def supply_stage_runner(self, runner: StageRunner) -> None:
        """注入 Worker 进程构建好的阶段执行回调函数。"""
        self._stage_runner = runner

    async def _run_delivery(self, stage: str, document_version_id: str, job_id: str) -> None:
        runner = self._stage_runner
        if runner is None:
            raise RuntimeError("当前队列未装配阶段执行器: Worker 必须注入执行函数")
        observation = self._tracing.start(
            name=f"ingestion.{stage}",
            metadata={
                "stage": stage,
                "document_version_id": document_version_id,
                "job_id": job_id,
            },
        )
        try:
            next_job = await runner(
                IngestionStage(stage),
                UUID(document_version_id),
                UUID(job_id),
            )
        except Exception as error:
            self._tracing.finish(
                observation,
                error_class=type(error).__name__,
                error_message=str(error),
            )
            raise
        self._tracing.finish(observation, output_text=f"{stage} 尝试执行完成")
        if next_job is not None:
            await self._publish_next_job(next_job)

    @property
    def broker(self) -> AsyncBroker:
        return self._broker

    async def dispatch_stage(
        self,
        *,
        stage: IngestionStage,
        document_version_id: UUID,
        job_id: UUID,
    ) -> None:
        """发布指定阶段的任务消息至消息队列。"""
        try:
            async with asyncio.timeout(self._dispatch_timeout_seconds):
                await self._start()
                await self._task.kiq(stage.value, str(document_version_id), str(job_id))
        except TimeoutError as error:
            raise JobDispatchError(
                f"{stage.value} 作业 {job_id} 在 {self._dispatch_timeout_seconds} 秒内未发布成功"
            ) from error
        except Exception as error:
            raise JobDispatchError(
                f"文档版本 {document_version_id} 的 {stage.value} 作业 "
                f"{job_id} 发布失败: {type(error).__name__}"
            ) from error
        log.info(
            "任务已分发至消息队列",
            stage=stage.value,
            document_version_id=str(document_version_id),
            job_id=str(job_id),
        )

    async def _publish_next_job(self, job: IngestionJob) -> None:
        """阶段完成后立即投递下一阶段消息：提示投递，漏投由对账补上。"""
        try:
            await self.dispatch_stage(
                stage=job.stage,
                document_version_id=job.document_version_id,
                job_id=job.id,
            )
        except JobDispatchError as error:
            log.warning(
                "下一阶段摄取任务分发失败",
                stage=job.stage.value,
                document_version_id=str(job.document_version_id),
                job_id=str(job.id),
                error_class=type(error).__name__,
            )

    async def shutdown(self) -> None:
        """关闭消息队列 Broker 连接。"""
        if not self._started:
            return
        self._started = False
        await self._broker.shutdown()

    async def consume(self, *, stop: asyncio.Event, max_async_tasks: int) -> None:
        """持续消费任务队列消息直到 stop 事件被触发。"""
        self._broker.is_worker_process = True
        await self._start()
        receiver = Receiver(
            broker=self._broker,
            run_startup=False,
            max_async_tasks=max_async_tasks,
        )
        try:
            await receiver.listen(stop)
        finally:
            await self.shutdown()

    async def _start(self) -> None:
        async with self._lock:
            if self._started:
                return
            await self._broker.startup()
            self._started = True


def _create_broker(
    *,
    rabbitmq_url: str,
    prefetch_count: int,
) -> AioPikaBroker:
    return AioPikaBroker(
        rabbitmq_url,
        task_queues=[Queue(name=TASK_QUEUE_NAME)],
        dead_letter_queue=Queue(name=DEAD_LETTER_QUEUE_NAME),
        qos=prefetch_count,
    )


def _declare_ingestion_task(
    broker: AioPikaBroker,
    run_delivery: Callable[[str, str, str], Awaitable[None]],
) -> AsyncTaskiqDecoratedTask[[str, str, str], CoroutineType[Any, Any, None]]:
    @broker.task(task_name=INGESTION_STAGE_TASK_NAME)
    async def run_ingestion_stage(
        stage: str,
        document_version_id: str,
        job_id: str,
    ) -> None:
        await run_delivery(stage, document_version_id, job_id)

    return run_ingestion_stage  # pyright: ignore[reportReturnType]
