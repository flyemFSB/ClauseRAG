"""业务 API FastAPI 应用装配工厂与共享中间件。"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from api.config import create_config_router
from api.documents import create_documents_router, get_document_catalog
from api.health import create_health_router
from api.knowledge_bases import (
    create_knowledge_bases_router,
    get_knowledge_base_service,
)
from composition.api.config_payload import render_config
from domain.knowledge import KnowledgeNotFoundError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from composition.api.runtime import ApiRuntime


def bind(app: FastAPI, provider: Callable[..., Any], value: object) -> None:
    """将构建好的依赖单例绑定至路由声明的依赖注入函数。"""
    app.dependency_overrides[provider] = lambda: value


def install_shared(app: FastAPI) -> None:
    """安装平台全部 HTTP 应用共享的追踪中间件与全局异常映射。"""

    @app.middleware("http")
    async def bind_request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id", "path")
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(KnowledgeNotFoundError)
    async def handle_knowledge_not_found(
        _request: Request,
        error: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(error)},
        )


def create_app(runtime: ApiRuntime) -> FastAPI:
    """构建业务 API FastAPI 应用并注册各模块路由。"""
    log = structlog.get_logger(__name__)
    settings = runtime.settings

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        log.info("业务API进程启动")
        try:
            yield
        finally:
            await runtime.close()
            log.info("业务API进程停止")

    app = FastAPI(title="RAG platform API", version="0.1.0", lifespan=lifespan)
    install_shared(app)
    bind(app, get_knowledge_base_service, runtime.knowledge_bases)
    bind(app, get_document_catalog, runtime.catalog)

    @app.middleware("http")
    async def bound_request_body(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        declared_length = request.headers.get("content-length")
        if (
            declared_length is not None
            and declared_length.isdigit()
            and int(declared_length) > settings.max_upload_bytes
        ):
            return JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={"detail": (f"the request body exceeds {settings.max_upload_bytes} bytes")},
            )
        return await call_next(request)

    app.include_router(create_health_router(runtime.health))
    app.include_router(create_config_router(render_config(settings)))
    app.include_router(create_knowledge_bases_router())
    app.include_router(create_documents_router())
    return app
