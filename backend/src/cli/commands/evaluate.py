"""RAGAS 评测子命令：先验证 judge 可用性，再按已完成的阶段执行对应模式。"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from infrastructure.config.settings import load_settings

if TYPE_CHECKING:
    import argparse

    from infrastructure.evaluation.engine import JudgeConfig, MetricScore


async def _smoke(config: JudgeConfig) -> tuple[MetricScore, ...]:
    from infrastructure.evaluation import engine

    async with engine.RagasEngine(config) as runner:
        return await runner.smoke()


def _print_smoke(config: JudgeConfig, scores: tuple[MetricScore, ...]) -> int:
    print(f"judge      {config.judge_model} @ {config.base_url}")
    print(f"embeddings {config.embedding_model}")
    print(f"cache      {config.cache_dir}")
    failed = 0
    for score in scores:
        detail = f"value={score.value:.4f}" if score.value is not None else (score.reason or "")
        line = f"  {score.name:38} {score.status:7} {score.latency_ms:5}ms  {detail}"
        print(line.rstrip())
        if score.status != "ok":
            failed += 1
            if score.error_class:
                print(f"      {score.error_class}: {score.error_message}")
    if failed:
        print(
            f"冒烟测试未通过: {len(scores)} 项指标中有 {failed} 项未返回有效评分 (smoke failed)",
            file=sys.stderr,
        )
        return 1
    print(f"冒烟测试通过: 全量 {len(scores)} 项指标均成功返回评分 (smoke passed)")
    return 0


def evaluate_ragas(arguments: argparse.Namespace) -> int:
    """执行评测命令。

    RAGAS 引擎在函数内延迟导入：`python -m cli` 与其它运维子命令不需要安装 `eval` 依赖组，
    而服务进程也永远不会加载评测库。
    """
    try:
        from infrastructure.evaluation.engine import judge_config
    except ModuleNotFoundError as error:
        print(f"评测环境依赖不可用: {error}", file=sys.stderr)
        return 2
    if arguments.mode != "smoke":
        # trace / deterministic / ragas 三个阶段尚未实现；这里显式失败而不是静默降级。
        print(f"模式 --mode {arguments.mode} 尚未实现", file=sys.stderr)
        return 2
    config = judge_config(load_settings())
    return _print_smoke(config, asyncio.run(_smoke(config)))
