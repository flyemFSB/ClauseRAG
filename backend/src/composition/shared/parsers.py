"""文档解析器路由映射表装配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.parsing import ParseRoute
from infrastructure.parsing.anydoc_parser import AnyDocParser
from infrastructure.parsing.html_parser import HtmlParser
from infrastructure.parsing.paddleocr_parser import PaddleOcrParser
from infrastructure.parsing.plain_text_parser import PlainTextParser

if TYPE_CHECKING:
    from collections.abc import Mapping

    from application.ingestion.parsers import DocumentParser
    from infrastructure.config.settings import Settings


def open_parsers(settings: Settings) -> Mapping[ParseRoute, DocumentParser]:
    """按解析路由构建文档解析器字典映射。"""
    return {
        ParseRoute.ANYDOC: AnyDocParser(),
        ParseRoute.HTML: HtmlParser(),
        ParseRoute.PLAIN_TEXT: PlainTextParser(),
        ParseRoute.OCR: PaddleOcrParser(
            api_key=settings.paddleocr_api_key.get_secret_value(),
            base_url=settings.paddleocr_base_url,
            model=settings.paddleocr_model,
            request_timeout_seconds=settings.paddleocr_request_timeout_seconds,
            poll_interval_seconds=settings.paddleocr_poll_interval_seconds,
            poll_timeout_seconds=settings.paddleocr_poll_timeout_seconds,
        ),
    }
