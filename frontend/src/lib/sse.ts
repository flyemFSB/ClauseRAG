/**
 * Agent 运行时流式响应 SSE 客户端
 *
 * 渐进式解析流式事件帧，严格校验契约版本号与终态事件（run_completed / run_failed / run_cancelled），
 * 支持调用方 AbortSignal 中止与跨分块行尾标准化。
 */

import { ApiError, malformed } from "./api";
import { asNullableString, asNumber, asRecord, asString, asStringArray } from "./contract";

export const SSE_SCHEMA_VERSION = 1;

export const SSE_EVENT_NAMES = [
  "run_started",
  "answer_delta",
  "citation",
  "run_completed",
  "run_failed",
  "run_cancelled",
] as const;

export type SseEventName = (typeof SSE_EVENT_NAMES)[number];

const TERMINAL_EVENT_NAMES: readonly SseEventName[] = [
  "run_completed",
  "run_failed",
  "run_cancelled",
];

export interface RunStarted {
  readonly event: "run_started";
  readonly runId: string;
  readonly conversationId: string;
  readonly userMessageId: string;
  readonly assistantMessageId: string;
}

export interface AnswerDelta {
  readonly event: "answer_delta";
  readonly text: string;
}

export interface CitationPayload {
  readonly citationId: string;
  readonly documentId: string;
  readonly documentVersionId: string;
  readonly documentName: string;
  readonly parentId: string;
  readonly childIds: readonly string[];
  readonly headingPath: readonly string[];
  readonly lineStart: number;
  readonly lineEnd: number;
  readonly quote: string;
}

export interface CitationEvent {
  readonly event: "citation";
  readonly citation: CitationPayload;
}

export interface RunCompleted {
  readonly event: "run_completed";
  readonly messageId: string;
  readonly answer: string;
  readonly citationIds: readonly string[];
  /** 证据门控状态：sufficient / degraded / insufficient，无召回时为 null */
  readonly evidenceStatus: string | null;
  readonly retrievalRounds: number;
  readonly intent: string | null;
  readonly finishReason: string | null;
  readonly removedCitationIds: readonly string[];
}

export interface RunFailed {
  readonly event: "run_failed";
  readonly messageId: string | null;
  readonly errorClass: string;
  readonly message: string;
}

export interface RunCancelled {
  readonly event: "run_cancelled";
  readonly messageId: string;
  readonly answer: string;
}

export type AgentRunEvent =
  | RunStarted
  | AnswerDelta
  | CitationEvent
  | RunCompleted
  | RunFailed
  | RunCancelled;

export function isTerminal(event: AgentRunEvent): boolean {
  return TERMINAL_EVENT_NAMES.includes(event.event);
}

export interface StreamRunRequest {
  /** 关联会话 ID */
  readonly conversationId: string;
  /** 提问内容 */
  readonly content: string;
  /** 调用方中止信号，触发中止将向服务端发送取消请求 */
  readonly signal: AbortSignal;
}

/** 发起 Agent 运行流式请求，按顺序产出解析后的 SSE 领域事件 */
export async function* streamAgentRun(request: StreamRunRequest): AsyncGenerator<AgentRunEvent> {
  const path = `/api/v1/conversations/${request.conversationId}/messages`;
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { accept: "text/event-stream", "content-type": "application/json" },
      body: JSON.stringify({ content: request.content }),
      signal: request.signal,
    });
  } catch (cause) {
    if (request.signal.aborted) {
      throw new ApiError("aborted", `${path} was cancelled`);
    }
    throw new ApiError("network", `${path} could not be reached: ${String(cause)}`);
  }
  if (!response.ok) {
    throw new ApiError("http", `${path} answered HTTP ${response.status}`, response.status);
  }
  if (response.body === null) {
    throw malformed(`${path} answered no stream body`);
  }

  let terminal = false;
  for await (const frame of readFrames(response.body)) {
    // 保证单流仅且必须产生一个终态事件，终态后的事件一律视为非法
    if (terminal) {
      throw malformed(`${path} carried an event after its terminal event`);
    }
    const event = parseEvent(frame);
    terminal = isTerminal(event);
    yield event;
  }
  if (!terminal) {
    throw malformed(`${path} ended without a terminal event`);
  }
}

