"""SQLAlchemy 声明式基类与公共数据库字段类型及常量。"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from enum import StrEnum


class DomainUuid(sa.types.TypeDecorator[uuid.UUID]):
    """确保返回标准 uuid.UUID 实例的 UUID 类型包装器（兼容 msgpack 序列化）。"""

    impl = sa.Uuid
    cache_ok = True

    def process_result_value(
        self,
        value: uuid.UUID | None,
        dialect: sa.Dialect,
    ) -> uuid.UUID | None:
        """规范化提取的值为标准 uuid.UUID。"""
        del dialect
        if value is None or type(value) is uuid.UUID:
            return value
        return uuid.UUID(str(value))


ENUM_VALUE_LENGTH = 32
SHORT_TEXT_LENGTH = 100
NAME_LENGTH = 200
TITLE_LENGTH = 500
MIME_TYPE_LENGTH = 255
CHECKSUM_LENGTH = 64


def check_constraint_values(enum_type: type[StrEnum]) -> str:
    """将枚举类型的值列表渲染为 SQL CHECK 约束字符串。"""
    return ", ".join(f"'{member.value}'" for member in enum_type)


class Base(DeclarativeBase):
    """业务数据表 SQLAlchemy 声明式映射基类。"""
