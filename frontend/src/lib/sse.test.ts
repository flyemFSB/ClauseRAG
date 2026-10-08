/**
 * Agent SSE 流式解析器单元测试
 *
 * 覆盖正常流解析、CRLF 与多行 data 组合、跨分块 UTF-8 字符边界、重复终态、缺少终态及异常截断等边界场景。
 */

import { afterEach, expect, test, vi } from "vite-plus/test";
import { ApiError } from "./api";
import { streamAgentRun, type AgentRunEvent } from "./sse";

const encoder = new TextEncoder();

afterEach(() => {
  vi.unstubAllGlobals();
});

/** 构造模拟分块流响应 */
function respondWith(parts: readonly Uint8Array[]): void {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const part of parts) {
        controller.enqueue(part);
      }
      controller.close();
    },
  });
  vi.stubGlobal("fetch", () => Promise.resolve(new Response(body, { status: 200 })));
}

function parts(text: string, splitAt?: number): readonly Uint8Array[] {
  const all = encoder.encode(text);
  return splitAt === undefined ? [all] : [all.slice(0, splitAt), all.slice(splitAt)];
}

async function collect(): Promise<AgentRunEvent[]> {
  const events: AgentRunEvent[] = [];
  for await (const event of streamAgentRun({
    conversationId: "c",
    content: "q",
    signal: new AbortController().signal,
  })) {
    events.push(event);
  }
  return events;
}

const STARTED = `event: run_started\ndata: {"schema_version":1,"run_id":"r","conversation_id":"c","user_message_id":"u","assistant_message_id":"a"}\n\n`;

const DELTA = `event: answer_delta\ndata: {"schema_version":1,"text":"`;

const DELTA_END = `"}\n\n`;

const COMPLETED = `event: run_completed\ndata: {"schema_version":1,"message_id":"a","answer":"你好","citations":[],"evidence_status":"sufficient","retrieval_rounds":1,"intent":"retrieval","finish_reason":"stop","removed_citation_ids":[]}\n\n`;

test("正常解析流并在终态事件后结束", async () => {
  respondWith(parts(STARTED + DELTA + "hi" + DELTA_END + COMPLETED));
  const events = await collect();
  expect(events.map((event) => event.event)).toEqual([
    "run_started",
    "answer_delta",
    "run_completed",
  ]);
  expect(events[1]).toMatchObject({ text: "hi" });
});

test("支持解析 CRLF 换行符与多行 data 载荷", async () => {
  // 验证包含 CRLF 与跨多行 data 字段的事件帧正确解析
  const crlf = `event: run_started\r\ndata: {"schema_version":1,"run_id":"r","conversation_id":"c","user_message_id":"u","assistant_message_id":"a"}\r\n\r\n`;
  const split = `event: answer_delta\r\ndata: {"schema_version":1,\r\ndata: "text":"hi"}\r\n\r\n`;
  const completed = COMPLETED.replace(/\n/g, "\r\n");
  respondWith(parts(crlf + split + completed));
  const events = await collect();
  expect(events.map((event) => event.event)).toEqual([
    "run_started",
    "answer_delta",
    "run_completed",
  ]);
  expect(events[1]).toMatchObject({ text: "hi" });
});

test("正确处理跨分块被切分的多字节 UTF-8 字符", async () => {
  const text = STARTED + DELTA + "你好" + DELTA_END + COMPLETED;
  // 在多字节 UTF-8 字符中间发生分块切分
  respondWith(parts(text, encoder.encode(STARTED + DELTA).length + 1));
  const events = await collect();
  expect(events[1]).toMatchObject({ text: "你好" });
  expect(events[2]).toMatchObject({ answer: "你好" });
});

test("拒绝出现第二个终态事件", async () => {
  respondWith(parts(STARTED + COMPLETED + COMPLETED));
  await expect(collect()).rejects.toThrow(/after its terminal event/);
});

test("拒绝未包含终态事件的流", async () => {
  respondWith(parts(STARTED + DELTA + "hi" + DELTA_END));
  await expect(collect()).rejects.toThrow(/without a terminal event/);
});

test("拒绝帧中间被截断的流", async () => {
  respondWith(parts(`${STARTED}${COMPLETED}event: answer_delta\ndata: {"schema_ver`));
  await expect(collect()).rejects.toThrow(/middle of a frame/);
});

test("拒绝未在契约中定义的未知事件名称", async () => {
  respondWith(parts(`event: mystery\ndata: {"schema_version":1}\n\n${COMPLETED}`));
  await expect(collect()).rejects.toThrow(/unknown event name/);
});

test("将流解析异常封装为 ApiError 抛出", async () => {
  respondWith(parts(STARTED + DELTA + "hi" + DELTA_END));
  await expect(collect()).rejects.toBeInstanceOf(ApiError);
});
