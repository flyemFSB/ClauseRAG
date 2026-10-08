"""生效配置看板的载荷渲染。

把 `Settings` 读到的值渲染成响应模型，供 `api.config` 的路由原样返回。放在 composition 而不是 api
层，是因为渲染要用 pydantic 的字段元数据（环境变量别名、注解里有没有 `SecretStr`），而 api 层的
依赖方向不允许它认识 `infrastructure`。

密钥项只回答"是否已配置"，绝不回传内容：屏幕上的一个值不值得换一次凭据泄漏，而"配没配"已经足够
回答运维真正要问的问题。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from api.config_schemas import ConfigEntry, ConfigResponse

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

    from infrastructure.config.settings import Settings


def _entry(name: str, field: FieldInfo, settings: Settings) -> ConfigEntry:
    """把一个配置字段渲染成一条可展示的记录。

    环境变量名就是字段名的大写形式：settings 不带前缀（没有 `env_prefix`），所以 `S3_BUCKET`
    这样的宿主环境变量会被这个进程直接读到——这正是前端要展示生效值而不是默认值的原因。
    """
    env = name.upper()
    value: Any = getattr(settings, name)
    if "SecretStr" in str(field.annotation):
        return ConfigEntry(env=env, value=None, secret=True, configured=value is not None)
    return ConfigEntry(
        env=env,
        value="" if value is None else str(value),
        secret=False,
        configured=value is not None,
    )


def render_config(settings: Settings) -> ConfigResponse:
    """按环境变量名排序，把本进程读到的配置渲染成响应。"""
    entries = (_entry(name, field, settings) for name, field in type(settings).model_fields.items())
    return ConfigResponse(entries=sorted(entries, key=lambda entry: entry.env))
