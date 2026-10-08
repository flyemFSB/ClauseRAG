/**
 * 配置项展示表格
 *
 * 行（名称、环境变量、说明）由页面手写，**值**来自后端：页面只声明"哪些项值得解释"，值由
 * `GET /api/v1/config` 报出本进程实际读到的那一份。两者分开是为了让一个被环境变量覆盖过的部署
 * 在页面上看得见——值写在代码里就永远显示默认值，等于换个地方抄手册。
 */

import type { ReactNode } from "react";

import { configValue, type EffectiveConfig } from "./api";

export interface ConfigRow {
  /** 配置项显示名称 */
  readonly name: string;
  /** 对应的环境变量名称，同时是取值键 */
  readonly env: string;
  /** 说明与变更影响 */
  readonly detail: string;
}

export function ConfigCaveat({ children }: { readonly children: ReactNode }): ReactNode {
  return <p className="rounded-lg bg-surface p-3 text-dense text-ink-secondary">{children}</p>;
}

export function ConfigGroup({
  title,
  rows,
  config,
}: {
  readonly title: string;
  readonly rows: readonly ConfigRow[];
  readonly config: EffectiveConfig | undefined;
}): ReactNode {
  return (
    <section className="rounded-lg border border-border bg-canvas">
      <h2 className="border-b border-border px-4 py-3 text-section font-semibold text-ink">
        {title}
      </h2>
      <dl className="divide-y divide-divider">
        {rows.map((row) => (
          <div
            key={row.env}
            className="grid gap-x-4 gap-y-1 px-4 py-3 md:grid-cols-[minmax(0,1.1fr)_minmax(0,0.7fr)_minmax(0,2fr)]"
          >
            <dt className="text-dense font-medium text-ink">{row.name}</dt>
            <dd className="font-mono text-dense tabular-nums text-ink md:text-right">
              {configValue(config, row.env)}
            </dd>
            <dd className="text-dense text-ink-secondary">
              {row.detail}
              <span className="mt-1 block font-mono text-quote text-ink-muted">{row.env}</span>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
