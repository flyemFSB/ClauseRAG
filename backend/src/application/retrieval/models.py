"""检索结果、诊断信息与检查点记录模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.citation import CitationSource
    from domain.retrieval import Candidate, ChannelResult, EvidenceDecision, RerankReport


@dataclass(frozen=True, slots=True)
class RetrievalDiagnostics:
    """单轮检索各渠道、融合与重排诊断信息"""

    channels: tuple[ChannelResult, ...]
    fused: tuple[Candidate, ...]
    reranked: tuple[Candidate, ...]
    rerank: RerankReport


@dataclass(frozen=True, slots=True)
class RetrievalRecord:
    """智能体运行检查点所需持久化的精简检索结果"""

    evidence: EvidenceDecision
    sources: tuple[CitationSource, ...]
    context: str
    context_tokens: int


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """完整检索结果（包含证据决策、引用来源、上下文文本及详细诊断）"""

    evidence: EvidenceDecision
    sources: tuple[CitationSource, ...]
    context: str
    context_tokens: int
    diagnostics: RetrievalDiagnostics

    @property
    def record(self) -> RetrievalRecord:
        """提取仅包含回答与校验所需核心数据的记录切片"""
        return RetrievalRecord(
            evidence=self.evidence,
            sources=self.sources,
            context=self.context,
            context_tokens=self.context_tokens,
        )
