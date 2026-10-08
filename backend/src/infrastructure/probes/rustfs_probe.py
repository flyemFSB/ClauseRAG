# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""RustFS (S3 兼容对象存储) 就绪探针。"""

from __future__ import annotations

import asyncio
from typing import Any

from domain.dependency import Dependency
from infrastructure.storage.s3_client import s3_client


class RustFsProbe:
    """RustFS 连通性探针：调用 list_buckets 验证签名与服务端连通性。"""

    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str,
        timeout_seconds: int,
    ) -> None:
        self.dependency = Dependency.RUSTFS
        self._client: Any = s3_client(
            endpoint_url=endpoint_url,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            timeout_seconds=timeout_seconds,
            # 探针只回答"此刻是否可达"，因此不重试。
            max_attempts=1,
        )

    async def probe(self) -> None:
        """执行探活检查，不可达或鉴权失败则抛出异常。"""
        await asyncio.to_thread(self._client.list_buckets)
