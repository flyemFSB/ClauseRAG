"""引用标记解析与来源回表服务。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from domain.citation import (
    CitationPolicy,
    CitationSource,
    CitationValidationError,
    quote_from_content,
    validate_answer,
)
from domain.conversation import CitationRecord

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from application.retrieval.chunks import ChunkStore

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedAnswer:
    """完成引用校验与回表解析后的回答文本与引用列表"""

    text: str
    citations: tuple[CitationRecord, ...]
    removed_ids: tuple[str, ...]

    @property
    def covered(self) -> bool:
        """回答是否至少携带一个可回表的合法引用"""
        return bool(self.citations)


class CitationService:
    """回答引用标记解析与权威元数据回表服务"""

    def __init__(
        self,
        *,
        chunks: ChunkStore,
        policy: CitationPolicy,
        quote_chars: int,
    ) -> None:
        self._chunks = chunks
        self._policy = policy
        self._quote_chars = quote_chars

    async def resolve(
        self,
        *,
        knowledge_base_id: UUID,
        answer: str,
        sources: Sequence[CitationSource],
    ) -> ResolvedAnswer:
        """校验回答引用标记并回表补充完整的文档元数据与引用摘要"""
        validated = validate_answer(answer, sources=sources, policy=self._policy)
        if not validated.cited_ids:
            return ResolvedAnswer(
                text=validated.text,
                citations=(),
                removed_ids=validated.removed_ids,
            )
        by_label = {source.citation_id: source for source in sources}
        cited_sources = [by_label[citation_id] for citation_id in validated.cited_ids]
        records = await self._chunks.load_records(
            knowledge_base_id=knowledge_base_id,
            child_ids=[source.child_id for source in cited_sources],
        )
        citations: list[CitationRecord] = []
        unresolvable: list[str] = []
        for source in cited_sources:
            record = records.get(source.child_id)
            if record is None:
                unresolvable.append(source.citation_id)
                continue
            citations.append(
                CitationRecord(
                    citation_id=source.citation_id,
                    child_id=record.child_id,
                    parent_id=record.parent_id,
                    document_id=record.document_id,
                    document_version_id=record.document_version_id,
                    document_name=record.document_name,
                    heading_path=record.heading_path,
                    line_start=record.line_start,
                    line_end=record.line_end,
                    quote=quote_from_content(record.content, max_chars=self._quote_chars),
                )
            )
        removed = (*validated.removed_ids, *unresolvable)
        if unresolvable and self._policy is CitationPolicy.REJECT:
            raise CitationValidationError("回答引用的文本块已不存在: " + ", ".join(unresolvable))
        text = validated.text
        for citation_id in unresolvable:
            text = text.replace(f"[{citation_id}]", "")
        if removed:
            log.warning(
                "无效引用标记已移除",
                removed=len(removed),
                policy=self._policy.value,
                resolved=len(citations),
            )
        return ResolvedAnswer(
            text=text.strip(),
            citations=tuple(citations),
            removed_ids=removed,
        )
