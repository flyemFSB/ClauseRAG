"""分块领域数据模型、接口协议与实体定义。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID


class TokenCounter(Protocol):
    """分块 Token 计数器协议"""

    def count(self, text: str) -> int:
        """计算文本所占用的 Token 数量"""
        ...


class BlockType(StrEnum):
    """Markdown 块类型枚举"""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    CODE = "code"
    IMAGE = "image"


class ChunkKind(StrEnum):
    """分块层级级别"""

    PARENT = "parent"
    CHILD = "child"


@dataclass(frozen=True, slots=True)
class ParentChunk:
    """父块（结构化上下文，供智能体理解和组装提示词）"""

    parent_id: UUID
    document_version_id: UUID
    heading_path: tuple[str, ...]
    ordinal: int
    content: str
    token_count: int


@dataclass(frozen=True, slots=True)
class ChildChunk:
    """子块（检索与引用单元，供向量化、召回与引用锚定）"""

    child_id: UUID
    parent_id: UUID
    document_version_id: UUID
    heading_path: tuple[str, ...]
    block_type: BlockType
    ordinal: int
    line_start: int
    line_end: int
    content: str
    token_count: int


@dataclass(frozen=True, slots=True)
class ChunkPlan:
    """分块执行规划产物（包含所有父块、子块及警告信息）"""

    document_version_id: UUID
    parents: tuple[ParentChunk, ...]
    children: tuple[ChildChunk, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChunkArtifact:
    """持久化分块产物元数据"""

    document_version_id: UUID
    object_key: str
    checksum: str
    size_bytes: int
    parent_count: int
    child_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChunkTarget:
    """分块输入目标（解析产物 Markdown 存储键及校验元数据）"""

    document_version_id: UUID
    markdown_object_key: str
    markdown_checksum: str
    markdown_size_bytes: int


@dataclass(frozen=True, slots=True)
class ChunkClaim:
    """Worker 认领的分块任务"""

    job_id: UUID
    target: ChunkTarget
    attempt: int
