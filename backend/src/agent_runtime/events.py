"""SSE 流式协议事件模型与数据帧定义。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from domain.conversation import CitationRecord
    from domain.retrieval import EvidenceStatus

# SSE 消息契约版本
SSE_SCHEMA_VERSION = 1


class EventName(StrEnum):
    """SSE 事件类型定义。"""

    RUN_STARTED = "run_started"
    ANSWER_DELTA = "answer_delta"
    CITATION = "citation"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


TERMINAL_EVENTS = frozenset(
    {EventName.RUN_COMPLETED, EventName.RUN_FAILED, EventName.RUN_CANCELLED}
)


@dataclass(frozen=True, slots=True)
class AnswerDelta:
    """流式模型回答增量文本。"""

    text: str


@dataclass(frozen=True, slots=True)
class ServerSentEvent:
    """SSE 单帧数据载体。"""

    event: EventName
    data: Mapping[str, object]

    @property
    def terminal(self) -> bool:
        """判断当前事件是否为流终止事件。"""
        return self.event in TERMINAL_EVENTS

    def encode(self) -> bytes:
        """编码为 UTF-8 格式的 SSE 协议字节流。"""
        payload = json.dumps(dict(self.data), ensure_ascii=False)
        return f"event: {self.event.value}\ndata: {payload}\n\n".encode()


def run_started(
    *,
    run_id: str,
    conversation_id: UUID,
    user_message_id: UUID,
    assistant_message_id: UUID,
) -> ServerSentEvent:
    """构建运行开始事件帧。"""
    return ServerSentEvent(
        event=EventName.RUN_STARTED,
        data={
            "schema_version": SSE_SCHEMA_VERSION,
            "run_id": run_id,
            "conversation_id": str(conversation_id),
            "user_message_id": str(user_message_id),
            "assistant_message_id": str(assistant_message_id),
        },
    )


def answer_delta(text: str) -> ServerSentEvent:
    """构建文本增量事件帧。"""
    return ServerSentEvent(
        event=EventName.ANSWER_DELTA,
        data={"schema_version": SSE_SCHEMA_VERSION, "text": text},
    )


def citation(record: CitationRecord) -> ServerSentEvent:
    """构建引用溯源事件帧。"""
    return ServerSentEvent(
        event=EventName.CITATION,
        data={
            "schema_version": SSE_SCHEMA_VERSION,
            "citation_id": record.citation_id,
            "document_id": str(record.document_id),
            "document_version_id": str(record.document_version_id),
            "document_name": record.document_name,
            "parent_id": str(record.parent_id),
            "child_ids": [str(record.child_id)],
            "heading_path": list(record.heading_path),
            "line_start": record.line_start,
            "line_end": record.line_end,
            "quote": record.quote,
        },
    )


def run_completed(
    *,
    message_id: UUID,
    answer: str,
    citations: Sequence[CitationRecord],
    evidence_status: EvidenceStatus,
    retrieval_rounds: int,
    intent: str | None,
    finish_reason: str | None,
    removed_citation_ids: Sequence[str],
) -> ServerSentEvent:
    """构建运行完成事件帧。"""
    return ServerSentEvent(
        event=EventName.RUN_COMPLETED,
        data={
            "schema_version": SSE_SCHEMA_VERSION,
            "message_id": str(message_id),
            "answer": answer,
            "citations": [record.citation_id for record in citations],
            "evidence_status": evidence_status.value,
            "retrieval_rounds": retrieval_rounds,
            "intent": intent,
            "finish_reason": finish_reason,
            "removed_citation_ids": list(removed_citation_ids),
        },
    )


def run_failed(*, message_id: UUID | None, error_class: str, message: str) -> ServerSentEvent:
    """构建运行失败事件帧。"""
    return ServerSentEvent(
        event=EventName.RUN_FAILED,
        data={
            "schema_version": SSE_SCHEMA_VERSION,
            "message_id": str(message_id) if message_id is not None else None,
            "error_class": error_class,
            "message": message,
        },
    )


def run_cancelled(*, message_id: UUID, answer: str) -> ServerSentEvent:
    """构建运行取消事件帧。"""
    return ServerSentEvent(
        event=EventName.RUN_CANCELLED,
        data={
            "schema_version": SSE_SCHEMA_VERSION,
            "message_id": str(message_id),
            "answer": answer,
        },
    )
