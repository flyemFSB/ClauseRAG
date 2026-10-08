/**
 * 控制台资产看板数据聚合服务。
 *
 * 聚合知识库文档总数、容量、就绪数、最新流水线吞吐与待处理失败任务诊断信息。
 */

import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { useDocumentCatalogue, type DocumentSummary } from "../documents/api";
import { versionJobsQueryOptions, type IngestionJob } from "../ingestion-jobs/api";

/** 核心资产统计指标。 */
export interface AssetFigures {
  readonly documents: number;
  readonly bytes: number;
  readonly ready: number;
  readonly lastUpdated: string | null;
}

/** 单日流水线处理吞吐（完成阶段数）。 */
export interface DayThroughput {
  readonly day: string;
  readonly stages: number;
}

export interface Diagnostic {
  readonly documentId: string;
  readonly documentName: string;
  readonly versionId: string;
  readonly stage: string;
  readonly errorClass: string | null;
  readonly errorMessage: string | null;
  readonly at: string;
}

/** 文档最新版本及其关联任务集合。 */
interface Latest {
  readonly document: DocumentSummary;
  readonly version: NonNullable<DocumentSummary["latestVersion"]>;
  readonly jobs: readonly IngestionJob[];
}

const DAY_LABELS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"] as const;
const DAY_MS = 24 * 60 * 60 * 1000;
const WINDOW_DAYS = 7;

/** 统计近 7 天每日已完成阶段数。 */
function throughputOf(jobs: readonly IngestionJob[], now: number): readonly DayThroughput[] {
  const days: DayThroughput[] = [];
  for (let offset = WINDOW_DAYS - 1; offset >= 0; offset -= 1) {
    const dayStart = new Date(now - offset * DAY_MS);
    dayStart.setHours(0, 0, 0, 0);
    const start = dayStart.getTime();
    const end = start + DAY_MS;
    const finished = jobs.filter((job) => {
      if (job.finishedAt === null) {
        return false;
      }
      const at = Date.parse(job.finishedAt);
      return !Number.isNaN(at) && at >= start && at < end;
    });
    days.push({
      day: DAY_LABELS[dayStart.getDay()] ?? "",
      stages: finished.length,
    });
  }
  return days;
}

export interface AssetDashboard {
  readonly figures: AssetFigures;
  readonly throughput: readonly DayThroughput[];
  readonly diagnostics: readonly Diagnostic[];
  /** 任意依赖请求进行中时为 true。 */
  readonly pending: boolean;
  /** 错误描述文本。 */
  readonly error: string | null;
}

/** 聚合加载并计算看板展示所需的各项核心指标与吞吐统计。 */
export function useAssetDashboard(): AssetDashboard {
  const catalogue = useDocumentCatalogue();
  const documents = useMemo(
    () => catalogue.entries.map((entry) => entry.document),
    [catalogue.entries],
  );

  const versions = useMemo(
    () =>
      documents
        .map((document) => ({ document, version: document.latestVersion }))
        .filter(
          (
            entry,
          ): entry is {
            document: DocumentSummary;
            version: NonNullable<DocumentSummary["latestVersion"]>;
          } => entry.version !== null,
        ),
    [documents],
  );

  const jobQueries = useQueries({
    queries: versions.map((entry) => versionJobsQueryOptions(entry.version.id)),
  });

  return useMemo<AssetDashboard>(() => {
    const now = new Date();
    now.setHours(23, 59, 59, 999);

    const latest: Latest[] = versions.map((entry, index) => ({
      document: entry.document,
      version: entry.version,
      jobs: jobQueries[index]?.data ?? [],
    }));

    const allJobs = latest.flatMap((entry) => entry.jobs);

    const figures: AssetFigures = {
      documents: documents.length,
      bytes: documents.reduce((sum, document) => sum + (document.latestVersion?.sizeBytes ?? 0), 0),
      ready: documents.filter((document) => document.latestVersion?.status === "ready").length,
      lastUpdated: documents.reduce<string | null>((latestAt, document) => {
        const at = document.latestVersion?.updatedAt ?? document.updatedAt;
        return latestAt === null || Date.parse(at) > Date.parse(latestAt) ? at : latestAt;
      }, null),
    };

    const diagnostics: Diagnostic[] = latest.flatMap((entry) =>
      entry.jobs
        .filter((job) => job.status === "failed" || job.status === "manual_retry_required")
        .map((job) => ({
          documentId: entry.document.id,
          documentName: entry.document.title,
          versionId: entry.version.id,
          stage: job.stage,
          errorClass: job.errorClass,
          errorMessage: job.errorMessage,
          at: job.finishedAt ?? job.updatedAt,
        })),
    );

    const error =
      catalogue.error !== null || jobQueries.some((query) => query.isError)
        ? "看板的部分数据没有读出来：文档目录或任务列表之一请求失败。"
        : null;

    return {
      figures,
      throughput: throughputOf(allJobs, now.getTime()),
      diagnostics: diagnostics.sort((left, right) => Date.parse(right.at) - Date.parse(left.at)),
      pending: catalogue.pending || jobQueries.some((query) => query.isPending),
      error,
    };
  }, [catalogue.error, catalogue.pending, documents, jobQueries, versions]);
}
