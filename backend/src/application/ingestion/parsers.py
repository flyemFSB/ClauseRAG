"""文档解析器抽象接口协议。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.parsing import ParsedDocument


class DocumentParser(Protocol):
    """文档解析器协议：将特定格式文件转换为结构化 Markdown 及页码跨度。"""

    name: str
    """解析器名称，记录在产物元数据中。"""

    version: str
    """解析器或模型版本号。"""

    async def parse(self, data: bytes, *, filename: str, mime_type: str) -> ParsedDocument:
        """解析文件字节数据，返回解析结果或抛出 DocumentParseError 子类异常。"""
        ...
