"""针对超长语义块的类型特异性分片算法。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.chunks.markdown import (
    LIST_ITEM_PATTERN,
    MarkdownBlock,
    closes_fence,
    fence_marker,
    is_table_separator,
)
from domain.chunks.model import BlockType, TokenCounter
from domain.chunks.policy import CHILD_MAX_TOKENS, CHUNK_TOKEN_CEILING

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class BlockUnit:
    """块内原子行片段（表格单行、代码单行或列表单个 item）"""

    lines: tuple[str, ...]
    line_start: int
    line_end: int


@dataclass(frozen=True, slots=True)
class BlockPiece:
    """分片后的候选子块片段"""

    block_type: BlockType
    heading_path: tuple[str, ...]
    line_start: int
    line_end: int
    content: str
    token_count: int


def split_block(
    block: MarkdownBlock,
    lines: Sequence[str],
    counter: TokenCounter,
) -> tuple[list[BlockPiece], list[str]]:
    """对超长语义块按类型规则进行安全分片（表格保留表头、代码块保留围栏、列表按项拆分）"""
    block_lines = list(lines[block.line_start - 1 : block.line_end])
    whole = "\n".join(block_lines)
    if counter.count(whole) <= CHILD_MAX_TOKENS:
        piece = piece_of(block, block.line_start, block.line_end, whole, counter)
        return [piece], []

    warnings: list[str] = []
    head: tuple[str, ...] = ()
    tail: tuple[str, ...] = ()
    claim_head_line = False
    if block.block_type is BlockType.TABLE:
        header_size = 2 if len(block_lines) > 1 and is_table_separator(block_lines[1]) else 1
        head = tuple(block_lines[:header_size])
        claim_head_line = True
        body = block_lines[header_size:]
        first_body_line = block.line_start + header_size
    elif block.block_type is BlockType.CODE:
        marker = fence_marker(block_lines[0])
        closes = marker is not None and closes_fence(block_lines[-1], marker)
        head = (block_lines[0],)
        tail = (block_lines[-1],) if closes else ()
        body = block_lines[1:-1] if closes else block_lines[1:]
        first_body_line = block.line_start + 1
    elif block.block_type is BlockType.LIST:
        units, warnings = item_units(block_lines, first_line=block.line_start, counter=counter)
        pieces = assemble(
            block,
            units,
            head=head,
            tail=tail,
            claim_head_line=claim_head_line,
            counter=counter,
        )
        return pieces, warnings
    else:
        body = block_lines
        first_body_line = block.line_start

    if not body:
        text = assemble_text(head, (), tail)
        if counter.count(text) > CHUNK_TOKEN_CEILING:
            warnings.append(
                f"lines {block.line_start}-{block.line_end} hold no line to cut on and were split "
                f"into parts of at most {CHUNK_TOKEN_CEILING} tokens"
            )
        return pieces_of_text(block, text, counter=counter), warnings

    units, warnings = line_units(body, first_line=first_body_line, counter=counter)
    pieces = assemble(
        block,
        units,
        head=head,
        tail=tail,
        claim_head_line=claim_head_line,
        counter=counter,
    )
    return pieces, warnings


def item_units(
    block_lines: Sequence[str],
    *,
    first_line: int,
    counter: TokenCounter,
) -> tuple[list[BlockUnit], list[str]]:
    """将列表块按列表项边界切分为单元"""
    units: list[BlockUnit] = []
    warnings: list[str] = []
    start = 0
    index = 0
    while start < len(block_lines):
        index = max(index, start)
        while index + 1 < len(block_lines):
            candidate = block_lines[index + 1]
            if LIST_ITEM_PATTERN.match(candidate) is not None:
                break
            if candidate.strip() and candidate[:1] in " \t":
                index += 1
                continue
            if not candidate.strip() and next_item_at(block_lines, index + 2):
                index += 1
                continue
            break
        item_lines = tuple(block_lines[start : index + 1])
        units.extend(
            split_unit(
                item_lines,
                line_start=first_line + start,
                counter=counter,
                warnings=warnings,
            )
        )
        start = index + 1
        index = start
    return units, warnings


def next_item_at(lines: Sequence[str], start: int) -> bool:
    """判断后续行是否为新的列表项"""
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if LIST_ITEM_PATTERN.match(line) is not None:
            return True
        return line[:1] in " \t"
    return False


def line_units(
    lines: Sequence[str],
    *,
    first_line: int,
    counter: TokenCounter,
) -> tuple[list[BlockUnit], list[str]]:
    """逐行切分文本块，并在单行超限时二分切断"""
    units: list[BlockUnit] = []
    warnings: list[str] = []
    for offset, line in enumerate(lines):
        units.extend(
            split_unit((line,), line_start=first_line + offset, counter=counter, warnings=warnings)
        )
    return units, warnings


def split_unit(
    lines: tuple[str, ...],
    *,
    line_start: int,
    counter: TokenCounter,
    warnings: list[str],
) -> list[BlockUnit]:
    """检查单单元 Token 数，若超过模型上限则递归二分强制硬切"""
    line_end = line_start + len(lines) - 1
    text = "\n".join(lines)
    if counter.count(text) <= CHUNK_TOKEN_CEILING:
        return [BlockUnit(lines=lines, line_start=line_start, line_end=line_end)]
    parts = hard_split(text, counter=counter)
    warnings.append(
        f"line {line_start} holds {counter.count(text)} tokens and was split into "
        f"{len(parts)} parts of at most {CHUNK_TOKEN_CEILING}"
    )
    return [BlockUnit(lines=(part,), line_start=line_start, line_end=line_end) for part in parts]


def hard_split(text: str, *, counter: TokenCounter) -> tuple[str, ...]:
    """递归二分文本，直到每部分均在安全 Token 上限以内"""
    if len(text) <= 1 or counter.count(text) <= CHUNK_TOKEN_CEILING:
        return (text,)
    middle = len(text) // 2
    return (
        *hard_split(text[:middle], counter=counter),
        *hard_split(text[middle:], counter=counter),
    )


def assemble(
    block: MarkdownBlock,
    units: Sequence[BlockUnit],
    *,
    head: tuple[str, ...],
    tail: tuple[str, ...],
    claim_head_line: bool,
    counter: TokenCounter,
) -> list[BlockPiece]:
    """将原子单元拼装为不超限的片段，每片均复用头部与尾部（如表格头或代码围栏）"""
    if not units:
        return pieces_of_text(block, assemble_text(head, (), tail), counter=counter)

    pieces: list[BlockPiece] = []
    group: list[BlockUnit] = []
    for unit in units:
        candidate = [*group, unit]
        if group and counter.count(assemble_text(head, candidate, tail)) > CHILD_MAX_TOKENS:
            pieces.append(
                assembled_piece(
                    block,
                    group,
                    head=head,
                    tail=tail,
                    claim_head_line=claim_head_line,
                    counter=counter,
                )
            )
            group = [unit]
            continue
        group = candidate
    if group:
        pieces.append(
            assembled_piece(
                block,
                group,
                head=head,
                tail=tail,
                claim_head_line=claim_head_line,
                counter=counter,
            )
        )
    return pieces


def pieces_of_text(block: MarkdownBlock, text: str, *, counter: TokenCounter) -> list[BlockPiece]:
    """从纯文本生成片段，必要时二分硬切"""
    parts = (
        (text,) if counter.count(text) <= CHUNK_TOKEN_CEILING else hard_split(text, counter=counter)
    )
    return [piece_of(block, block.line_start, block.line_end, part, counter) for part in parts]


def assemble_text(head: Sequence[str], units: Sequence[BlockUnit], tail: Sequence[str]) -> str:
    """换行拼接头部、单元行与尾部"""
    return "\n".join([*head, *(line for unit in units for line in unit.lines), *tail])


def assembled_piece(
    block: MarkdownBlock,
    units: Sequence[BlockUnit],
    *,
    head: tuple[str, ...],
    tail: tuple[str, ...],
    claim_head_line: bool,
    counter: TokenCounter,
) -> BlockPiece:
    """从一组单元构建组装后的分片并标记行号跨度"""
    content = assemble_text(head, units, tail)
    return piece_of(
        block,
        block.line_start if claim_head_line else units[0].line_start,
        units[-1].line_end,
        content,
        counter,
    )


def piece_of(
    block: MarkdownBlock,
    line_start: int,
    line_end: int,
    content: str,
    counter: TokenCounter,
) -> BlockPiece:
    """构建单项分片对象"""
    return BlockPiece(
        block_type=block.block_type,
        heading_path=block.heading_path,
        line_start=line_start,
        line_end=line_end,
        content=content,
        token_count=counter.count(content),
    )