/** 解析后的 SSE 基础帧结构 */
interface Frame {
  readonly name: string;
  readonly data: string;
}

async function* readFrames(body: ReadableStream<Uint8Array>): AsyncGenerator<Frame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      // 渐进式流式解码 UTF-8 字符块
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      buffer = normalizeLineEndings(buffer, done);
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const frame = parseFrame(raw);
        if (frame !== null) {
          yield frame;
        }
        boundary = buffer.indexOf("\n\n");
      }
      if (done) {
        // 流异常截断检测
        if (buffer.trim().length > 0) {
          throw malformed("the stream ended in the middle of a frame");
        }
        return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** 规范化各类换行符为 \n，以便根据连续两个换行识别 SSE 帧边界 */
function normalizeLineEndings(text: string, complete: boolean): string {
  const normalized = text.replace(/\r\n/g, "\n");
  return complete ? normalized.replace(/\r/g, "\n") : normalized.replace(/\r(?!$)/g, "\n");
}

/** 解析单帧文本中的 event 与 data 字段 */
function parseFrame(raw: string): Frame | null {
  let name = "";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      name = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      data.push(line.slice("data:".length).trim());
    }
  }
  if (name.length === 0 || data.length === 0) {
    return null;
  }
  return { name, data: data.join("\n") };
}

function parseEvent(frame: Frame): AgentRunEvent {
  if (!SSE_EVENT_NAMES.includes(frame.name as SseEventName)) {
    throw malformed(`the stream carried an unknown event name ${frame.name}`);
  }
  let payload: unknown;
  try {
    payload = JSON.parse(frame.data);
  } catch (cause) {
    throw malformed(`event ${frame.name} carried data that is not JSON: ${String(cause)}`);
  }
  const record = asRecord(payload, `event ${frame.name}`);
  if (record["schema_version"] !== SSE_SCHEMA_VERSION) {
    throw malformed(
      `event ${frame.name} carries schema_version ${String(record["schema_version"])}, and this client speaks ${SSE_SCHEMA_VERSION}`,
    );
  }
  switch (frame.name as SseEventName) {
    case "run_started":
      return {
        event: "run_started",
        runId: asString(record, "run_id"),
        conversationId: asString(record, "conversation_id"),
        userMessageId: asString(record, "user_message_id"),
        assistantMessageId: asString(record, "assistant_message_id"),
      };
    case "answer_delta":
      return { event: "answer_delta", text: asString(record, "text") };
    case "citation":
      return { event: "citation", citation: parseCitation(record) };
    case "run_completed":
      return {
        event: "run_completed",
        messageId: asString(record, "message_id"),
        answer: asString(record, "answer"),
        citationIds: asStringArray(record, "citations"),
        evidenceStatus: asNullableString(record, "evidence_status"),
        retrievalRounds: asNumber(record, "retrieval_rounds"),
        intent: asNullableString(record, "intent"),
        finishReason: asNullableString(record, "finish_reason"),
        removedCitationIds: asStringArray(record, "removed_citation_ids"),
      };
    case "run_failed":
      return {
        event: "run_failed",
        messageId: asNullableString(record, "message_id"),
        errorClass: asString(record, "error_class"),
        message: asString(record, "message"),
      };
    case "run_cancelled":
      return {
        event: "run_cancelled",
        messageId: asString(record, "message_id"),
        answer: asString(record, "answer"),
      };
  }
}

function parseCitation(record: Record<string, unknown>): CitationPayload {
  return {
    citationId: asString(record, "citation_id"),
    documentId: asString(record, "document_id"),
    documentVersionId: asString(record, "document_version_id"),
    documentName: asString(record, "document_name"),
    parentId: asString(record, "parent_id"),
    childIds: asStringArray(record, "child_ids"),
    headingPath: asStringArray(record, "heading_path"),
    lineStart: asNumber(record, "line_start"),
    lineEnd: asNumber(record, "line_end"),
    quote: asString(record, "quote"),
  };
}
