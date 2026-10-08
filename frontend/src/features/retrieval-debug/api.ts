/**
 * 检索调试 API 服务与数据模型。
 *
 * 发起即时单轮检索诊断（POST /retrieval-debug/query），
 * 获取密集向量、关键词两通道召回、RRF 融合、重排与证据门控决策报告。
 */

import { useMutation } from "@tanstack/react-query";
import { requestJson } from "../../lib/api";
import {
  asArray,
  asNullableNumber,
  asNullableString,
  asNumber,
  asRecord,
  asString,
  parseList,
} from "../../lib/contract";
import type { MarkTone } from "../../components/state-mark";

const DEBUG_PATH = "/api/v1/retrieval-debug/query";
const RUN_TIMEOUT_MS = 130_000;

export interface ChannelHit {
  readonly childId: string;
  readonly parentId: string;
  readonly documentVersionId: string;
  readonly rank: number;
  readonly rawScore: number | null;
}

export interface ChannelReport {
  readonly channel: string;
  readonly status: string;
  readonly latencyMs: number;
  readonly errorType: string | null;
  readonly hits: readonly ChannelHit[];
}

export interface Candidate {
  readonly childId: string;
  readonly parentId: string;
  readonly documentVersionId: string;
  readonly ordinal: number;
  readonly rrfScore: number;
  readonly rerankScore: number | null;
  readonly channelRanks: Readonly<Record<string, number>>;
}

export interface RerankReport {
  readonly status: string;
  readonly model: string | null;
  readonly scored: number;
  readonly reason: string | null;
}

export interface EvidenceReport {
  readonly status: string;
  readonly reason: string;
  readonly accepted: readonly string[];
}

export interface ContextSource {
  readonly citationId: string;
  readonly childId: string;
  readonly parentId: string;
  readonly documentId: string;
  readonly documentVersionId: string;
  readonly documentName: string;
  readonly headingPath: readonly string[];
  readonly lineStart: number;
  readonly lineEnd: number;
  readonly quote: string;
}

export interface RetrievalReport {
  readonly query: string;
  readonly queries: readonly string[];
  readonly intent: string;
  readonly channels: readonly ChannelReport[];
  readonly fused: readonly Candidate[];
  readonly reranked: readonly Candidate[];
  readonly rerank: RerankReport;
  readonly evidence: EvidenceReport;
  readonly contextSources: readonly ContextSource[];
  readonly contextTokens: number;
}

function parseChannelRanks(record: Record<string, unknown>): Record<string, number> {
  const ranks: Record<string, number> = {};
  for (const [channel, rank] of Object.entries(record)) {
    if (typeof rank === "number") {
      ranks[channel] = rank;
    }
  }
  return ranks;
}

function parseHit(payload: unknown): ChannelHit {
  const record = asRecord(payload, "channel hit");
  return {
    childId: asString(record, "child_id"),
    parentId: asString(record, "parent_id"),
    documentVersionId: asString(record, "document_version_id"),
    rank: asNumber(record, "rank"),
    rawScore: asNullableNumber(record, "raw_score"),
  };
}

function parseChannel(payload: unknown): ChannelReport {
  const record = asRecord(payload, "channel");
  return {
    channel: asString(record, "channel"),
    status: asString(record, "status"),
    latencyMs: asNumber(record, "latency_ms"),
    errorType: asNullableString(record, "error_type"),
    hits: parseList(record["hits"], "channel hits", parseHit),
  };
}

function parseCandidate(payload: unknown): Candidate {
  const record = asRecord(payload, "candidate");
  return {
    childId: asString(record, "child_id"),
    parentId: asString(record, "parent_id"),
    documentVersionId: asString(record, "document_version_id"),
    ordinal: asNumber(record, "ordinal"),
    rrfScore: asNumber(record, "rrf_score"),
    rerankScore: asNullableNumber(record, "rerank_score"),
    channelRanks: parseChannelRanks(asRecord(record["channel_ranks"], "channel ranks")),
  };
}

function parseContextSource(payload: unknown): ContextSource {
  const record = asRecord(payload, "context source");
  return {
    citationId: asString(record, "citation_id"),
    childId: asString(record, "child_id"),
    parentId: asString(record, "parent_id"),
    documentId: asString(record, "document_id"),
    documentVersionId: asString(record, "document_version_id"),
    documentName: asString(record, "document_name"),
    headingPath: asArray(record, "heading_path").map((part) => String(part)),
    lineStart: asNumber(record, "line_start"),
    lineEnd: asNumber(record, "line_end"),
    quote: asString(record, "quote"),
  };
}

