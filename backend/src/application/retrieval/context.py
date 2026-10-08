"""上下文窗口Token预算裁剪与引用来源选择服务。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.citation import select_context

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain.chunks.model import TokenCounter
    from domain.citation import CitationSource
    from domain.retrieval import Candidate, EvidenceDecision, RetrievalBudget


class ContextSelection:
    """在检索预算和渲染后 Token 上限内挑选组装上下文"""

    def __init__(
        self,
        *,
        budget: RetrievalBudget,
        quote_chars: int,
        counter: TokenCounter,
    ) -> None:
        self._budget = budget
        self._quote_chars = quote_chars
        self._counter = counter

    def select(
        self,
        *,
        candidates: Sequence[Candidate],
        evidence: EvidenceDecision,
    ) -> tuple[tuple[CitationSource, ...], int]:
        """按预算选择有效证据并分配引用编号"""
        return select_context(
            candidates,
            accepted=evidence.accepted,
            final_parent_limit=self._budget.final_parent_limit,
            context_token_budget=self._budget.max_context_tokens,
            quote_chars=self._quote_chars,
            counter=self._counter,
        )
