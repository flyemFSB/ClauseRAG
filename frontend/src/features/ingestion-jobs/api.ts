/**
 * 文档摄取流水线任务数据模型与接口调用。
 *
 * 维护解析、分块、向量化、索引四个阶段的任务状态与重试逻辑。
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson } from "../../lib/api";
import { asNullableString, asNumber, asRecord, asString, parseList } from "../../lib/contract";
import { formatSpan, formatTimestamp } from "../../lib/format";
import { documentVersionKeys, knowledgeBaseKeys } from "../../lib/queryKeys";
import type { MarkTone } from "../../components/state-mark";
import type { Stage, StageName, StageState } from "../ingestion-jobs/Stepper";

const JOBS_PATH = "/api/v1/document-versions";
const RETRY_TIMEOUT_MS = 30_000;

export interface IngestionJob {
  readonly id: string;
  readonly documentVersionId: string;
  readonly stage: string;
  readonly status: string;
  readonly revision: number;
  readonly attempt: number;
  readonly errorClass: string | null;
  readonly errorMessage: string | null;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly startedAt: string | null;
  readonly finishedAt: string | null;
}

export interface ParseRetry {
  readonly job: IngestionJob;
  readonly versionStatus: string;
  readonly outcome: string;
  readonly created: boolean;
}

export function parseIngestionJob(payload: unknown): IngestionJob {
  const record = asRecord(payload, "ingestion job");
  return {
    id: asString(record, "id"),
    documentVersionId: asString(record, "document_version_id"),
    stage: asString(record, "stage"),
    status: asString(record, "status"),
    revision: asNumber(record, "revision"),
    attempt: asNumber(record, "attempt"),
    errorClass: asNullableString(record, "error_class"),
    errorMessage: asNullableString(record, "error_message"),
    createdAt: asString(record, "created_at"),
    updatedAt: asString(record, "updated_at"),
    startedAt: asNullableString(record, "started_at"),
    finishedAt: asNullableString(record, "finished_at"),
  };
}

export async function fetchVersionJobs(
  versionId: string,
  signal: AbortSignal,
): Promise<readonly IngestionJob[]> {
  const payload = await requestJson(`${JOBS_PATH}/${versionId}/jobs`, { signal });
  return parseList(payload, "ingestion jobs", parseIngestionJob);
}

export function versionJobsQueryOptions(versionId: string) {
  return {
    queryKey: documentVersionKeys.jobs(versionId),
    queryFn: ({ signal }: { readonly signal: AbortSignal }) => fetchVersionJobs(versionId, signal),
    staleTime: 4_000,
  };
}

export function useVersionJobs(versionId: string) {
  return useQuery(versionJobsQueryOptions(versionId));
}

function parseParseRetry(payload: unknown): ParseRetry {
  const record = asRecord(payload, "retry");
  return {
    job: parseIngestionJob(record["job"]),
    versionStatus: asString(record, "version_status"),
    outcome: asString(record, "outcome"),
    created: record["created"] === true,
  };
}

export async function retryVersion(versionId: string, signal: AbortSignal): Promise<ParseRetry> {
  return parseParseRetry(
    await requestJson(`${JOBS_PATH}/${versionId}/retry`, { signal, method: "POST" }),
  );
}

export function useRetryVersion(knowledgeBaseId: string | null) {
  const client = useQueryClient();
  return useMutation<ParseRetry, unknown, string>({
    mutationFn: (versionId: string) =>
      retryVersion(versionId, AbortSignal.timeout(RETRY_TIMEOUT_MS)),
    onSuccess: async (_result, versionId) => {
      await client.invalidateQueries({ queryKey: documentVersionKeys.detail(versionId) });
      await client.invalidateQueries({ queryKey: documentVersionKeys.jobs(versionId) });
      if (knowledgeBaseId !== null) {
        await client.invalidateQueries({ queryKey: knowledgeBaseKeys.documents(knowledgeBaseId) });
      }
    },
  });
}

export const JOB_STAGE_LABEL: Readonly<Record<string, string>> = {
  parse: "文档解析",
  chunk: "文本分块",
  embed: "向量化",
  index: "构建索引",
};

export const JOB_STATUS_LABEL: Readonly<Record<string, string>> = {
  pending: "待处理",
  running: "进行中",
  succeeded: "已完成",
  failed: "失败",
  manual_retry_required: "需人工重试",
};

export function jobStageLabel(stage: string): string {
  return JOB_STAGE_LABEL[stage] ?? stage;
}

export function jobStatusLabel(status: string): string {
  return JOB_STATUS_LABEL[status] ?? status;
}

export function jobStatusTone(status: string): MarkTone {
  switch (status) {
    case "succeeded":
      return "success";
    case "running":
      return "running";
    case "failed":
      return "error";
    case "manual_retry_required":
      return "warning";
    default:
      return "pending";
  }
}

export const RETRY_OUTCOME_LABEL: Readonly<Record<string, string>> = {
  created: "已追加一次解析重试，任务在队列中",
  stale: "上一次尝试已判定为中断，已追加新的一次",
  queued: "已排队的任务覆盖这次重试，没有追加新任务",
  running: "此刻有 worker 正在执行，重试未生效",
};

/** 判断当前任务列表中是否存在需要人工重试的失败阶段。 */
export function needsManualRetry(jobs: readonly IngestionJob[]): boolean {
  return jobs.some((job) => job.status === "failed" || job.status === "manual_retry_required");
}

const STAGE_NAME: Readonly<Record<string, StageName>> = {
  parse: "parse",
  chunk: "chunk",
  embed: "embed",
  index: "index",
};

/** 流水线阶段标准呈现顺序。 */
const STAGES: readonly StageName[] = ["parse", "chunk", "embed", "index"];

const STAGE_STATE: Readonly<Record<string, StageState>> = {
  pending: "pending",
  running: "running",
  succeeded: "completed",
  failed: "failed",
  manual_retry_required: "retry",
};

/** 按阶段提取最新版本的任务记录（用于阶段药丸与详情面板展示）。 */
export function newestJobsByStage(
  jobs: readonly IngestionJob[],
): ReadonlyMap<StageName, IngestionJob> {
  const newest = new Map<StageName, IngestionJob>();
  for (const job of jobs) {
    const name = STAGE_NAME[job.stage];
    if (name === undefined) {
      continue;
    }
    const current = newest.get(name);
    if (current === undefined || job.revision >= current.revision) {
      newest.set(name, job);
    }
  }
  return newest;
}

/** 将任务记录列表转换为流水线步进器阶段状态数组。 */
export function toPipelineStages(jobs: readonly IngestionJob[]): readonly Stage[] {
  const newest = newestJobsByStage(jobs);

  return STAGES.map((name) => {
    const job = newest.get(name);
    if (job === undefined) {
      return { name, state: "pending" as StageState, logs: [] };
    }
    const state: StageState = STAGE_STATE[job.status] ?? "pending";
    return {
      name,
      state,
      meta:
        state === "completed"
          ? formatSpan(job.startedAt ?? job.createdAt, job.finishedAt, Date.now())
          : state === "running"
            ? `自 ${formatTimestamp(job.startedAt ?? job.createdAt)}`
            : undefined,
      logs: [],
    };
  });
}
