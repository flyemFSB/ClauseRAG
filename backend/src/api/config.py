"""运行中进程的生效配置路由。

前端的两张配置页（系统设置、模型配置）展示的必须是 **本进程实际读到的值**：`.env` 与进程环境可以
覆盖任意一项，页面看到的就是覆盖后的结果，而不是代码里的默认值。在此之前那两张页只能抄手册，改
了配置也无从确认有没有生效。

载荷在装配时算好再传进来，而不是在这里读 `Settings`：`Settings` 是冻结的，进程一起就定了，而
`api` 层按依赖方向不许碰 `infrastructure`（见 `scripts/check-architecture.py`）。由 composition
把读到的值渲染成响应，这里只负责提供它。
"""

from __future__ import annotations

from fastapi import APIRouter

from api.config_schemas import ConfigResponse


def create_config_router(payload: ConfigResponse) -> APIRouter:
    """构建生效配置只读路由。"""
    router = APIRouter(prefix="/api/v1", tags=["config"])

    @router.get("/config")
    async def config() -> ConfigResponse:
        """返回本进程读到的全部生效配置（密钥项只报是否已配置）。"""
        return payload

    return router
