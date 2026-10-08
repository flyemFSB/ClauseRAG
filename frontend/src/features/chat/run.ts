/**
 * 单次 Agent 生成运行生命周期管理。
 *
 * 负责接收并规约 SSE 消息流（POST /conversations/{id}/messages），
 * 维护增量回答、权威答案、检索引用及运行状态（流式中、已完成、失败、已取消）。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../lib/api";
import { createGeneration, type Generation } from "../../lib/generation";
import { type AgentRunEvent, type CitationPayload, streamAgentRun } from "../../lib/sse";
import { conversationKeys } from "../../lib/queryKeys";

export type RunStatus = "streaming" | "completed" | "failed" | "cancelled";

export interface RunState {
  readonly status: RunStatus;
  /** 接收到的流式增量文本拼接结果。 */
  readonly streamedText: string;
  /** 服务端终态返回的权威校验答案；接收到终态事件后取代 streamedText。 */
  readonly authoritativeAnswer: string | null;
  readonly citations: readonly CitationPayload[];
  readonly evidenceStatus: string | null;
  readonly retrievalRounds: number | null;
  readonly intent: string | null;
  readonly finishReason: string | null;
  readonly errorClass: string | null;
  /** 错误描述文本。 */
  readonly errorMessage: string | null;
  readonly removedCitationIds: readonly string[];
  /** 用户消息 ID。 */
  readonly userMessageId: string | null;
  /** 助手消息 ID。 */
  readonly assistantMessageId: string | null;
}

export const INITIAL_RUN_STATE: RunState = {
  status: "streaming",
  streamedText: "",
  authoritativeAnswer: null,
  citations: [],
  evidenceStatus: null,
  retrievalRounds: null,
  intent: null,
  finishReason: null,
  errorClass: null,
  errorMessage: null,
  removedCitationIds: [],
  userMessageId: null,
  assistantMessageId: null,
};

/** 获取当前应呈现的文本（优先权威答案，未收尾时使用流式拼接文本）。 */
export function runText(state: RunState): string {
  return state.authoritativeAnswer ?? state.streamedText;
}

export function applyRunEvent(state: RunState, event: AgentRunEvent): RunState {
  switch (event.event) {
    case "run_started":
      return {
        ...state,
        status: "streaming",
        userMessageId: event.userMessageId,
        assistantMessageId: event.assistantMessageId,
      };
    case "answer_delta":
      return { ...state, streamedText: state.streamedText + event.text };
    case "citation":
      return { ...state, citations: [...state.citations, event.citation] };
    case "run_completed":
      return {
        ...state,
        status: "completed",
        authoritativeAnswer: event.answer,
        evidenceStatus: event.evidenceStatus,
        retrievalRounds: event.retrievalRounds,
        intent: event.intent,
        finishReason: event.finishReason,
        removedCitationIds: event.removedCitationIds,
        assistantMessageId: event.messageId,
      };
    case "run_failed":
      return {
        ...state,
        status: "failed",
        errorClass: event.errorClass,
        errorMessage: event.message,
        assistantMessageId: event.messageId ?? state.assistantMessageId,
      };
    case "run_cancelled":
      return {
        ...state,
        status: "cancelled",
        authoritativeAnswer: event.answer,
        assistantMessageId: event.messageId,
      };
  }
}

/** 校验异常是否为用户主动中止。 */
function isCancellation(cause: unknown): boolean {
  if (cause instanceof ApiError) {
    return cause.kind === "aborted";
  }
  return cause instanceof DOMException && cause.name === "AbortError";
}

export interface AgentRunDriver {
  /** 停止当前轮次运行（中止底层 HTTP 连接）。 */
  readonly cancel: () => void;
  /** 当前轮次完成或终止的 Promise。 */
  readonly done: Promise<void>;
}

export interface StartAgentRunOptions {
  readonly conversationId: string;
  readonly question: string;
  /** 状态更新回调。 */
  readonly commit: (update: (previous: RunState) => RunState) => void;
  /** 运行结束后的缓存失效与同步回调。 */
  readonly onSettled: () => Promise<void>;
}

/**
 * 启动单次 Agent 生成运行任务。
 *
 * 采用代际隔离（generation）控制并发，确保已过期的旧请求事件不会写入当前界面状态。
 */
export function startAgentRun(
  generation: Generation,
  options: StartAgentRunOptions,
): AgentRunDriver {
  const attempt = generation.begin();
  const controller = new AbortController();

  const done = (async () => {
    try {
      for await (const event of streamAgentRun({
        conversationId: options.conversationId,
        content: options.question,
        signal: controller.signal,
      })) {
        // 当前轮次已被更新的运行取代，直接丢弃
        if (!generation.isCurrent(attempt)) {
          return;
        }
        options.commit((previous) => applyRunEvent(previous, event));
      }
    } catch (cause) {
      if (!generation.isCurrent(attempt)) {
        return;
      }
      if (isCancellation(cause)) {
        options.commit((previous) => ({ ...previous, status: "cancelled" }));
        return;
      }
      options.commit((previous) => ({
        ...previous,
        status: "failed",
        errorClass: cause instanceof ApiError ? cause.kind : "stream_failed",
        errorMessage: cause instanceof Error ? cause.message : "流式回答传输异常中断",
      }));
    } finally {
      if (generation.isCurrent(attempt)) {
        await options.onSettled();
      }
    }
  })();

  return {
    cancel: () => {
      controller.abort();
    },
    done,
  };
}

export interface AgentRun {
  readonly state: RunState;
  /** 停止生成。 */
  readonly cancel: () => void;
}

/**
 * 驱动单轮会话提问与流式回答的自定义 Hook。
 *
 * 管理运行状态并自动在收尾后刷新会话详情与列表缓存。
 */
export function useAgentRun(
  conversationId: string | null,
  question: string | null,
  runKey: number,
): AgentRun {
  const identity = `${conversationId ?? ""}#${String(runKey)}#${question ?? ""}`;
  const [run, setRun] = useState<{ identity: string; state: RunState }>({
    identity,
    state: INITIAL_RUN_STATE,
  });
  // 跨渲染周期的代际栅栏实例
  const [generation] = useState(createGeneration);
  const driverRef = useRef<AgentRunDriver | null>(null);
  const client = useQueryClient();

  useEffect(() => {
    if (conversationId === null || question === null) {
      return;
    }
    const driver = startAgentRun(generation, {
      conversationId,
      question,
      commit: (update) => {
        setRun((previous) => ({
          identity,
          state: update(previous.identity === identity ? previous.state : INITIAL_RUN_STATE),
        }));
      },
      onSettled: async () => {
        await client.invalidateQueries({ queryKey: conversationKeys.detail(conversationId) });
        await client.invalidateQueries({ queryKey: conversationKeys.list() });
      },
    });
    driverRef.current = driver;

    return () => {
      // 切换上下文或卸载时废弃当前代际并中止请求
      generation.abandon();
      driver.cancel();
      if (driverRef.current === driver) {
        driverRef.current = null;
      }
    };
  }, [client, conversationId, generation, identity, question]);

  const cancel = useCallback(() => {
    driverRef.current?.cancel();
  }, []);

  // 校验当前标识符匹配，避免展示历史残留数据
  const state = run.identity === identity ? run.state : INITIAL_RUN_STATE;
  return { state, cancel };
}
