/**
 * Agent 生成运行竞态单元测试。
 *
 * 验证代际隔离下旧流数据不覆盖新会话状态、中止请求的准确隔离等并发行为。
 */

import { afterEach, expect, test, vi } from "vite-plus/test";
import { createGeneration } from "../../lib/generation";
import { INITIAL_RUN_STATE, startAgentRun, type RunState } from "./run";

const encoder = new TextEncoder();

/** 每次 `fetch` 得到的响应体，交由测试逐帧推进。 */
const bodies: ReadableStreamDefaultController<Uint8Array>[] = [];
/** 每次 `fetch` 拿到的 signal，用来证明取消落在哪一代上。 */
const signals: (AbortSignal | null | undefined)[] = [];

/**
 * 一个只答流、但不自己推进的 `fetch`。
 *
 * 它同时把 abort 接到响应体上：真实的 fetch 在连接被中止时会让 body 出错，而测试必须能等到
 * `driver.done`，所以这里如实照做。
 */
function stubStreamingFetch(): void {
  bodies.length = 0;
  signals.length = 0;
  vi.stubGlobal("fetch", (_path: string, init: RequestInit) => {
    let body!: ReadableStreamDefaultController<Uint8Array>;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        body = controller;
      },
    });
    const signal = init.signal;
    if (signal !== null && signal !== undefined) {
      signal.addEventListener("abort", () => {
        body.error(new DOMException("The operation was aborted.", "AbortError"));
      });
    }
    bodies.push(body);
    signals.push(signal);
    return Promise.resolve(new Response(stream, { status: 200 }));
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  bodies.length = 0;
  signals.length = 0;
});

/** 把一帧推进第 `index` 个响应体。 */
function push(index: number, text: string): void {
  const body = bodies[index];
  if (body === undefined) {
    throw new Error(`no stream at ${String(index)}`);
  }
  body.enqueue(encoder.encode(text));
}

async function opened(count: number): Promise<void> {
  await vi.waitFor(() => {
    expect(bodies).toHaveLength(count);
  });
}

const STARTED = `event: run_started\ndata: ${JSON.stringify({
  schema_version: 1,
  run_id: "r",
  conversation_id: "c",
  user_message_id: "u",
  assistant_message_id: "a",
})}\n\n`;

const delta = (text: string): string =>
  `event: answer_delta\ndata: ${JSON.stringify({ schema_version: 1, text })}\n\n`;

const completed = (answer: string): string =>
  `event: run_completed\ndata: ${JSON.stringify({
    schema_version: 1,
    message_id: "a",
    answer,
    citations: [],
    evidence_status: "sufficient",
    retrieval_rounds: 1,
    intent: "retrieval",
    finish_reason: "stop",
    removed_citation_ids: [],
  })}\n\n`;

/** 一个把状态累积在本地变量里的提交口 —— 与同一 identity 下最危险的那种情形等价。 */
function collector(): {
  readonly commit: (update: (previous: RunState) => RunState) => void;
  readonly read: () => RunState;
} {
  let state: RunState = INITIAL_RUN_STATE;
  return {
    commit: (update) => {
      state = update(state);
    },
    read: () => state,
  };
}

const settled = async (): Promise<void> => undefined;

test("被取代的那一代晚到的字节写不进当前 run", async () => {
  stubStreamingFetch();
  const generation = createGeneration();
  const state = collector();

  const first = startAgentRun(generation, {
    conversationId: "c",
    question: "第一个问题",
    commit: state.commit,
    onSettled: settled,
  });
  await opened(1);
  push(0, STARTED);
  await vi.waitFor(() => {
    expect(state.read().userMessageId).toBe("u");
  });

  // 新一代接管：第一个 run 就此失去写状态的资格，它的 controller 也不再是“停止”指向的那一个。
  const second = startAgentRun(generation, {
    conversationId: "c",
    question: "第二个问题",
    commit: state.commit,
    onSettled: settled,
  });
  await opened(2);

  // 第一代的帧此刻才到达 —— 这就是 abort 之后仍在路上的那一段。
  push(0, delta("旧答案"));
  push(0, completed("旧答案"));
  bodies[0]?.close();
  await first.done;

  expect(state.read().streamedText).toBe("");
  expect(state.read().authoritativeAnswer).toBeNull();

  // 而当前这一代照常写入：修竞态不能变成把新 run 也一起静音。
  push(1, STARTED);
  push(1, delta("新-"));
  push(1, delta("答案"));
  push(1, completed("新答案"));
  bodies[1]?.close();
  await second.done;

  expect(state.read().streamedText).toBe("新-答案");
  expect(state.read().authoritativeAnswer).toBe("新答案");
});

test("被取代的那一代既不写状态，也不重读服务端记录", async () => {
  stubStreamingFetch();
  const generation = createGeneration();
  const state = collector();
  const rereads: string[] = [];

  const first = startAgentRun(generation, {
    conversationId: "c",
    question: "第一个问题",
    commit: state.commit,
    onSettled: async () => {
      rereads.push("first");
    },
  });
  await opened(1);

  // effect 清理走的就是这条顺序：先作废这一代，再中止它。
  generation.abandon();
  first.cancel();
  await first.done;

  expect(rereads).toEqual([]);
  expect(state.read()).toBe(INITIAL_RUN_STATE);
});

test("取消只中止自己那一代的请求", async () => {
  stubStreamingFetch();
  const generation = createGeneration();
  const state = collector();

  const first = startAgentRun(generation, {
    conversationId: "c",
    question: "第一个问题",
    commit: state.commit,
    onSettled: settled,
  });
  await opened(1);

  const second = startAgentRun(generation, {
    conversationId: "c",
    question: "第二个问题",
    commit: state.commit,
    onSettled: settled,
  });
  await opened(2);

  first.cancel();
  expect(signals[0]?.aborted).toBe(true);
  expect(signals[1]?.aborted).toBe(false);

  // 新一代自己的“停止生成”仍然是有效的。
  second.cancel();
  expect(signals[1]?.aborted).toBe(true);

  await Promise.all([first.done, second.done]);
});
