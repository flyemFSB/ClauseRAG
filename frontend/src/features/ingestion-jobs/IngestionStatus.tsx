/**
 * 文档摄取状态徽标组件。
 *
 * 采用文本与图形双重标识呈现排队中、解析中、已解析、失败等状态。
 */

import { type ReactNode } from "react";
import { IconCheck, IconError, IconInfo, Spinner } from "../../components/icons";

export type DocumentStatus = "queued" | "running" | "parsed" | "failed";

const STATUS_STYLE: Record<DocumentStatus, string> = {
  queued: "bg-surface text-ink-secondary",
  running: "bg-accent-soft text-accent-strong",
  parsed: "bg-success/10 text-success-ink",
  failed: "bg-error/10 text-error-ink",
};

const STATUS_LABEL: Record<DocumentStatus, string> = {
  queued: "排队中",
  running: "解析中",
  parsed: "已解析",
  failed: "失败",
};

export function StatusBadge({
  status,
  stage,
}: {
  readonly status: DocumentStatus;
  readonly stage?: string;
}): ReactNode {
  const icon =
    status === "running" ? (
      <Spinner />
    ) : status === "parsed" ? (
      <IconCheck size={14} />
    ) : status === "failed" ? (
      <IconError size={14} />
    ) : (
      <IconInfo size={14} />
    );

  return (
    <span
      className={`inline-flex h-5 items-center gap-1 rounded-sm px-1.5 text-label font-medium ${STATUS_STYLE[status]}`}
    >
      {icon}
      <span>
        {STATUS_LABEL[status]}
        {status === "running" && stage !== undefined ? ` · ${stage}` : ""}
      </span>
    </span>
  );
}
