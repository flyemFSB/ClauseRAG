"""引用标记规范与校验领域模型。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from uuid import UUID

    from domain.chunks.model import TokenCounter
    from domain.retrieval import Candidate

CITATION_LABEL_PREFIX = "S"
_BLOCK_OPEN = "[source:"
_BLOCK_CLOSE = "[/source:"
_CITATION_MARKER = re.compile(r"\[S(\d+)\]")
_BLOCK_MARKER = re.compile(r"\[/?source:S\d+\]")
_ANY_MARKER = re.compile(r"\[/?source:S\d+\]|\[S\d+\]")
_SECTION_ID = "Section: see"


class CitationPolicy(StrEnum):
    """未召回或非法引用标记的处理策略"""

    STRIP = "strip"
    """从回答文本中剥离非法引用标记"""

    REJECT = "reject"
    """直接拒绝回答并触发校验异常"""


class CitationValidationError(Exception):
    """引用标记校验未通过异常"""


@dataclass(frozen=True, slots=True)
class CitationSource:
    """提供给大模型参考的单项来源块（附带请求级引用编号）

    ``context_text`` 是父块的聚合正文，只用于生成上下文；``quote`` 与行号区间来自命中的
    子块，只用于读者回查。两者不共用同一个字段，因此父块文本永远不会变成引用原文。
    """

    citation_id: str
    child_id: UUID
    parent_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_name: str
    heading_path: tuple[str, ...]
    line_start: int
    line_end: int
    context_text: str
    quote: str
    parent_citation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValidatedAnswer:
    """完成引用校验与过滤后的模型回答结果"""

    text: str
    cited_ids: tuple[str, ...]
    removed_ids: tuple[str, ...]


def quote_from_content(content: str, *, max_chars: int) -> str:
    """截取首段内容作为引用摘要，尽量在换行符边界处截断"""
    if len(content) <= max_chars:
        return content
    window = content[:max_chars]
    boundary = window.rfind("\n")
    if boundary <= 0:
        return window
    return window[:boundary]


def sanitized(text: str) -> str:
    """剔除被引用正文里自带的全部协议标记（块标记与 `[S#]`）

    文档正文不能自己携带协议标记，否则它可以伪造一个引用块、提前闭合一个块，或者直接给模型
    一个后端随后不得不拒绝的编号。
    """
    return _ANY_MARKER.sub("", text)


def render_source_block(source: CitationSource) -> str:
    """将单个引用源渲染为上下文提示词块

    同一父块的后续来源不再重复正文，而是指回该父块首次出现的编号：父块正文进提示词
    一次，子块锚点各占一个编号。
    """
    lines = [
        f"{_BLOCK_OPEN}{source.citation_id}]",
        f"Document: {source.document_name}",
        f"Heading: {' > '.join(source.heading_path) if source.heading_path else '(none)'}",
    ]
    if source.parent_citation_id is None:
        lines.append(f"Content: {sanitized(source.context_text)}")
    else:
        lines.append(f"{_SECTION_ID} [{source.parent_citation_id}]")
    lines.append(f"Passage: {sanitized(source.quote)}")
    lines.append(f"{_BLOCK_CLOSE}{source.citation_id}]")
    return "\n".join(lines)


def render_context(sources: Sequence[CitationSource]) -> str:
    """将所有引用源拼接为最终的上下文提示词文本"""
    return "\n\n".join(render_source_block(source) for source in sources)


def label_of(index: int) -> str:
    """生成第 index 个引用来源的标签（从 1 起始）"""
    return f"{CITATION_LABEL_PREFIX}{index}"


def select_context(
    candidates: Sequence[Candidate],
    *,
    accepted: Collection[UUID],
    final_parent_limit: int,
    context_token_budget: int,
    quote_chars: int,
    counter: TokenCounter,
) -> tuple[tuple[CitationSource, ...], int]:
    """按父块聚合候选块，在渲染后的 token 预算内挑选上下文并分配引用编号

    预算以实际渲染文本计量（文档名、标题路径、分隔标记与父块正文都计入），因此它衡量的
    是提示词里真正出现的内容，而不是子块的记账 token 数。预算不足时整组父块跳过。
    """
    grouped: dict[UUID, list[Candidate]] = {}
    order: list[UUID] = []
    for candidate in candidates:
        if candidate.child_id not in accepted:
            continue
        if candidate.parent_id not in grouped:
            order.append(candidate.parent_id)
        grouped.setdefault(candidate.parent_id, []).append(candidate)

    sources: list[CitationSource] = []
    used_tokens = 0
    for parent_id in order[:final_parent_limit]:
        first_of_parent: str | None = None
        for candidate in sorted(grouped[parent_id], key=lambda item: item.ordinal):
            record = candidate.record
            source = CitationSource(
                citation_id=label_of(len(sources) + 1),
                child_id=record.child_id,
                parent_id=record.parent_id,
                document_id=record.document_id,
                document_version_id=record.document_version_id,
                document_name=record.document_name,
                heading_path=record.heading_path,
                line_start=record.line_start,
                line_end=record.line_end,
                context_text=record.parent_content,
                quote=quote_from_content(record.content, max_chars=quote_chars),
                parent_citation_id=first_of_parent,
            )
            tokens = counter.count(render_source_block(source))
            if used_tokens + tokens > context_token_budget:
                if first_of_parent is None:
                    break
                continue
            used_tokens += tokens
            sources.append(source)
            if first_of_parent is None:
                first_of_parent = source.citation_id
    return tuple(sources), used_tokens


def emitted_ids(answer: str) -> tuple[str, ...]:
    """提取回答中出现的所有引用编号（按首次出现顺序去重）"""
    seen: dict[str, None] = {}
    for match in _CITATION_MARKER.finditer(answer):
        seen.setdefault(f"{CITATION_LABEL_PREFIX}{match.group(1)}", None)
    return tuple(seen)


def validate_answer(
    answer: str,
    *,
    sources: Sequence[CitationSource],
    policy: CitationPolicy,
) -> ValidatedAnswer:
    """校验回答中的引用标记是否在有效上下文范围内

    这里只剥离块标记；有效引用编号必须原样保留（回答文本与流式片元是一份文本），未召回的编号
    按策略拒绝或逐个移除。
    """
    labels = {source.citation_id for source in sources}
    cited: list[str] = []
    removed: list[str] = []
    for citation_id in emitted_ids(answer):
        if citation_id in labels:
            cited.append(citation_id)
        else:
            removed.append(citation_id)
    if removed and policy is CitationPolicy.REJECT:
        raise CitationValidationError(
            f"回答中包含超出当前请求证据集的无效引用标记: {', '.join(removed)}"
        )
    text = _BLOCK_MARKER.sub("", answer)
    for citation_id in removed:
        text = text.replace(f"[{citation_id}]", "")
    return ValidatedAnswer(
        text=text.strip(),
        cited_ids=tuple(cited),
        removed_ids=tuple(removed),
    )
