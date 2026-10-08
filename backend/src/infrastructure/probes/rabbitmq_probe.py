"""RabbitMQ 消息队列就绪探针。"""

from __future__ import annotations

import aio_pika

from domain.dependency import Dependency


class RabbitMqProbe:
    """RabbitMQ 连通性探针：建立并关闭 AMQP 连接以验证握手与鉴权。"""

    def __init__(self, *, rabbitmq_url: str, timeout_seconds: int) -> None:
        self.dependency = Dependency.RABBITMQ
        self._rabbitmq_url = rabbitmq_url
        self._timeout_seconds = timeout_seconds

    async def probe(self) -> None:
        """执行探活检查，连接拒绝或超时则抛出异常。"""
        connection = await aio_pika.connect_robust(
            self._rabbitmq_url, timeout=self._timeout_seconds
        )
        await connection.close()
