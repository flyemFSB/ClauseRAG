"""S3 兼容对象存储客户端装配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrastructure.storage.object_storage import S3ObjectStorage

if TYPE_CHECKING:
    from infrastructure.config.settings import Settings


def open_object_storage(settings: Settings) -> S3ObjectStorage:
    """初始化并配置 S3 兼容对象存储客户端实例。"""
    return S3ObjectStorage(
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        bucket=settings.s3_bucket,
        timeout_seconds=settings.storage_timeout_seconds,
    )
