"""多路检索渠道并发扇出与结果归并。"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from domain.retrieval import (
    ChannelMatch,
    ChannelResult,
    ChannelStatus,
    rank_channel_matches,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from application.retrieval.channels import RetrievalChannel
    from domain.retrieval import RetrievalBudget


log = structlog.get_logger(__name__)


def elapsed_ms(started: float) -> int:
    """计算耗时毫秒数"""
    return int((time.perf_counter() - started) * 1000)


class ChannelFanOut:
    """多渠道并发检索调度器"""

    def __init__(
        self,
        *,
        channels: Sequence[RetrievalChannel],
        budget: RetrievalBudget,
        timeout_seconds: int,
    ) -> None:
        self._channels = tuple(channels)
        self._budget = budget
        self._timeout_seconds = timeout_seconds

    async def run(
        self,
        *,
        knowledge_base_id: UUID,
        queries: Sequence[str],
    ) -> tuple[ChannelResult, ...]:
        """并发请求所有检索渠道并收集执行结果"""
        return await self._run_channels(knowledge_base_id=knowledge_base_id, queries=queries)

    async def _run_channels(
        self,
        *,
        knowledge_base_id: UUID,
        queries: Sequence[str],
    ) -> tuple[ChannelResult, ...]:
        """使用任务组并发执行各渠道检索并记录耗时"""
        started = time.perf_counter()
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(
                    self._run_channel(channel, knowledge_base_id=knowledge_base_id, queries=queries)
                )
                for channel in self._channels
            ]
        results = tuple(task.result() for task in tasks)
        log.info(
            "多渠道检索完成",
            knowledge_base_id=str(knowledge_base_id),
            queries=len(queries),
            channels=len(results),
            hits=sum(len(result.hits) for result in results),
            latency_ms=elapsed_ms(started),
        )
        return results

    async def _run_channel(
        self,
        channel: RetrievalChannel,
        *,
        knowledge_base_id: UUID,
        queries: Sequence[str],
    ) -> ChannelResult:
        """带超时保护执行单个检索渠道并对匹配项进行排序归并"""
        started = time.perf_counter()
        limit = self._budget.top_k_for(channel.channel)
        matches: list[ChannelMatch] = []
        try:
            async with asyncio.timeout(self._timeout_seconds):
                for query in queries:
                    matches.extend(
                        await channel.search(
                            knowledge_base_id=knowledge_base_id,
                            query=query,
                            limit=limit,
                        )
                    )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return ChannelResult.failed(
                channel.channel,
                error_type="TimeoutError",
                latency_ms=elapsed_ms(started),
            )
        except Exception as error:
            log.warning(
                "单检索渠道执行异常",
                channel=channel.channel.value,
                error_type=type(error).__name__,
            )
            return ChannelResult.failed(
                channel.channel,
                error_type=type(error).__name__,
                latency_ms=elapsed_ms(started),
            )
        hits = rank_channel_matches(matches)
        return ChannelResult(
            channel=channel.channel,
            status=ChannelStatus.OK if hits else ChannelStatus.EMPTY,
            hits=hits,
            latency_ms=elapsed_ms(started),
        )