export function parseRetrievalReport(payload: unknown): RetrievalReport {
  const record = asRecord(payload, "retrieval report");
  const rerank = asRecord(record["rerank"], "rerank");
  const evidence = asRecord(record["evidence"], "evidence");
  return {
    query: asString(record, "query"),
    queries: asArray(record, "queries").map((part) => String(part)),
    intent: asString(record, "intent"),
    channels: parseList(record["channels"], "channels", parseChannel),
    fused: parseList(record["fused"], "fused", parseCandidate),
    reranked: parseList(record["reranked"], "reranked", parseCandidate),
    rerank: {
      status: asString(rerank, "status"),
      model: asNullableString(rerank, "model"),
      scored: asNumber(rerank, "scored"),
      reason: asNullableString(rerank, "reason"),
    },
    evidence: {
      status: asString(evidence, "status"),
      reason: asString(evidence, "reason"),
      accepted: asArray(evidence, "accepted").map((part) => String(part)),
    },
    contextSources: parseList(record["context_sources"], "context sources", parseContextSource),
    contextTokens: asNumber(record, "context_tokens"),
  };
}

/** 触发单次检索调试运行。 */
export async function runRetrievalDebug(
  knowledgeBaseId: string,
  query: string,
  signal: AbortSignal,
): Promise<RetrievalReport> {
  return parseRetrievalReport(
    await requestJson(DEBUG_PATH, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(RUN_TIMEOUT_MS)]),
      method: "POST",
      body: { knowledge_base_id: knowledgeBaseId, query },
    }),
  );
}

export function useRetrievalDebug() {
  return useMutation<
    RetrievalReport,
    unknown,
    { readonly knowledgeBaseId: string; readonly query: string; readonly signal: AbortSignal }
  >({
    mutationFn: ({ knowledgeBaseId, query, signal }) =>
      runRetrievalDebug(knowledgeBaseId, query, signal),
  });
}

export const CHANNEL_LABEL: Readonly<Record<string, string>> = {
  dense: "dense",
  keyword: "keyword",
};

export function channelLabel(channel: string): string {
  return CHANNEL_LABEL[channel] ?? channel;
}

export const CHANNEL_STATUS_LABEL: Readonly<Record<string, string>> = {
  ok: "有结果",
  empty: "无结果",
  failed: "检索失败",
  unavailable: "未启用",
};

export function channelStatusLabel(status: string): string {
  return CHANNEL_STATUS_LABEL[status] ?? status;
}

export function channelStatusTone(status: string): MarkTone {
  switch (status) {
    case "ok":
      return "success";
    case "empty":
      return "muted";
    case "failed":
      return "error";
    default:
      return "off";
  }
}

export const EVIDENCE_STATUS_LABEL: Readonly<Record<string, string>> = {
  sufficient: "证据充足",
  degraded: "证据降级",
  insufficient: "证据不足",
  unverified: "引用未验证",
};

export function evidenceStatusLabel(status: string): string {
  return EVIDENCE_STATUS_LABEL[status] ?? status;
}

export function evidenceStatusTone(status: string): MarkTone {
  switch (status) {
    case "sufficient":
      return "success";
    case "degraded":
    case "unverified":
      return "warning";
    default:
      return "muted";
  }
}

export const RERANK_STATUS_LABEL: Readonly<Record<string, string>> = {
  ok: "已重排",
  degraded: "重排不可用，保留融合顺序",
  skipped: "本次未重排",
};

export function rerankStatusLabel(status: string): string {
  return RERANK_STATUS_LABEL[status] ?? status;
}

export function rerankStatusTone(status: string): MarkTone {
  switch (status) {
    case "ok":
      return "success";
    case "degraded":
      return "warning";
    default:
      return "muted";
  }
}

export const INTENT_LABEL: Readonly<Record<string, string>> = {
  retrieval: "检索问答",
  direct_response: "直接回答",
  ask_clarification: "反问澄清",
  plan_retrieval: "规划检索",
};

export function intentLabel(intent: string): string {
  return INTENT_LABEL[intent] ?? intent;
}
