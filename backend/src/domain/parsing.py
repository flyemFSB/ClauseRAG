"""文档解析路由规则、产物与阶段异常定义。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from domain.knowledge import (
    MANUAL_RETRY_STATE,
    DocumentVersionStatus,
    IngestionJobStatus,
    StageFailureState,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from domain.knowledge import IngestionJob


class ParseRoute(StrEnum):
    """文档解析器类型路由"""

    ANYDOC = "anydoc"
    HTML = "html-to-markdown"
    PLAIN_TEXT = "plain-text"
    OCR = "paddleocr-vl"


_EXTENSION_ROUTES: Mapping[str, ParseRoute] = {
    ".pdf": ParseRoute.ANYDOC,
    ".docx": ParseRoute.ANYDOC,
    ".pptx": ParseRoute.ANYDOC,
    ".xlsx": ParseRoute.ANYDOC,
    ".html": ParseRoute.HTML,
    ".htm": ParseRoute.HTML,
    ".txt": ParseRoute.PLAIN_TEXT,
    ".md": ParseRoute.PLAIN_TEXT,
    ".markdown": ParseRoute.PLAIN_TEXT,
    ".png": ParseRoute.OCR,
    ".jpg": ParseRoute.OCR,
    ".jpeg": ParseRoute.OCR,
    ".webp": ParseRoute.OCR,
    ".bmp": ParseRoute.OCR,
    ".tif": ParseRoute.OCR,
    ".tiff": ParseRoute.OCR,
}

OUT_OF_SCOPE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".doc",
        ".docm",
        ".ppt",
        ".pptm",
        ".xls",
        ".xlsm",
        ".xlsb",
        ".odt",
        ".ods",
        ".odp",
        ".rtf",
        ".epub",
        ".csv",
    }
)


def parse_route_for_extension(extension: str) -> ParseRoute:
    """根据文件扩展名解析对应的解析器路由"""
    route = _EXTENSION_ROUTES.get(extension)
    if route is not None:
        return route
    if extension in OUT_OF_SCOPE_EXTENSIONS:
        raise UnsupportedDocumentFormatError(f"当前版本暂不支持解析 {extension} 格式文件")
    named = extension or "无扩展名文件"
    raise UnsupportedDocumentFormatError(f"未找到支持 {named} 的解析器")


def parsed_object_key(version_id: UUID, job_id: UUID, attempt: int) -> str:
    """生成标准化解析产物 Markdown 在对象存储中的键"""
    return f"parsed/{version_id}/{job_id}/attempt-{attempt}/document.md"


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """解析器原始输出对象（未标准化）"""

    markdown: str
    parser_name: str
    parser_version: str
    page_count: int | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParseArtifact:
    """持久化解析产物元数据"""

    document_version_id: UUID
    parser_name: str
    parser_version: str
    markdown_object_key: str
    checksum: str
    size_bytes: int
    page_count: int | None
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParseTarget:
    """解析目标参数（源存储对象及 MIME 类型）"""

    document_version_id: UUID
    source_object_key: str
    mime_type: str


@dataclass(frozen=True, slots=True)
class ParseClaim:
    """Worker 认领的解析任务"""

    job_id: UUID
    target: ParseTarget
    attempt: int


class DocumentParseError(Exception):
    """文档解析基础异常"""


class UnparseableDocumentError(DocumentParseError):
    """文档内容损坏或加密无法解析（需人工介入）"""


class UnsupportedDocumentFormatError(UnparseableDocumentError):
    """不支持的文件格式"""


class TransientParseError(DocumentParseError):
    """解析服务瞬时网络或超时错误（可自动重试）"""


class OcrProviderError(DocumentParseError):
    """OCR 外部模型服务拒绝错误"""


class OcrRequiredError(DocumentParseError):
    """文档为扫描件或纯图像，需要转入 OCR 流水线处理"""


PARSE_FAILED_STATE: StageFailureState = StageFailureState(
    version_status=DocumentVersionStatus.PARSE_FAILED,
    job_status=IngestionJobStatus.FAILED,
)


def failure_state_for(error: DocumentParseError) -> StageFailureState:
    """根据解析异常类型计算失败状态组合"""
    if isinstance(error, UnparseableDocumentError):
        return MANUAL_RETRY_STATE
    return PARSE_FAILED_STATE


RETRYABLE_PARSE_STATUSES: frozenset[DocumentVersionStatus] = frozenset(
    {DocumentVersionStatus.MANUAL_RETRY_REQUIRED, DocumentVersionStatus.PARSE_FAILED}
)

ABANDONED_ATTEMPT_CLASS = "AbandonedAttempt"
ABANDONED_ATTEMPT_MESSAGE = "任务尝试已超出超时时限，已被新的解析修订版本取代"


class ParseRetryOutcome(StrEnum):
    """重试请求处理结果"""

    CREATED = "created"
    """已创建新的解析修订版本并排队"""

    STALE = "stale"
    """原任务执行超时，已被放弃并新建修订版本"""

    QUEUED = "queued"
    """已有排队中的任务，直接复用"""

    RUNNING = "running"
    """当前正在执行中，无需重复排队"""

    NOT_RETRYABLE = "not_retryable"
    """当前状态不允许重试"""


@dataclass(frozen=True, slots=True)
class ParseRetry:
    """解析重试操作响应结果"""

    outcome: ParseRetryOutcome
    version_status: DocumentVersionStatus
    job: IngestionJob


class RetryNotAllowedError(Exception):
    """当前状态禁止手动重试异常"""

    def __init__(self, version_id: UUID, status: DocumentVersionStatus) -> None:
        retryable = ", ".join(sorted(state.value for state in RETRYABLE_PARSE_STATUSES))
        super().__init__(
            f"文档版本 {version_id} 当前状态为 {status.value}，不支持手动重试；"
            f"仅允许在以下状态下重试: {retryable}"
        )
        self.version_id = version_id
        self.status = status
