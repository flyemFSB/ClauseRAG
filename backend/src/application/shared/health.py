"""外部依赖并发健康探测应用服务。"""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import TYPE_CHECKING, Protocol

from domain.dependency import (
    Dependency,
    DependencyState,
    DependencyStatus,
    ReadinessReport,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class DependencyProbe(Protocol):
    """外部依赖连通性探测接口"""

    dependency: Dependency

    async def probe(self) -> None: ...


class HealthService:
    """聚合探测各项外部依赖就绪状态"""

    def __init__(self, probes: Sequence[DependencyProbe], timeout_seconds: float) -> None:
        self._probes = tuple(probes)
        self._timeout_seconds = timeout_seconds

    async def check_readiness(self) -> ReadinessReport:
        """并发探测所有外部依赖并返回汇总就绪报告"""
        started = perf_counter()
        statuses = await asyncio.gather(*(self._probe(probe) for probe in self._probes))
        return ReadinessReport(
            statuses=tuple(statuses),
            duration_ms=round((perf_counter() - started) * 1000),
        )

    async def _probe(self, probe: DependencyProbe) -> DependencyStatus:
        """带超时限制的单项依赖探测"""
        started = perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await probe.probe()
        except TimeoutError:
            state = DependencyState.UNHEALTHY
            detail = f"probe exceeded {self._timeout_seconds:g}s"
        except Exception as error:
            state = DependencyState.UNHEALTHY
            detail = f"{type(error).__name__}: {error}"
        else:
            state = DependencyState.HEALTHY
            detail = None
        return DependencyStatus(
            dependency=probe.dependency,
            state=state,
            latency_ms=round((perf_counter() - started) * 1000),
            detail=detail,
        )
