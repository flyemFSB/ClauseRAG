"""基于 AnyDoc 的 Office 与 PDF 文档解析适配器。"""

from __future__ import annotations

import asyncio
from importlib.metadata import version as package_version

import anydoc

from domain.parsing import (
    OcrRequiredError,
    ParsedDocument,
    TransientParseError,
    UnparseableDocumentError,
    UnsupportedDocumentFormatError,
)
from domain.uploads import extension_of

_ANYDOC_VERSION = package_version("firecrawl-anydoc")

_UNPARSEABLE_ERRORS = (
    anydoc.UnsupportedError,
    anydoc.EncryptedError,
    anydoc.MalformedError,
    anydoc.MissingPartError,
    anydoc.ResourceLimitError,
)


class AnyDocParser:
    """解析 .pdf, .docx, .pptx, .xlsx 格式文件。"""

    name: str = "anydoc"
    version: str = _ANYDOC_VERSION

    async def parse(self, data: bytes, *, filename: str, mime_type: str) -> ParsedDocument:
        """在独立工作线程中将文档字节流转换为 Markdown。"""
        document_format = anydoc.format_from_extension(extension_of(filename))
        if document_format is None:
            raise UnsupportedDocumentFormatError(f"{self.name} 解析器无法读取文件: {filename}")
        try:
            markdown = await asyncio.to_thread(anydoc.to_markdown_bytes, data, document_format)
        except anydoc.NeedsOcrError as error:
            raise OcrRequiredError(
                f"{filename}: 共 {error.page_count} 页中包含扫描页 ({error.pages})，需要执行 OCR"
            ) from error
        except _UNPARSEABLE_ERRORS as error:
            raise UnparseableDocumentError(f"{filename}: {error}") from error
        except OSError as error:
            raise TransientParseError(f"{filename}: {error}") from error
        return ParsedDocument(
            markdown=markdown,
            parser_name=self.name,
            parser_version=self.version,
        )
