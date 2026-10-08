"""纯文本与 Markdown 文档解析适配器。"""

from __future__ import annotations

from domain.parsing import ParsedDocument, UnparseableDocumentError


class PlainTextParser:
    """解析 .txt, .md, .markdown 文件。"""

    name: str = "plain-text"
    version: str = "1"

    async def parse(self, data: bytes, *, filename: str, mime_type: str) -> ParsedDocument:
        """按 UTF-8 (支持带 BOM) 解码文本字节流。"""
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise UnparseableDocumentError(
                f"{filename} is not UTF-8 text: {error.reason} at byte {error.start}"
            ) from error
        return ParsedDocument(
            markdown=text,
            parser_name=self.name,
            parser_version=self.version,
        )
