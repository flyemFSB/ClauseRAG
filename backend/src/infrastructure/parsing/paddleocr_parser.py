"""基于 PaddleOCR-VL 异步 API 的图像与扫描件 OCR 解析适配器。"""

from __future__ import annotations

import asyncio
import time

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain.parsing import (
    DocumentParseError,
    OcrProviderError,
    ParsedDocument,
    TransientParseError,
    UnparseableDocumentError,
)

_PROVIDER = "paddleocr-vl"
_JOBS_PATH = "/api/v2/ocr/jobs"

_UNREADABLE_CODES = frozenset({10004, 11003})
_TRANSIENT_CODES = frozenset({429, 500, 503, 504, 10010, 12002})
_OPERATIONAL_CODES = frozenset({401, 403, 10007, 10008, 11001, 12001})
_OPERATIONAL_STATUS_CODES = frozenset({400, 401, 403, 404})

_PAYLOAD_CONFIG = ConfigDict(extra="ignore", frozen=True)


class _ResultUrl(BaseModel):
    model_config = _PAYLOAD_CONFIG
    json_url: str | None = Field(default=None, alias="jsonUrl")


class _JobData(BaseModel):
    model_config = _PAYLOAD_CONFIG
    job_id: str | None = Field(default=None, alias="jobId")
    state: str | None = None
    error_msg: str | None = Field(default=None, alias="errorMsg")
    result_url: _ResultUrl | None = Field(default=None, alias="resultUrl")


class _JobEnvelope(BaseModel):
    model_config = _PAYLOAD_CONFIG
    code: int
    msg: str = ""
    data: _JobData | None = None


class _PageMarkdown(BaseModel):
    model_config = _PAYLOAD_CONFIG
    text: str | None = None


class _Page(BaseModel):
    model_config = _PAYLOAD_CONFIG
    markdown: _PageMarkdown | None = None


class _ResultDocument(BaseModel):
    model_config = _PAYLOAD_CONFIG
    layout_parsing_results: list[_Page] = Field(alias="layoutParsingResults")


class _ResultEnvelope(BaseModel):
    model_config = _PAYLOAD_CONFIG
    error_code: int = Field(alias="errorCode")
    error_msg: str = Field(default="", alias="errorMsg")
    result: _ResultDocument | None = None


def _provider_failure(
    code: int,
    message: str,
    *,
    what: str,
    status_code: int | None = None,
) -> DocumentParseError:
    detail = f"{_PROVIDER} {what} 失败: code={code} message={message!r}"
    if status_code is not None:
        detail = f"{detail} http_status={status_code}"
    if code in _TRANSIENT_CODES or (
        status_code is not None and (status_code >= 500 or status_code == 429)
    ):
        return TransientParseError(detail)
    if code in _UNREADABLE_CODES:
        return UnparseableDocumentError(detail)
    return OcrProviderError(detail)


