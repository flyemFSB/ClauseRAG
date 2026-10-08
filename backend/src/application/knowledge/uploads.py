"""上传文件校验、流式度量与异常定义。"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import BinaryIO

UPLOAD_READ_BYTES = 1024 * 1024


class UnsupportedFileTypeError(Exception):
    """不支持的文件格式异常"""

    def __init__(self, filename: str) -> None:
        super().__init__(f"{filename} is not an accepted document type")
        self.filename = filename


class UploadTooLargeError(Exception):
    """文件大小超出配置上限异常"""

    def __init__(self, max_upload_bytes: int) -> None:
        super().__init__(f"the upload exceeds {max_upload_bytes} bytes")
        self.max_upload_bytes = max_upload_bytes


class EmptyUploadError(Exception):
    """文件内容为空异常"""

    def __init__(self, filename: str) -> None:
        super().__init__(f"{filename} is empty")
        self.filename = filename


class UploadVerificationError(Exception):
    """对象存储中写入的文件校验失败异常"""

    def __init__(self, object_key: str) -> None:
        super().__init__(f"storage does not match the uploaded bytes at {object_key}")
        self.object_key = object_key


def measure_upload(source: BinaryIO, max_upload_bytes: int) -> tuple[str, int]:
    """分块流式读取文件流，计算 SHA-256 哈希与字节总大小（超限立即中断）"""
    digest = hashlib.sha256()
    size_bytes = 0
    source.seek(0)
    while True:
        chunk = source.read(min(UPLOAD_READ_BYTES, max_upload_bytes - size_bytes + 1))
        if not chunk:
            break
        digest.update(chunk)
        size_bytes += len(chunk)
        if size_bytes > max_upload_bytes:
            raise UploadTooLargeError(max_upload_bytes)
    return digest.hexdigest(), size_bytes
