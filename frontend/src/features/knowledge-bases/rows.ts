import { formatBytes, formatTimestamp } from "../../lib/format";
import {
  documentKindOf,
  documentStatusOf,
  SUPPORTED_UPLOAD_EXTENSIONS,
  type DocumentSummary,
  type DocumentVersion,
} from "../documents/api";

export interface Row {
  readonly document: DocumentSummary;
  readonly version: DocumentVersion | null;
  readonly status: ReturnType<typeof documentStatusOf>;
  readonly kind: string;
  readonly size: string;
  readonly uploadedAt: string;
}

export function rowOf(document: DocumentSummary): Row {
  const version = document.latestVersion;
  return {
    document,
    version,
    status: documentStatusOf(version),
    kind: version === null ? "—" : documentKindOf(version.mimeType),
    size: version === null ? "—" : formatBytes(version.sizeBytes),
    uploadedAt: formatTimestamp(version?.createdAt ?? document.createdAt),
  };
}

export type StatusFilter = "all" | "parsed" | "processing" | "failed";

export const FILTER_LABEL: Record<StatusFilter, string> = {
  all: "全部状态",
  parsed: "仅已解析",
  processing: "仅处理中",
  failed: "仅失败",
};

export function matchesFilter(row: Row, filter: StatusFilter): boolean {
  switch (filter) {
    case "all":
      return true;
    case "parsed":
      return row.status === "parsed";
    case "processing":
      return row.status === "running" || row.status === "queued";
    case "failed":
      return row.status === "failed";
  }
}

export interface Figure {
  readonly label: string;
  readonly value: string;
  readonly note: string;
  /** 是否以紧凑字体排版（如时间戳）。 */
  readonly compact?: boolean;
}

export function figuresOf(rows: readonly Row[], name: string): readonly Figure[] {
  const bytes = rows.reduce((sum, row) => sum + (row.version?.sizeBytes ?? 0), 0);
  const ready = rows.filter(
    (row) =>
      row.version !== null && (row.version.status === "ready" || row.version.status === "parsed"),
  ).length;
  const newest = rows.reduce<string | null>((latest, row) => {
    const at = row.version?.updatedAt ?? row.document.updatedAt;
    return latest === null || Date.parse(at) > Date.parse(latest) ? at : latest;
  }, null);
  return [
    { label: "文档总数", value: String(rows.length), note: `全部来自「${name}」` },
    { label: "知识库容量", value: formatBytes(bytes), note: "上传文件字节之和" },
    {
      label: "已解析文档",
      value: String(ready),
      note: `其余 ${String(rows.length - ready)} 份在流水线或失败`,
    },
    {
      label: "最近更新",
      value: formatTimestamp(newest),
      note: "最新一次版本变更",
      compact: true,
    },
  ];
}

export const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;

export type QueueState = "waiting" | "uploading" | "done" | "failed" | "rejected";

export interface QueueItem {
  readonly id: string;
  readonly file: File;
  readonly state: QueueState;
  /** 上传被拒或失败原因说明。 */
  readonly reason?: string;
}

export function refusalOf(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!SUPPORTED_UPLOAD_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return `不支持的格式：契约接受 ${SUPPORTED_UPLOAD_EXTENSIONS.join("、")}。`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `超过 100 MB 上限（${formatBytes(file.size)}）。`;
  }
  return null;
}

export const CELL = "px-3 text-dense text-ink";
export const HEAD_CELL = "px-3 text-left text-label font-medium text-ink-secondary";
