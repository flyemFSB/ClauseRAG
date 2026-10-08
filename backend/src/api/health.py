"""健康检查路由：存活探针（liveness）与就绪探针（readiness）。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from application.shared.health import HealthService
from domain.dependency import Dependency, DependencyState


class LivenessResponse(BaseModel):
    """存活探针响应"""

    status: Literal["alive"] = "alive"


class DependencyHealth(BaseModel):
    """单项外部依赖健康状态"""

    name: Dependency
    state: DependencyState
    latency_ms: int
    detail: str | None = None


class ReadinessResponse(BaseModel):
    """就绪探针响应"""

    status: Literal["ready", "unavailable"]
    duration_ms: int
    dependencies: list[DependencyHealth]


def create_health_router(health: HealthService) -> APIRouter:
    """构建健康检查路由"""
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/live")
    async def live() -> LivenessResponse:
        """服务存活检查（不探测外部依赖）"""
        return LivenessResponse()

    @router.get("/ready")
    async def ready(response: Response) -> ReadinessResponse:
        """外部依赖就绪检查（任一依赖异常返回 503）"""
        report = await health.check_readiness()
        if not report.ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="ready" if report.ready else "unavailable",
            duration_ms=report.duration_ms,
            dependencies=[
                DependencyHealth(
                    name=probe_status.dependency,
                    state=probe_status.state,
                    latency_ms=probe_status.latency_ms,
                    detail=probe_status.detail,
                )
                for probe_status in report.statuses
            ],
        )

    return router
