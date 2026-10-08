"""storage-init 命令：初始化对象存储存储桶。"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from infrastructure.storage.s3_bucket import BucketInitializationError

if TYPE_CHECKING:
    from composition.cli.runtime import StorageRuntime


def storage_init(runtime: StorageRuntime) -> int:
    """幂等创建对象存储业务存储桶。"""
    try:
        created = runtime.bucket_initializer.ensure_bucket()
    except BucketInitializationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    state = "created" if created else "already present"
    print(f"bucket {runtime.settings.s3_bucket} {state}")
    return 0