class PaddleOcrParser:
    """调用 PaddleOCR-VL 异步接口解析图像与扫描件。"""

    name: str = _PROVIDER
    version: str

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        request_timeout_seconds: int,
        poll_interval_seconds: float,
        poll_timeout_seconds: int,
    ) -> None:
        self.version = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._request_timeout = request_timeout_seconds
        self._poll_interval = poll_interval_seconds
        self._poll_timeout = poll_timeout_seconds

    async def parse(self, data: bytes, *, filename: str, mime_type: str) -> ParsedDocument:
        """提交 OCR 任务、轮询结果并按页组装 Markdown。"""
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._request_timeout),
        ) as client:
            job_id = await self._submit(client, data, filename, mime_type)
            result_url = await self._await_result(client, job_id)
            result = await self._fetch_result(client, result_url)
        return self._to_document(result, filename)

    async def _submit(
        self,
        client: httpx.AsyncClient,
        data: bytes,
        filename: str,
        mime_type: str,
    ) -> str:
        try:
            response = await client.post(
                _JOBS_PATH,
                files={"file": (filename, data, mime_type)},
                data={"model": self._model},
                headers=self._authorization(),
            )
        except httpx.HTTPError as error:
            raise TransientParseError(f"{self.name} OCR 服务不可达: {error}") from error
        envelope = _read_job_envelope(response)
        job_id = envelope.data.job_id if envelope.data is not None else None
        if envelope.code == 0 and job_id:
            return job_id
        raise _provider_failure(
            envelope.code,
            envelope.msg,
            what="提交任务",
            status_code=response.status_code,
        )

    async def _await_result(self, client: httpx.AsyncClient, job_id: str) -> str:
        deadline = time.monotonic() + self._poll_timeout
        state = "unknown"
        while True:
            try:
                envelope = await self._query(client, job_id)
            except TransientParseError:
                state = "unreadable"
            else:
                if envelope.code != 0:
                    raise _provider_failure(
                        envelope.code,
                        envelope.msg,
                        what=f"查询任务 {job_id} 状态",
                    )
                job = envelope.data
                if job is not None and job.state == "done":
                    url = job.result_url.json_url if job.result_url is not None else None
                    if not url:
                        raise TransientParseError(
                            f"{self.name} 任务 {job_id} 执行完成但未返回结果 URL"
                        )
                    return url
                if job is not None and job.state == "failed":
                    raise TransientParseError(
                        f"{self.name} 任务 {job_id} 服务端失败: {job.error_msg or '未返回失败原因'}"
                    )
                state = job.state if job is not None and job.state else state
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransientParseError(
                    f"{self.name} 任务 {job_id} 轮询超时 "
                    f"({self._poll_timeout} 秒)，当前状态: {state}"
                )
            await asyncio.sleep(min(self._poll_interval, remaining))

    async def _query(self, client: httpx.AsyncClient, job_id: str) -> _JobEnvelope:
        try:
            response = await client.get(f"{_JOBS_PATH}/{job_id}", headers=self._authorization())
        except httpx.HTTPError as error:
            raise TransientParseError(f"{self.name} 状态查询失败: {error}") from error
        return _read_job_envelope(response)

    async def _fetch_result(self, client: httpx.AsyncClient, result_url: str) -> list[_Page]:
        try:
            response = await client.get(result_url)
        except httpx.HTTPError as error:
            raise TransientParseError(f"{self.name} 结果下载失败: {error}") from error
        return _read_result_pages(response)

    def _to_document(self, result: list[_Page], filename: str) -> ParsedDocument:
        pages: list[str] = []
        warnings: list[str] = []
        for page_number, page in enumerate(result, start=1):
            text = page.markdown.text if page.markdown is not None else None
            if text is None or not text.strip():
                warnings.append(f"{filename} 第 {page_number} 页未识别到任何文本")
                continue
            pages.append(text)
        return ParsedDocument(
            markdown="\n\n".join(pages),
            parser_name=self.name,
            parser_version=self.version,
            page_count=len(result) or None,
            warnings=tuple(warnings),
        )

    def _authorization(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}


def _read_job_envelope(response: httpx.Response) -> _JobEnvelope:
    try:
        return _JobEnvelope.model_validate_json(response.text)
    except ValidationError as error:
        raise TransientParseError(
            f"PaddleOCR-VL 响应解析失败 (状态码 {response.status_code}): "
            f"{error.error_count()} 处校验错误"
        ) from error


def _read_result_pages(response: httpx.Response) -> list[_Page]:
    """解析 PaddleOCR-VL 响应体。

    长文档由服务端以换行分隔的多个 JSON 封包流式返回，每行承载若干页的 layoutParsingResults。
    按行独立反序列化并合并页面，避免因跨行包含额外数据导致整体验证失败。
    """
    payloads = [line for line in response.text.splitlines() if line.strip()]
    if not payloads:
        raise TransientParseError(f"{_PROVIDER} 响应为空 (状态码 {response.status_code})")
    pages: list[_Page] = []
    for index, payload in enumerate(payloads):
        try:
            envelope = _ResultEnvelope.model_validate_json(payload)
        except ValidationError as error:
            raise TransientParseError(
                f"{_PROVIDER} 结果封包第 {index + 1}/{len(payloads)} 行解析失败: "
                f"{error.error_count()} 处校验错误"
            ) from error
        if envelope.error_code != 0:
            raise _provider_failure(
                envelope.error_code,
                envelope.error_msg,
                what="结果解析",
                status_code=response.status_code,
            )
        if envelope.result is not None:
            pages.extend(envelope.result.layout_parsing_results)
    if not pages:
        raise TransientParseError(f"{_PROVIDER} 返回的结果中未包含任何页面")
    return pages
