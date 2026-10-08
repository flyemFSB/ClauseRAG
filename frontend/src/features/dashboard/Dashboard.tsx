/**
 * 知识资产看板主页面组件。
 *
 * 集中展示知识总量、容量、置信度/采纳率指标、合同类型分布、流水线吞吐与待处理失败任务诊断列表。
 */

import { useMemo, useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { knowledgeBaseKeys } from "../../lib/queryKeys";
import { IconReplay, IconWarning } from "../../components/icons";
import { FailureNotice } from "../../components/failure-notice";
import { SkeletonLines } from "../../components/skeleton";
import { formatBytes, formatTimestamp } from "../../lib/format";
import { CONSOLE_PATHS } from "../shell/paths";
import { useRetryVersion, RETRY_OUTCOME_LABEL, jobStageLabel } from "../ingestion-jobs/api";
import { useAssetDashboard, type Diagnostic } from "./api";
import {
  CITATION_ADOPTION,
  CONTRACT_TYPES,
  RETRIEVAL_QUALITY,
  SYNTHETIC_NOTICE,
} from "./analytics";
import { DonutChart, GaugeArc, MeterBar, ThroughputChart } from "./charts";

const PANEL = "rounded-lg border border-border bg-canvas shadow-tactile";
const PANEL_HEADER =
  "flex items-baseline gap-2 border-b border-divider px-4 py-3 text-dense font-medium text-ink";

function Figure({
  label,
  value,
  caption,
  mark,
  alert = false,
  synthetic = false,
}: {
  readonly label: string;
  readonly value: ReactNode;
  readonly caption: string;
  readonly mark?: ReactNode;
  readonly alert?: boolean;
  /** 是否带有“示意”徽标。 */
  readonly synthetic?: boolean;
}): ReactNode {
  return (
    <div className="flex flex-col justify-between gap-2.5 bg-canvas p-4.5 tint hover:bg-surface/30">
      <div>
        <p className="flex items-center gap-2 text-label font-medium text-ink-secondary">
          {alert ? (
            <span className="h-1.5 w-1.5 rounded-full bg-error animate-pulse" aria-hidden="true" />
          ) : null}
          {label}
          {synthetic ? (
            <span className="inline-flex h-4 items-center rounded-sm bg-warning-soft px-1.5 text-[11px] font-medium text-ink">
              示意
            </span>
          ) : null}
        </p>
        <p className="mt-2 text-[30px] font-semibold tracking-tight tabular-nums text-ink leading-none">
          {value}
        </p>
      </div>
      {mark}
      <p className="text-label text-ink-secondary">{caption}</p>
    </div>
  );
}

function ContractTypes(): ReactNode {
  const total = CONTRACT_TYPES.reduce((sum, entry) => sum + entry.count, 0);
  return (
    <section className={PANEL}>
      <h2 className={PANEL_HEADER}>
        审查合同类型分布
        <span className="inline-flex h-5 items-center rounded-sm bg-warning-soft px-1.5 text-label font-normal text-ink">
          示意
        </span>
        <span className="ml-auto text-label font-normal text-ink-secondary">
          近 7 天 {String(total)} 次审查
        </span>
      </h2>
      <div className="flex items-center gap-5 p-4">
        <DonutChart slices={CONTRACT_TYPES} centerLabel={String(total)} centerCaption="次审查" />
        <ul className="flex min-w-0 flex-1 flex-col gap-2">
          {CONTRACT_TYPES.map((entry) => (
            <li key={entry.label} className="flex items-baseline gap-3">
              <span className="min-w-0 flex-1 truncate text-dense text-ink">{entry.label}</span>
              <span className="text-dense tabular-nums text-ink-secondary">
                {String(entry.count)}
              </span>
              <span className="w-12 text-right text-dense tabular-nums font-medium text-ink">
                {(entry.share * 100).toFixed(1)}%
              </span>
            </li>
          ))}
        </ul>
      </div>
      <p className="border-t border-divider px-4 py-2 text-label text-ink-secondary">
        合同类型来自会话元数据分类，当前数据模型没有这个字段。
      </p>
    </section>
  );
}

function Throughput({
  days,
  pending,
}: {
  readonly days: readonly {
    readonly day: string;
    readonly stages: number;
  }[];
  readonly pending: boolean;
}): ReactNode {
  const totalStages = days.reduce((sum, day) => sum + day.stages, 0);
  return (
    <section className={PANEL}>
      <h2 className={PANEL_HEADER}>
        文档流水线吞吐
        <span className="ml-auto text-label font-normal text-ink-secondary">
          近 7 天 · 完成 {String(totalStages)} 个阶段
        </span>
      </h2>
      <div className="px-3 pt-3">
        {pending ? <SkeletonLines lines={4} /> : <ThroughputChart days={days} />}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2">
        <span className="flex items-center gap-2 text-label text-ink-secondary">
          <span className="h-2 w-3 rounded-sm bg-accent" aria-hidden="true" />
          当日完成阶段数
        </span>
        <span className="text-label text-ink-secondary">日标签下为当日完成阶段数</span>
      </div>
    </section>
  );
}

function Diagnostics({
  rows,
  pending,
  retrying,
  onRetry,
}: {
  readonly rows: readonly Diagnostic[];
  readonly pending: boolean;
  readonly retrying: readonly string[];
  readonly onRetry: (diagnostic: Diagnostic) => void;
}): ReactNode {
  return (
    <section className={PANEL}>
      <h2 className={PANEL_HEADER}>
        <IconWarning size={15} />
        待处理与诊断
        <span className="text-label font-normal text-ink-secondary">
          {String(rows.length)} 个失败阶段
        </span>
        <span className="ml-auto text-label font-normal text-ink-secondary">
          每份文档只读最新版本的任务
        </span>
      </h2>

      {pending ? (
        <SkeletonLines lines={4} />
      ) : rows.length === 0 ? (
        <p className="px-4 py-8 text-center text-dense text-ink-secondary">
          没有待处理的异常：每份文档最新版本的任务都没有失败或等待人工重试的阶段。
        </p>
      ) : (
        <ul>
          <li className="flex items-center gap-3 border-b border-divider px-4 py-2">
            <span className="text-label text-ink-secondary">文档</span>
            <span className="ml-auto text-label text-ink-secondary">阶段 · 原因 · 时间</span>
          </li>
          {rows.map((row) => {
            const isRetrying = retrying.includes(row.versionId);
            return (
              <li
                key={`${row.versionId}-${row.stage}`}
                className="flex items-center gap-3 border-b border-divider px-4 py-2 last:border-b-0"
              >
                <Link
                  to={CONSOLE_PATHS.documents}
                  search={{ doc: row.documentId }}
                  className="min-w-0 flex-1 truncate text-dense text-ink hover:underline"
                >
                  {row.documentName}
                </Link>
                <span className="hidden shrink-0 items-center gap-2 md:flex">
                  <span className="inline-flex h-5 items-center rounded-[var(--radius-pill)] bg-surface px-2 font-mono text-label text-ink-secondary">
                    {row.stage}
                  </span>
                  <span className="max-w-[260px] truncate text-label text-error-ink">
                    {row.errorClass ?? row.errorMessage ?? "未记录原因"}
                  </span>
                  <span className="w-32 text-right text-label tabular-nums text-ink-secondary">
                    {formatTimestamp(row.at)}
                  </span>
                </span>
                {isRetrying ? (
                  <span className="inline-flex h-7 shrink-0 items-center rounded-md bg-accent-soft px-2 text-label font-medium text-accent-strong">
                    已重新排队
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      onRetry(row);
                    }}
                    className="flex h-7 shrink-0 items-center gap-2 rounded-md px-2 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink"
                  >
                    <IconReplay size={13} />
                    重试解析
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <p className="border-t border-divider px-4 py-2 text-label text-ink-secondary">
        重试调用 <span className="font-mono">POST /document-versions/&#123;id&#125;/retry</span>
        ，只重启解析阶段——这是契约提供的唯一重试。其它阶段的失败要修复原因后重新上传。
      </p>
    </section>
  );
}

export function Dashboard(): ReactNode {
  const dashboard = useAssetDashboard();
  const client = useQueryClient();
  const retry = useRetryVersion(null);
  const [retrying, setRetrying] = useState<readonly string[]>([]);
  const [outcome, setOutcome] = useState<{
    readonly text: string;
    readonly tone: "ok" | "error";
  } | null>(null);

  const figures = dashboard.figures;

  const runRetry = useMemo(
    () =>
      async (diagnostic: Diagnostic): Promise<void> => {
        setOutcome(null);
        setRetrying((current) => [...current, diagnostic.versionId]);
        try {
          const result = await retry.mutateAsync(diagnostic.versionId);
          setOutcome({
            text: `${diagnostic.documentName}（${jobStageLabel(diagnostic.stage)}）：${
              RETRY_OUTCOME_LABEL[result.outcome] ?? `后端返回 ${result.outcome}`
            }`,
            tone: result.created ? "ok" : "error",
          });
          await client.invalidateQueries({ queryKey: knowledgeBaseKeys.all() });
        } catch (error) {
          setOutcome({
            text: `${diagnostic.documentName}：${error instanceof Error ? error.message : "重试失败"}`,
            tone: "error",
          });
        } finally {
          setRetrying((current) => current.filter((id) => id !== diagnostic.versionId));
        }
      },
    [client, retry],
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-4 px-5 py-5">
        <header className="flex flex-col gap-2">
          <div className="flex flex-wrap items-baseline gap-3">
            <h1 className="text-title font-semibold text-ink">知识资产看板</h1>
            <span className="ml-auto text-dense text-ink-secondary">
              最近 7 天 · 更新于 {formatTimestamp(figures.lastUpdated)}
            </span>
          </div>
          <p className="max-w-[92ch] text-dense text-ink-secondary">{SYNTHETIC_NOTICE}</p>
        </header>

        {dashboard.error === null ? null : (
          <FailureNotice title="看板数据不完整" detail={dashboard.error} />
        )}

        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-divider lg:grid-cols-4">
          <Figure
            label="已构建知识总量"
            value={
              <>
                {String(figures.documents)}
                <span className="ml-1 text-section font-medium text-ink-secondary">份</span>
                <span className="ml-2 text-section font-medium text-ink-secondary">
                  {formatBytes(figures.bytes)}
                </span>
              </>
            }
            caption={`就绪 ${String(figures.ready)} 份 · 版本状态为 ready 的文档数`}
          />
          <Figure
            label="RAG 检索平均置信度"
            value={RETRIEVAL_QUALITY.label}
            mark={<GaugeArc value={RETRIEVAL_QUALITY.confidence} className="h-[46px] w-[84px]" />}
            caption={`${RETRIEVAL_QUALITY.window} · 需要分析端点`}
            synthetic
          />
          <Figure
            label="引用采纳率"
            value={CITATION_ADOPTION.label}
            mark={<MeterBar value={CITATION_ADOPTION.adoption} />}
            caption={`${CITATION_ADOPTION.window} · 需要产品埋点`}
            synthetic
          />
          <Figure
            label="待处理失败阶段"
            value={
              <>
                {String(dashboard.diagnostics.length)}
                <span className="ml-1 text-section font-medium text-ink-secondary">个</span>
              </>
            }
            alert
            caption="每份文档最新版本的失败与人工重试阶段"
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.05fr_1fr]">
          <ContractTypes />
          <Throughput days={dashboard.throughput} pending={dashboard.pending} />
        </div>

        {outcome === null ? null : (
          <FailureNotice
            title={outcome.tone === "ok" ? "重试结果" : "重试未生效"}
            detail={outcome.text}
            action={
              <button
                type="button"
                onClick={() => {
                  setOutcome(null);
                }}
                className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
              >
                知道了
              </button>
            }
          />
        )}

        <Diagnostics
          rows={dashboard.diagnostics}
          pending={dashboard.pending}
          retrying={retrying}
          onRetry={(diagnostic) => {
            void runRetry(diagnostic);
          }}
        />

        <p className="pb-1 text-label text-ink-secondary">
          知识库里没有的商业合同与协议模板，去{" "}
          <Link to={CONSOLE_PATHS.documents} className="text-accent-strong hover:underline">
            文档与流水线
          </Link>{" "}
          上传；上传后解析、分块、嵌入与索引的进度同样在那两页。
        </p>
      </div>
    </div>
  );
}
