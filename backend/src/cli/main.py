"""CLI 命令行入口：schema 建立、存储初始化、单阶段摄取与索引重建。"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from cli.commands.cleanup import DEFAULT_CLEANUP_LIMIT, cleanup_pending
from cli.commands.evaluate import evaluate_ragas
from cli.commands.graph import graph_topology, observability_init
from cli.commands.schema import schema_init, schema_reset
from cli.commands.stages import RUNNABLE_STAGES, parse_version_id, reindex, run_stage
from cli.commands.storage import storage_init
from composition.cli.runtime import (
    build_cleanup_runtime,
    build_reindex_runtime,
    build_run_stage_runtime,
    build_schema_runtime,
    build_storage_runtime,
)
from domain.knowledge import IngestionStage
from infrastructure.config.settings import ConfigurationError, load_settings
from infrastructure.observability.logging import configure_logging

if TYPE_CHECKING:
    from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """解析命令行参数并执行目标子命令。"""
    arguments = _build_parser().parse_args(argv)
    try:
        return _dispatch(arguments)
    except ConfigurationError as error:
        print(f"配置错误: {error}", file=sys.stderr)
        return 2


def _dispatch(arguments: argparse.Namespace) -> int:
    """按需构建对应子命令的轻量运行时并调度执行。"""
    if arguments.command == "storage-init":
        return storage_init(build_storage_runtime())
    if arguments.command == "schema-init":
        return schema_init(build_schema_runtime())
    if arguments.command == "schema-reset":
        return schema_reset(build_schema_runtime())
    if arguments.command == "graph-topology":
        return graph_topology()
    if arguments.command == "observability-init":
        return observability_init(load_settings())
    if arguments.command == "evaluate-ragas":
        return evaluate_ragas(arguments)
    if arguments.command == "cleanup-pending":
        runtime = build_cleanup_runtime()
        configure_logging(service="cli", level=runtime.settings.log_level)
        return cleanup_pending(runtime, arguments.limit)
    # 构建运行时前预先校验版本 UUID，避免无效入参初始化未释放资源
    version_id = parse_version_id(arguments.version_id)
    if version_id is None:
        return 1
    if arguments.command == "run-stage":
        stage = IngestionStage(arguments.stage)
        runtime = build_run_stage_runtime(stage)
        configure_logging(service="cli", level=runtime.settings.log_level)
        return run_stage(runtime, stage, version_id)
    if arguments.command == "reindex":
        runtime = build_reindex_runtime()
        configure_logging(service="cli", level=runtime.settings.log_level)
        return reindex(runtime, version_id)
    raise RuntimeError(f"未实现子命令 {arguments.command} 的执行处理器")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli",
        description="ClauseRAG 平台运维与管理命令行工具。",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "schema-init",
        help="从 ORM 模型幂等建立缺失的业务表与检索扩展，不触碰已有数据",
    )

    commands.add_parser(
        "schema-reset",
        help="破坏性：删除并重建全部业务表（开发循环用；表里现有的数据会全部丢失）",
    )

    commands.add_parser(
        "storage-init",
        help="当 S3 存储桶不存在时自动创建原始文档与制品桶",
    )

    run_stage = commands.add_parser(
        "run-stage",
        help="针对指定文档版本单步执行摄取流水线阶段，并输出执行结果",
    )
    run_stage.add_argument(
        "stage",
        choices=[stage.value for stage in RUNNABLE_STAGES],
        help="待执行阶段: parse (解析), chunk (分块), embed (向量化), index (索引核验)",
    )
    run_stage.add_argument("version_id", help="待处理文档版本的 UUID")

    reindex = commands.add_parser(
        "reindex",
        help="基于已分块产物重建指定文档版本的向量索引并完成核验",
    )
    reindex.add_argument("version_id", help="待重建文档版本的 UUID")

    commands.add_parser(
        "graph-topology",
        help="打印审查 Agent 图拓扑结构、节点流转边与有界循环保护",
    )

    commands.add_parser(
        "observability-init",
        help="当 Langfuse 可观测组件缺失数据库或存储桶时执行初始化",
    )

    evaluate = commands.add_parser(
        "evaluate-ragas",
        help="执行 Ragas 离线评测流水线 (需安装 eval 依赖组)",
    )
    evaluate.add_argument(
        "--mode",
        choices=["smoke"],
        default="smoke",
        help="冒烟验证评测裁判接口及指标结构化输出",
    )

    cleanup = commands.add_parser(
        "cleanup-pending",
        help="执行文档删除后遗留的派生制品与向量清理任务",
    )
    cleanup.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_CLEANUP_LIMIT,
        help=f"单次批处理清理意图的最大数量 (默认 {DEFAULT_CLEANUP_LIMIT})",
    )
    return parser
