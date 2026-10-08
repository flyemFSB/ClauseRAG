# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""S3 兼容对象存储适配器：异步线程池封装分片上传与流式读取。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from boto3.s3.transfer import TransferConfig
from botocore.exceptions import BotoCoreError, ClientError

from application.shared.storage import ObjectStorageError, StoredObject
from infrastructure.storage.s3_client import error_code, s3_client

if TYPE_CHECKING:
    from typing import BinaryIO

SHA256_METADATA_KEY = "sha256"
_MISSING_OBJECT_CODES = frozenset({"404", "NoSuchKey", "NotFound"})
_MULTIPART_THRESHOLD_BYTES = 8 * 1024 * 1024
_MULTIPART_CHUNK_BYTES = 8 * 1024 * 1024
_UPLOAD_CONCURRENCY = 4
_DOWNLOAD_READ_BYTES = 1024 * 1024


class S3ObjectStorage:
    """基于 boto3 的 S3 兼容对象存储适配器。"""

    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        timeout_seconds: int,
    ) -> None:
        self._bucket = bucket
        self._client: Any = s3_client(
            endpoint_url=endpoint_url,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            timeout_seconds=timeout_seconds,
        )
        self._transfer_config: Any = TransferConfig(
            multipart_threshold=_MULTIPART_THRESHOLD_BYTES,
            multipart_chunksize=_MULTIPART_CHUNK_BYTES,
            max_concurrency=_UPLOAD_CONCURRENCY,
            use_threads=True,
        )

    async def put_stream(
        self,
        source: BinaryIO,
        *,
        key: str,
        content_type: str,
        sha256: str,
    ) -> None:
        """分片上传流对象并附加 SHA-256 元数据。"""

        def upload() -> None:
            source.seek(0)
            self._client.upload_fileobj(
                source,
                self._bucket,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "Metadata": {SHA256_METADATA_KEY: sha256},
                },
                Config=self._transfer_config,
            )

        try:
            await asyncio.to_thread(upload)
        except (ClientError, BotoCoreError, OSError) as error:
            raise ObjectStorageError(f"写入对象 {key} 失败: {_describe(error)}") from error

    async def head(self, key: str) -> StoredObject | None:
        """获取对象元数据及 SHA-256 校验和（不存在返回 None）。"""

        def read() -> StoredObject | None:
            try:
                response: Any = self._client.head_object(Bucket=self._bucket, Key=key)
            except ClientError as error:
                if error_code(error) in _MISSING_OBJECT_CODES:
                    return None
                raise
            metadata: dict[str, str] = response.get("Metadata") or {}
            size: Any = response.get("ContentLength", 0)
            return StoredObject(
                size_bytes=size if isinstance(size, int) else 0,
                sha256=metadata.get(SHA256_METADATA_KEY),
            )

        try:
            return await asyncio.to_thread(read)
        except (ClientError, BotoCoreError, OSError) as error:
            raise ObjectStorageError(f"获取对象元数据 {key} 失败: {_describe(error)}") from error

    async def delete(self, key: str) -> None:
        """删除指定对象，对象不存在时不报错。"""

        def remove() -> None:
            self._client.delete_object(Bucket=self._bucket, Key=key)

        try:
            await asyncio.to_thread(remove)
        except (ClientError, BotoCoreError, OSError) as error:
            raise ObjectStorageError(f"删除对象 {key} 失败: {_describe(error)}") from error

    async def get_bytes(self, key: str, *, max_bytes: int) -> bytes | None:
        """分块读取对象完整字节流，超出上限立即抛出异常。"""

        def read() -> bytes | None:
            try:
                response: Any = self._client.get_object(Bucket=self._bucket, Key=key)
            except ClientError as error:
                if error_code(error) in _MISSING_OBJECT_CODES:
                    return None
                raise
            body: Any = response["Body"]
            chunks: list[bytes] = []
            received = 0
            try:
                while True:
                    chunk: bytes = body.read(_DOWNLOAD_READ_BYTES)
                    if not chunk:
                        return b"".join(chunks)
                    received += len(chunk)
                    if received > max_bytes:
                        raise ObjectStorageError(
                            f"读取对象 {key} 失败: 对象大小超过上限 ({max_bytes} 字节)"
                        )
                    chunks.append(chunk)
            finally:
                body.close()

        try:
            return await asyncio.to_thread(read)
        except (ClientError, BotoCoreError, OSError) as error:
            raise ObjectStorageError(f"读取对象 {key} 失败: {_describe(error)}") from error


def _describe(error: Exception) -> str:
    if isinstance(error, ClientError):
        code = error_code(error)
        return code or type(error).__name__
    return type(error).__name__
