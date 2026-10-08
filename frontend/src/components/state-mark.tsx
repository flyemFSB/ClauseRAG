import type { ReactNode } from "react";
import { IconCheck, IconError, IconInfo, IconSlash, IconWarning, ProgressRing } from "./icons";

export type MarkTone = "pending" | "running" | "success" | "warning" | "error" | "muted" | "off";

const MARK_CLASS: Record<MarkTone, string> = {
  pending: "text-ink-muted",
  running: "text-accent",
  success: "text-success",
  warning: "text-warning",
  error: "text-error",
  muted: "text-ink-muted",
  off: "text-ink-muted",
};

const LABEL_CLASS: Record<MarkTone, string> = {
  pending: "text-ink-secondary",
  running: "text-accent-strong",
  success: "text-success-ink",
  warning: "text-warning-ink",
  error: "text-error-ink",
  muted: "text-ink-secondary",
  off: "text-ink-secondary",
};

function MarkGlyph({ tone, size }: { readonly tone: MarkTone; readonly size: number }): ReactNode {
  switch (tone) {
    case "success":
      return <IconCheck size={size} />;
    case "warning":
      return <IconWarning size={size} />;
    case "error":
      return <IconError size={size} />;
    case "running":
      return (
        <span className="animate-spin">
          <ProgressRing size={size + 2} ratio={0.28} state="running" />
        </span>
      );
    case "off":
      return <IconSlash size={size} />;
    case "pending":
      return (
        <span
          className="block rounded-full border-[1.5px] border-current"
          style={{ width: size - 3, height: size - 3 }}
        />
      );
    default:
      return <IconInfo size={size} />;
  }
}

export interface StatusMarkProps {
  readonly tone: MarkTone;
  readonly label: string;
  readonly title?: string;
  readonly variant?: "inline" | "pill";
  readonly size?: number;
}

/** 状态标识组件：组合图标符号与文本标签呈现多状态语义（遵循非纯色盲依赖规则）。 */
export function StatusMark({
  tone,
  label,
  title,
  variant = "inline",
  size = 14,
}: StatusMarkProps): ReactNode {
  const glyph = (
    <span className={`flex shrink-0 items-center ${MARK_CLASS[tone]}`}>
      <MarkGlyph tone={tone} size={size} />
    </span>
  );

  if (variant === "pill") {
    return (
      <span
        title={title}
        className={`inline-flex h-5 shrink-0 items-center gap-1 rounded-sm bg-surface px-1.5 text-label font-medium ${LABEL_CLASS[tone]}`}
      >
        {glyph}
        {label}
      </span>
    );
  }

  return (
    <span title={title} className="inline-flex min-w-0 items-center gap-1.5 text-dense">
      {glyph}
      <span className="truncate text-ink">{label}</span>
    </span>
  );
}
