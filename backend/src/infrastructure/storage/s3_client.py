# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""S3 兼容客户端的构造与错误码读取：适配器、存储桶初始化与探针共用一份连接配置。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config

if TYPE_CHECKING:
    from botocore.exceptions import ClientError

# 业务写入按 3 次上限重试；探针要的是“当下可达与否”，自己传 1。
_DEFAULT_MAX_ATTEMPTS = 3


def s3_client(
    *,
    endpoint_url: str,
    region: str,
    access_key: str,
    secret_key: str,
    timeout_seconds: int,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
) -> Any:
    """构造一个 path-style 的 S3 客户端。"""
    client: Any = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(
            connect_timeout=timeout_seconds,
            read_timeout=timeout_seconds,
            retries={"max_attempts": max_attempts, "mode": "standard"},
            s3={"addressing_style": "path"},
        ),
    )
    return client


def error_code(error: ClientError) -> str:
    """读取 botocore 错误里的服务端错误码，读不到时返回空串。"""
    response: Any = error.response
    error_block: dict[str, Any] = response.get("Error", {})
    code = error_block.get("Code", "")
    return code if isinstance(code, str) else ""
