"""就绪探针与健康检查服务装配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.shared.health import HealthService
from infrastructure.probes.postgres_probe import PostgresProbe
from infrastructure.probes.rabbitmq_probe import RabbitMqProbe
from infrastructure.probes.rustfs_probe import RustFsProbe

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings


def open_health(settings: Settings) -> HealthService:
    """组装覆盖全部外部基础设施依赖的健康检查服务。"""
    timeout_seconds = settings.health_probe_timeout_seconds
    return HealthService(
        probes=(
            PostgresProbe(
                database_url=settings.database_url.get_secret_value(),
                timeout_seconds=timeout_seconds,
            ),
            RabbitMqProbe(
                rabbitmq_url=settings.rabbitmq_url.get_secret_value(),
                timeout_seconds=timeout_seconds,
            ),
            RustFsProbe(
                endpoint_url=settings.s3_endpoint_url,
                access_key=settings.s3_access_key.get_secret_value(),
                secret_key=settings.s3_secret_key.get_secret_value(),
                region=settings.s3_region,
                timeout_seconds=timeout_seconds,
            ),
        ),
        timeout_seconds=timeout_seconds,
    )
