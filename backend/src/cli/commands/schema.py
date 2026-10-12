"""schema-init / schema-reset 命令：从 ORM 模型建立或清空业务 schema。"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from composition.cli.runtime import SchemaRuntime


def schema_init(runtime: SchemaRuntime) -> int:
    """幂等建立缺失的业务表与检索扩展，不触碰已有数据。"""
    try:
        created = asyncio.run(_create(runtime))
    except Exception as error:
        print(f"错误: 建立业务 schema 失败: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    state = f"新建 {len(created)} 张表: {', '.join(created)}" if created else "结构已是最新"
    print(f"schema 已就绪；{state}")
    return 0


def schema_reset(runtime: SchemaRuntime) -> int:
    """清空并重建全部业务表（开发循环破坏性操作）。"""
    try:
        dropped, created = asyncio.run(_reset(runtime))
    except Exception as error:
        print(f"错误: 重建业务 schema 失败: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(f"已删除 {len(dropped)} 张表: {', '.join(dropped) or '-'}")
    print(f"已新建 {len(created)} 张表: {', '.join(created) or '-'}")
    return 0


async def _create(runtime: SchemaRuntime) -> tuple[str, ...]:
    try:
        return await runtime.bootstrap.create()
    finally:
        await runtime.close()


async def _reset(runtime: SchemaRuntime) -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        return await runtime.bootstrap.reset()
    finally:
        await runtime.close()
