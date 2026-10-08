"""Markdown 语义块扫描与块边界识别。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.chunks.model import BlockType

if TYPE_CHECKING:
    from collections.abc import Sequence

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_PATTERN = re.compile(r"^(`{3,}|~{3,})(.*)$")
LIST_ITEM_PATTERN = re.compile(r"^([ \t]*)(?:-|\*|\+|\d+[.)])([ \t]+)\S")
IMAGE_PATTERN = re.compile(r"^!\[[^\]]*\]\([^)]*\)$")


@dataclass(frozen=True, slots=True)
class MarkdownBlock:
    """Markdown 语义块（类型、层级标题路径及行号区间）"""

    block_type: BlockType
    heading_path: tuple[str, ...]
    line_start: int
    line_end: int


def lines_of(markdown: str) -> list[str]:
    """将 Markdown 拆分为按 1 起始的行列表"""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def scan_blocks(lines: Sequence[str]) -> list[MarkdownBlock]:
    """顺序扫描各行并识别语义块，维护标题层级栈"""
    blocks: list[MarkdownBlock] = []
    heading_path: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        number = index + 1
        heading = HEADING_PATTERN.match(line)
        if heading is not None:
            level = len(heading.group(1))
            del heading_path[level - 1 :]
            heading_path.append((level, heading.group(2).strip()))
            blocks.append(MarkdownBlock(BlockType.HEADING, path_of(heading_path), number, number))
            index += 1
            continue
        path = path_of(heading_path)
        if FENCE_PATTERN.match(line) is not None:
            end = fence_end(lines, index)
            blocks.append(MarkdownBlock(BlockType.CODE, path, number, end + 1))
            index = end + 1
            continue
        if is_table_row(line):
            end = index
            while end + 1 < len(lines) and is_table_row(lines[end + 1]):
                end += 1
            blocks.append(MarkdownBlock(BlockType.TABLE, path, number, end + 1))
            index = end + 1
            continue
        if LIST_ITEM_PATTERN.match(line) is not None:
            end = list_end(lines, index)
            blocks.append(MarkdownBlock(BlockType.LIST, path, number, end + 1))
            index = end + 1
            continue
        if IMAGE_PATTERN.match(line.strip()) is not None:
            blocks.append(MarkdownBlock(BlockType.IMAGE, path, number, number))
            index += 1
            continue
        end = index
        while end + 1 < len(lines) and is_paragraph_line(lines[end + 1]):
            end += 1
        blocks.append(MarkdownBlock(BlockType.PARAGRAPH, path, number, end + 1))
        index = end + 1
    return blocks


def path_of(heading_path: Sequence[tuple[int, str]]) -> tuple[str, ...]:
    """获取当前层级作用域内的所有标题文本列表"""
    return tuple(title for _level, title in heading_path)


def is_table_row(line: str) -> bool:
    """判断是否为 Markdown 表格行"""
    stripped = line.strip()
    return len(stripped) > 1 and stripped.startswith("|") and stripped.endswith("|")


def is_table_separator(line: str) -> bool:
    """判断是否为 Markdown 表格分割对齐行"""
    stripped = line.strip()
    return is_table_row(line) and set(stripped) <= set("|-: ")


def is_paragraph_line(line: str) -> bool:
    """判断指定行是否属于当前段落的延续行"""
    if not line.strip():
        return False
    return not (
        HEADING_PATTERN.match(line) is not None
        or FENCE_PATTERN.match(line) is not None
        or is_table_row(line)
        or LIST_ITEM_PATTERN.match(line) is not None
        or IMAGE_PATTERN.match(line.strip()) is not None
    )


def fence_end(lines: Sequence[str], start: int) -> int:
    """寻找闭合代码块围栏的行索引"""
    fence = FENCE_PATTERN.match(lines[start])
    if fence is None:
        return start
    marker = fence.group(1)
    index = start + 1
    while index < len(lines):
        stripped = lines[index].strip()
        if len(stripped) >= len(marker) and set(stripped) == {marker[0]}:
            return index
        index += 1
    return len(lines) - 1


def list_end(lines: Sequence[str], start: int) -> int:
    """寻找列表块的结束行索引"""
    index = start
    while index + 1 < len(lines):
        candidate = lines[index + 1]
        if LIST_ITEM_PATTERN.match(candidate) is not None:
            index += 1
            continue
        if candidate.strip() and candidate[:1] in " \t":
            index += 1
            continue
        if not candidate.strip() and next_line_is_item(lines, index + 2):
            index += 1
            continue
        break
    return index


def next_line_is_item(lines: Sequence[str], start: int) -> bool:
    """判断后续第一个非空行是否属于列表项或其缩进内容"""
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        return LIST_ITEM_PATTERN.match(line) is not None or line[:1] in " \t"
    return False


def fence_marker(line: str) -> str | None:
    """提取代码围栏起始字符，非代码围栏返回 None"""
    fence = FENCE_PATTERN.match(line)
    return None if fence is None else fence.group(1)


def closes_fence(line: str, marker: str) -> bool:
    """判断指定行是否能闭合代码围栏"""
    stripped = line.strip()
    return len(stripped) >= len(marker) and set(stripped) == {marker[0]}
