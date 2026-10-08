"""基于 html-to-markdown 的 HTML 文档解析适配器。"""

from __future__ import annotations

from importlib.metadata import version as package_version

import html_to_markdown

from domain.parsing import ParsedDocument, UnparseableDocumentError

_OPTIONS = html_to_markdown.ConversionOptions(extract_metadata=False)


class HtmlParser:
    """将 .html 与 .htm 文档转换为标准 Markdown。"""

    name: str = "html-to-markdown"
    version: str = package_version("html-to-markdown")

    async def parse(self, data: bytes, *, filename: str, mime_type: str) -> ParsedDocument:
        """解析 UTF-8 HTML 文本并生成 Markdown。"""
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise UnparseableDocumentError(
                f"{filename} 并非有效的 UTF-8 HTML 文件: {error.reason} (字节位置: {error.start})"
            ) from error
        try:
            result = html_to_markdown.convert(text, _OPTIONS)
        except html_to_markdown.ConversionError as error:
            raise UnparseableDocumentError(f"{filename} 转换失败: {error}") from error
        warnings = tuple(warning.message for warning in result.warnings)
        return ParsedDocument(
            markdown=result.content or "",
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
        )
