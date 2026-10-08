"""系统外部依赖健康状态值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Dependency(StrEnum):
    """关键外部服务组件枚举"""

    POSTGRES = "postgres"
    QDRANT = "qdrant"
    RABBITMQ = "rabbitmq"
    RUSTFS = "rustfs"


class DependencyState(StrEnum):
    """依赖可用性状态"""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """单项外部依赖探测结果"""

    dependency: Dependency
    state: DependencyState
    latency_ms: int
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """全量外部依赖就绪检查报告"""

    statuses: tuple[DependencyStatus, ...]
    duration_ms: int

    @property
    def ready(self) -> bool:
        """所有依赖均健康时返回 True"""
        return all(status.state is DependencyState.HEALTHY for status in self.statuses)
