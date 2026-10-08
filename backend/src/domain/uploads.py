"""文件上传规范、MIME 类型推导与原始存储键规则。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

SUPPORTED_EXTENSIONS: Mapping[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def extension_of(filename: str) -> str:
    """提取包含点的小写扩展名，无扩展名时返回空字符串"""
    _, dot, extension = filename.rpartition(".")
    if not dot:
        return ""
    return f".{extension.lower()}"


def mime_type_for_filename(filename: str) -> str | None:
    """根据文件名推导标准 MIME 类型，不受支持时返回 None"""
    return SUPPORTED_EXTENSIONS.get(extension_of(filename))


def original_object_key(version_id: UUID, filename: str) -> str:
    """生成原始上传文件在对象存储中的持久化键"""
    return f"raw/{version_id}/original{extension_of(filename)}"
