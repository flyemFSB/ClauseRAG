import type { ReactNode } from "react";
import { StatusMark } from "./state-mark";

/** 失败提示条：展示错误信息并提供明确的操作恢复路径。 */
export function FailureNotice({
  title,
  detail,
  action,
}: {
  readonly title: string;
  readonly detail: string;
  readonly action?: ReactNode;
}): ReactNode {
  return (
    <section
      role="alert"
      className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-border bg-canvas px-4 py-3"
    >
      <div className="min-w-0 flex-1">
        <StatusMark tone="error" label={title} />
        <p className="mt-1 max-w-[100ch] text-dense break-words text-ink-secondary">{detail}</p>
      </div>
      {action === undefined ? null : <div className="shrink-0">{action}</div>}
    </section>
  );
}

/** 空数据提示占位组件。 */
export function EmptyState({
  title,
  children,
}: {
  readonly title: string;
  readonly children: ReactNode;
}): ReactNode {
  return (
    <section className="rounded-lg border border-border bg-canvas px-4 py-8">
      <h2 className="text-section font-semibold text-ink">{title}</h2>
      <p className="mt-1.5 max-w-[80ch] text-body text-ink-secondary">{children}</p>
    </section>
  );
}
