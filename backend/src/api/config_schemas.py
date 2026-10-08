"""HTTP 响应模型：本进程生效配置看板。"""

from __future__ import annotations

from pydantic import BaseModel


class ConfigEntry(BaseModel):
    """一项生效配置。"""

    #: 环境变量名（覆盖它的那一项，字段名即配置契约）
    env: str
    #: 本进程实际生效的值；密钥项不回传内容，这里是 None
    value: str | None
    #: 是否为密钥类型
    secret: bool
    #: 是否已给出值（密钥项用它表达"配没配"，而不是把值说出来）
    configured: bool


class ConfigResponse(BaseModel):
    """本进程读取到的全部生效配置。"""

    entries: list[ConfigEntry]
