# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""S3 存储桶幂等初始化组件。"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from infrastructure.storage.s3_client import error_code, s3_client

_MISSING_BUCKET_CODES = frozenset({"404", "NotFound", "NoSuchBucket"})


class BucketInitializationError(RuntimeError):
    """存储桶初始化异常。"""


class S3BucketInitializer:
    """S3 存储桶幂等初始化器。"""

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

    def ensure_bucket(self) -> bool:
        """确保存储桶存在，若新建返回 True，已存在返回 False。"""
        try:
            if self._exists():
                return False
            self._client.create_bucket(Bucket=self._bucket)
        except ClientError as error:
            if error_code(error) == "BucketAlreadyOwnedByYou":
                return False
            raise BucketInitializationError(
                f"bucket {self._bucket}: {error_code(error) or type(error).__name__}"
            ) from error
        return True

    def _exists(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as error:
            if error_code(error) in _MISSING_BUCKET_CODES:
                return False
            raise
        return True
