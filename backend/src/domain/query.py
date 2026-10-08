"""用户查询理解意图与路由领域模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MAX_REWRITTEN_QUERIES = 2


class QueryIntent(StrEnum):
    """查询意图分类"""

    RETRIEVAL = "retrieval"
    DIRECT_RESPONSE = "direct_response"
    CLARIFICATION = "ask_clarification"


class QueryRoute(StrEnum):
    """图状态流转路由"""

    PLAN_RETRIEVAL = "plan_retrieval"
    DIRECT_RESPONSE = "direct_response"
    ASK_CLARIFICATION = "ask_clarification"


_ROUTES: dict[QueryIntent, QueryRoute] = {
    QueryIntent.RETRIEVAL: QueryRoute.PLAN_RETRIEVAL,
    QueryIntent.DIRECT_RESPONSE: QueryRoute.DIRECT_RESPONSE,
    QueryIntent.CLARIFICATION: QueryRoute.ASK_CLARIFICATION,
}


def route_for(intent: QueryIntent) -> QueryRoute:
    """根据意图返回对应的图执行路由分支"""
    return _ROUTES[intent]


@dataclass(frozen=True, slots=True)
class QueryUnderstanding:
    """查询理解判定结果（意图、检索查询词与降级标记）"""

    intent: QueryIntent
    queries: tuple[str, ...]
    reason: str | None = None
    degraded: bool = False

    @staticmethod
    def fallback(question: str, *, reason: str) -> QueryUnderstanding:
        """模型分类失败时的降级方案（回退为默认检索意图，使用原查询词）"""
        return QueryUnderstanding(
            intent=QueryIntent.RETRIEVAL,
            queries=(question,),
            reason=reason,
            degraded=True,
        )
