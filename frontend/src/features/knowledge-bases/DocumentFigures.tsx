import type { ReactNode } from "react";

import { figuresOf, type Row } from "./rows";

interface DocumentFiguresProps {
  readonly rows: readonly Row[];
  readonly knowledgeBaseName: string;
  readonly isPending: boolean;
  readonly inFlight: boolean;
}

export function DocumentFigures({
  rows,
  knowledgeBaseName,
  isPending,
  inFlight,
}: DocumentFiguresProps): ReactNode {
  return (
    <section className="mt-5 rounded-lg border border-border">
      <dl className="grid grid-cols-1 divide-y divide-divider md:grid-cols-4 md:divide-x md:divide-y-0">
        {figuresOf(rows, knowledgeBaseName).map((metric) => (
          <div key={metric.label} className="p-4">
            <dt className="text-label text-ink-secondary">{metric.label}</dt>
            <dd
              className={`mt-1 font-semibold tabular-nums text-ink ${metric.compact === true ? "text-section" : "text-title"}`}
            >
              {isPending ? "—" : metric.value}
            </dd>
            <p className="mt-1 text-label text-ink-secondary">
              {isPending ? "正在读取文档列表" : metric.note}
            </p>
          </div>
        ))}
      </dl>
      <p className="border-t border-divider px-4 py-2 text-label text-ink-secondary">
        {inFlight
          ? "有文档仍在流水线中，这一页每 5 秒自动刷新一次。"
          : "数值取自文档列表的实测字节数与版本状态；契约没有分析端点，因此没有「较上月」一类的对比。"}
      </p>
    </section>
  );
}
