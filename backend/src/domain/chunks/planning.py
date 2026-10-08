"""块感知确定性分块规划算法与 JSONL 产物序列化。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.chunks.errors import UnchunkableDocumentError
from domain.chunks.keys import chunk_id
from domain.chunks.markdown import lines_of, scan_blocks
from domain.chunks.model import (
    BlockType,
    ChildChunk,
    ChunkKind,
    ChunkPlan,
    ParentChunk,
    TokenCounter,
)
from domain.chunks.policy import (
    CHILD_MAX_TOKENS,
    CHILD_MIN_TOKENS,
    PARENT_MAX_TOKENS,
    PARENT_MIN_TOKENS,
)
from domain.chunks.splitting import BlockPiece, split_block

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from uuid import UUID


@dataclass(frozen=True, slots=True)
class ChunkItem:
    """分组分块单元"""

    index: int
    content: str
    heading_path: tuple[str, ...]
    line_start: int
    line_end: int
    pieces: tuple[BlockPiece, ...]


def plan_chunks(
    markdown: str,
    *,
    document_version_id: UUID,
    counter: TokenCounter,
) -> ChunkPlan:
    """对标准化 Markdown 进行层次化语义分块，生成确定性的父块与子块规划方案"""
    lines = lines_of(markdown)
    warnings: list[str] = []
    pieces: list[BlockPiece] = []
    for block in scan_blocks(lines):
        block_pieces, block_warnings = split_block(block, lines, counter)
        pieces.extend(block_pieces)
        warnings.extend(block_warnings)
    if not pieces:
        raise UnchunkableDocumentError(
            f"文档版本 {document_version_id} 的 Markdown 制品中未扫描到可切分的文本块"
        )

    child_items = [
        ChunkItem(
            index=index,
            content=piece.content,
            heading_path=piece.heading_path,
            line_start=piece.line_start,
            line_end=piece.line_end,
            pieces=(piece,),
        )
        for index, piece in enumerate(pieces)
    ]
    child_groups = group_items(
        child_items,
        counter=counter,
        target=CHILD_MIN_TOKENS,
        limit=CHILD_MAX_TOKENS,
    )
    parent_items = [
        ChunkItem(
            index=index,
            content=join_parts(item.content for item in group),
            heading_path=group[0].heading_path,
            line_start=group[0].line_start,
            line_end=group[-1].line_end,
            pieces=tuple(piece for item in group for piece in item.pieces),
        )
        for index, group in enumerate(child_groups)
    ]
    parent_groups = group_items(
        parent_items,
        counter=counter,
        target=PARENT_MIN_TOKENS,
        limit=PARENT_MAX_TOKENS,
    )

    parents: list[ParentChunk] = []
    children: list[ChildChunk] = []
    for parent_ordinal, parent_group in enumerate(parent_groups, start=1):
        parent_id = chunk_id(document_version_id, ChunkKind.PARENT, parent_ordinal)
        parent_content = join_parts(item.content for item in parent_group)
        parents.append(
            ParentChunk(
                parent_id=parent_id,
                document_version_id=document_version_id,
                heading_path=parent_group[0].heading_path,
                ordinal=parent_ordinal,
                content=parent_content,
                token_count=counter.count(parent_content),
            )
        )
        for child_group in child_groups_of(child_groups, parent_group):
            ordinal = len(children) + 1
            content = join_parts(item.content for item in child_group)
            children.append(
                ChildChunk(
                    child_id=chunk_id(document_version_id, ChunkKind.CHILD, ordinal),
                    parent_id=parent_id,
                    document_version_id=document_version_id,
                    heading_path=child_group[0].heading_path,
                    block_type=dominant_block_type(child_group),
                    ordinal=ordinal,
                    line_start=child_group[0].line_start,
                    line_end=child_group[-1].line_end,
                    content=content,
                    token_count=counter.count(content),
                )
            )
    return ChunkPlan(
        document_version_id=document_version_id,
        parents=tuple(parents),
        children=tuple(children),
        warnings=tuple(warnings),
    )


def render_chunks_jsonl(plan: ChunkPlan) -> bytes:
    """将分块规划结果序列化为 JSONL 字节流（父块在前，随后紧跟其下子块）"""
    children_by_parent: dict[UUID, list[ChildChunk]] = {
        parent.parent_id: [] for parent in plan.parents
    }
    for child in plan.children:
        children_by_parent[child.parent_id].append(child)
    lines: list[str] = []
    for parent in plan.parents:
        lines.append(
            json.dumps(
                {
                    "kind": ChunkKind.PARENT.value,
                    "parent_id": str(parent.parent_id),
                    "document_version_id": str(parent.document_version_id),
                    "heading_path": list(parent.heading_path),
                    "ordinal": parent.ordinal,
                    "token_count": parent.token_count,
                    "content": parent.content,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        for child in children_by_parent[parent.parent_id]:
            lines.append(
                json.dumps(
                    {
                        "kind": ChunkKind.CHILD.value,
                        "child_id": str(child.child_id),
                        "parent_id": str(child.parent_id),
                        "document_version_id": str(child.document_version_id),
                        "heading_path": list(child.heading_path),
                        "block_type": child.block_type.value,
                        "ordinal": child.ordinal,
                        "line_start": child.line_start,
                        "line_end": child.line_end,
                        "token_count": child.token_count,
                        "content": child.content,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
    return "".join(f"{line}\n" for line in lines).encode("utf-8")


def group_items(
    items: Sequence[ChunkItem],
    *,
    counter: TokenCounter,
    target: int,
    limit: int,
) -> list[list[ChunkItem]]:
    """在保持同标题层级约束下，按目标 Token 范围贪心合并相邻单元"""
    groups: list[list[ChunkItem]] = []
    current: list[ChunkItem] = []
    for item in items:
        if current and item.heading_path != current[0].heading_path:
            groups.append(current)
            current = []
        if not current:
            current = [item]
            tokens = counter.count(item.content)
        else:
            candidate = [*current, item]
            tokens = counter.count(join_parts(entry.content for entry in candidate))
            if tokens > limit:
                groups.append(current)
                current = [item]
                tokens = counter.count(item.content)
            else:
                current = candidate
        if tokens >= target:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return merge_tail(groups, counter=counter, limit=limit)


def merge_tail(
    groups: list[list[ChunkItem]],
    *,
    counter: TokenCounter,
    limit: int,
) -> list[list[ChunkItem]]:
    """若尾部剩余微小分块且与前一组属于同标题路径，在不超限前提下合并"""
    if len(groups) < 2:
        return groups
    tail = groups[-1]
    previous = groups[-2]
    if tail[0].heading_path != previous[0].heading_path:
        return groups
    if previous[-1].line_end >= tail[0].line_start:
        return groups
    if counter.count(join_parts(item.content for item in [*previous, *tail])) > limit:
        return groups
    return [*groups[:-2], [*previous, *tail]]


def child_groups_of(
    child_groups: Sequence[list[ChunkItem]],
    parent_group: Sequence[ChunkItem],
) -> list[list[ChunkItem]]:
    """获取父块包含的所有子块单元组"""
    covered = sorted(item.index for item in parent_group)
    return [child_groups[index] for index in covered]


def dominant_block_type(items: Sequence[ChunkItem]) -> BlockType:
    """计算子块中 Token 占比最大的主要语义块类型"""
    best = items[0].pieces[0]
    for item in items:
        for piece in item.pieces:
            if piece.token_count > best.token_count:
                best = piece
    return best.block_type


def join_parts(parts: Iterable[str]) -> str:
    """换行拼接文本片段"""
    return "\n".join(parts)
