"""解析产物 Markdown 确定性标准化算法。"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain.parsing import ParsedDocument

_ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_BULLET_MARKER = re.compile(r"^(\s*)[*+]([ \t]+)")
_ORDERED_MARKER = re.compile(r"^(\s*)(\d+)[.)]([ \t]+)")
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_TABLE_CELL = re.compile(r"(?<!\\)\|")


def normalize_parsed_document(document: ParsedDocument) -> ParsedDocument:
    """标准化解析文档 Markdown 文本"""
    source_lines = document.markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kept = _normalize_lines(source_lines)
    markdown = "".join(f"{line}\n" for line in kept)
    return replace(document, markdown=markdown)


def _normalize_lines(lines: Sequence[str]) -> list[str]:
    """标准化各行内容并返回保留下来的行"""
    lines = list(lines)
    if lines:
        lines[0] = lines[0].lstrip("\ufeff")
    kept: list[tuple[int, str]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        if fence is not None:
            kept.append((index, line))
            if _closes_fence(line, fence):
                fence = None
            continue
        opening = _FENCE_OPEN.match(line)
        if opening is not None:
            fence = opening.group(1)
            kept.append((index, line.rstrip()))
            continue
        if not line.strip():
            if kept and kept[-1][1] != "":
                kept.append((index, ""))
            continue
        kept.append((index, _normalize_content_line(line)))
    while kept and kept[-1][1] == "":
        kept.pop()
    return [line for _index, line in kept]


def _normalize_content_line(line: str) -> str:
    """标准化单行普通文本内容（标题、列表标记与表格对齐）"""
    stripped = line.strip()
    indent = line[: len(line) - len(line.lstrip(" \t"))]
    if len(indent) <= 3 and "\t" not in indent:
        heading = _ATX_HEADING.match(line)
        if heading is not None:
            title = heading.group(2).strip()
            if title:
                return f"{heading.group(1)} {title}"
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            return _normalize_table_row(stripped)
    bullet = _BULLET_MARKER.match(line)
    if bullet is not None:
        return f"{bullet.group(1)}- {line[bullet.end() :].rstrip()}"
    ordered = _ORDERED_MARKER.match(line)
    if ordered is not None:
        item = line[ordered.end() :].rstrip()
        return f"{ordered.group(1)}{ordered.group(2)}. {item}"
    return line.rstrip()


def _normalize_table_row(stripped: str) -> str:
    """标准化表格行单元格空格填充"""
    cells = _TABLE_CELL.split(stripped)[1:-1]
    return f"| {' | '.join(cell.strip() for cell in cells)} |"


def _closes_fence(line: str, fence: str) -> bool:
    """判断当前行是否闭合代码围栏"""
    stripped = line.strip()
    return len(stripped) >= len(fence) and set(stripped) == {fence[0]}
