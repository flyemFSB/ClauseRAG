"""S3 兼容对象存储接口协议与元数据值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from typing import BinaryIO


@dataclass(frozen=True, slots=True)
class StoredObject:
    """对象存储元数据"""

    size_bytes: int
    sha256: str | None


class ObjectStorageError(RuntimeError):
    """对象存储操作异常"""


class ObjectStorage(Protocol):
    """不可变对象存储接口协议"""

    async def put_stream(
        self,
        source: BinaryIO,
        *,
        key: str,
        content_type: str,
        sha256: str,
    ) -> None:
        """流式上传文件对象至指定键"""
        ...

    async def head(self, key: str) -> StoredObject | None:
        """获取对象元数据，不存在时返回 None"""
        ...

    async def delete(self, key: str) -> None:
        """删除指定键的对象（若不存在则视为空操作）"""
        ...

    async def get_bytes(self, key: str, *, max_bytes: int) -> bytes | None:
        """读取对象的完整字节内容，超过上限时抛出 ObjectStorageError"""
        ...
