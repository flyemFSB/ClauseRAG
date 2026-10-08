/**
 * 文档摄取流水线步进器与阶段详情面板组件。
 *
 * 包含解析、分块、向量化、索引四个阶段的药丸状态节点（StagePills）
 * 以及展开后查看任务执行详情与解析产物的面板（StageDetailPanel）。
 */

import { type ReactNode } from "react";
import {
  IconCheck,
  IconError,
  IconReplay,
  IconWarning,
  ProgressRing,
} from "../../components/icons";
import { formatBytes, formatTimestamp, formatSpan, shortId } from "../../lib/format";
import type { ParseArtifact } from "../documents/api";
import { jobStatusLabel, type IngestionJob } from "./api";

export const STAGES = ["parse", "chunk", "embed", "index"] as const;

export type StageName = (typeof STAGES)[number];

/** 阶段运行状态（包含需人工重试、告警等子状态）。 */
export type StageState = "pending" | "running" | "completed" | "warning" | "failed" | "retry";

export interface Stage {
  readonly name: StageName;
  readonly state: StageState;
  /** 阶段附加产物或时间元数据（如耗时文本）。 */
  readonly meta?: string;
  /** 估计进度（0–1），无法估计时为 null。 */
  readonly progress?: number | null;
  readonly elapsed?: string;
  readonly logs: readonly string[];
}

export const STAGE_LABEL: Record<StageName, string> = {
  parse: "文档解析",
  chunk: "文本分块",
  embed: "向量化",
  index: "构建索引",
};

export const STATE_LABEL: Record<StageState, string> = {
  pending: "待处理",
  running: "进行中",
  completed: "已就绪",
  warning: "告警",
  failed: "失败",
  retry: "需人工重试",
};

function NodeGlyph({
  state,
  progress,
  size = 18,
}: {
  readonly state: StageState;
  readonly progress: number;
  readonly size?: number;
}): ReactNode {
  switch (state) {
    case "completed":
      return (
        <span className="text-success">
          <IconCheck size={size} />
        </span>
      );
    case "running":
      return (
        <span className="animate-spin">
          <ProgressRing size={size + 2} ratio={progress} state="running" />
        </span>
      );
    case "warning":
      return (
        <span className="text-warning">
          <IconWarning size={size} />
        </span>
      );
    case "retry":
      return (
        <span className="text-warning">
          <IconReplay size={size} />
        </span>
      );
    case "failed":
      return (
        <span className="text-error">
          <IconError size={size} />
        </span>
      );
    default:
      return (
        <span
          className="block rounded-full border-[1.5px] border-ink-muted"
          style={{ width: size, height: size }}
        />
      );
  }
}

/** 获取阶段节点展示的单行摘要文本（进度百分比、耗时或状态说明）。 */
function stageSummary(stage: Stage): string {
  if (stage.state === "warning" || stage.state === "failed" || stage.state === "retry") {
    return STATE_LABEL[stage.state];
  }
  if (stage.state === "running") {
    return stage.progress != null
      ? `${String(Math.round(stage.progress * 100))}%`
      : (stage.elapsed ?? STATE_LABEL.running);
  }
  return stage.meta ?? STATE_LABEL[stage.state];
}

export interface StagePillsProps {
  readonly stages: readonly Stage[];
  /** 当前选中的阶段；为 null 时表示所有阶段详情面板均处于收起状态。 */
  readonly selected: StageName | null;
  readonly onSelect: (stage: StageName) => void;
}

/** 流水线各阶段状态药丸横向列表组件。 */
export function StagePills({ stages, selected, onSelect }: StagePillsProps): ReactNode {
  return (
    <ol className="flex flex-wrap items-center gap-1.5" aria-label="解析流水线">
      {stages.map((stage, index) => {
        const isSelected = stage.name === selected;
        const isRunning = stage.state === "running";
        return (
          <li key={stage.name} className="flex items-center gap-1.5">
            {index > 0 ? (
              <span
                className="text-[11px] text-ink-muted/50 select-none font-mono"
                aria-hidden="true"
              >
                →
              </span>
            ) : null}
            <button
              type="button"
              onClick={() => {
                onSelect(stage.name);
              }}
              aria-current={isSelected ? "step" : undefined}
              aria-expanded={isSelected}
              title={`${STAGE_LABEL[stage.name]} · ${STATE_LABEL[stage.state]}${
                stage.elapsed === undefined ? "" : ` · 已用 ${stage.elapsed}`
              }`}
              className={`flex h-6.5 items-center gap-1.5 rounded-md px-2 text-label font-medium tint transition-all ${
                isSelected
                  ? "bg-accent-soft text-accent-strong border border-accent/30 shadow-xs font-semibold"
                  : isRunning
                    ? "bg-accent-soft/50 text-accent-strong border border-accent/25 animate-pulse"
                    : "bg-surface/80 text-ink-secondary border border-border/40 hover:bg-surface-hover hover:text-ink hover:border-border"
              }`}
            >
              <NodeGlyph state={stage.state} progress={stage.progress ?? 0} size={13} />
              <span>{STAGE_LABEL[stage.name]}</span>
              <span className="tabular-nums text-ink-muted text-[11px]">{stageSummary(stage)}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

export interface StageDetailProps {
  readonly stage: Stage;
  /** 当前阶段关联的最新任务数据（未入队时为 null）。 */
  readonly job: IngestionJob | null;
  /** 解析阶段产物元数据（仅解析阶段成功后有效）。 */
  readonly artifact: ParseArtifact | null;
}

/** 单行字段名与属性值展示项。 */
function Fact({ label, value }: { readonly label: string; readonly value: ReactNode }): ReactNode {
  return (
    <div className="flex gap-2">
      <dt className="w-24 shrink-0 text-label text-ink-secondary">{label}</dt>
      <dd className="min-w-0 text-label break-words text-ink">{value}</dd>
    </div>
  );
}

function ParseArtifactFacts({ artifact }: { readonly artifact: ParseArtifact }): ReactNode {
  return (
    <dl className="flex flex-col gap-1">
      <Fact label="解析器" value={`${artifact.parserName} ${artifact.parserVersion}`} />
      <Fact
        label="页数"
        value={artifact.pageCount === null ? "—（没有页码）" : String(artifact.pageCount)}
      />
      <Fact
        label="规范化 Markdown"
        value={`${formatBytes(artifact.sizeBytes)} · 校验和 ${shortId(artifact.checksum)}`}
      />
      <Fact
        label="解析警告"
        value={artifact.warnings.length === 0 ? "无" : artifact.warnings.join("；")}
      />
    </dl>
  );
}

/** 单个流水线阶段展开后的执行详情与异常信息展示面板。 */
export function StageDetailPanel({ stage, job, artifact }: StageDetailProps): ReactNode {
  return (
    <div className="flex flex-col gap-3 rounded-md bg-surface p-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <h4 className="text-label font-medium text-ink">
          {STAGE_LABEL[stage.name]} · {STATE_LABEL[stage.state]}
        </h4>
        {stage.meta === undefined ? null : (
          <span className="text-label tabular-nums text-ink-secondary">{stage.meta}</span>
        )}
        {job === null ? null : (
          <span className="text-label tabular-nums text-ink-secondary">
            修订 {String(job.revision)} · 尝试 {String(job.attempt)}
          </span>
        )}
      </div>

      {stage.state === "failed" || stage.state === "retry" ? (
        <p className="flex items-center gap-2 text-label text-error-ink">
          <IconError size={14} />
          该阶段没有成功完成，可在版本行选择「重新解析」重试这一阶段。
        </p>
      ) : null}

      {job === null ? (
        <p className="text-label text-ink-secondary">
          队列还没有把这一阶段排给这个版本，所以没有任务行可读。
        </p>
      ) : (
        <dl className="flex flex-col gap-1">
          <Fact label="任务状态" value={jobStatusLabel(job.status)} />
          <Fact label="开始" value={formatTimestamp(job.startedAt)} />
          <Fact label="结束" value={formatTimestamp(job.finishedAt)} />
          <Fact
            label="已用"
            value={
              job.startedAt === null
                ? "尚未开始"
                : job.finishedAt === null
                  ? "进行中，结束时间尚未写入"
                  : formatSpan(job.startedAt, job.finishedAt, 0)
            }
          />
          <Fact label="任务号" value={<span className="font-mono">{shortId(job.id)}</span>} />
        </dl>
      )}

      {job !== null && (job.errorClass !== null || job.errorMessage !== null) ? (
        <div className="rounded-sm border border-border bg-canvas p-2">
          <p className="font-mono text-quote text-error-ink">{job.errorClass ?? "—"}</p>
          <p className="mt-1 text-dense break-words text-ink-secondary">{job.errorMessage ?? ""}</p>
        </div>
      ) : null}

      {stage.name === "parse" ? (
        artifact === null ? (
          <p className="text-label text-ink-secondary">
            这个版本还没有一次成功的解析：产物摘要（解析器、页区间、警告、Markdown
            校验和）要在解析成功后 才有。
          </p>
        ) : (
          <ParseArtifactFacts artifact={artifact} />
        )
      ) : null}

      {stage.name === "chunk" ? (
        <p className="text-label text-ink-secondary">
          分块预览需要按子块读取分块正文的接口；契约目前只发布任务状态，因此这里只报告这一阶段实际跑了什么。
        </p>
      ) : null}
      {stage.name === "embed" || stage.name === "index" ? (
        <p className="text-label text-ink-secondary">
          向量与点位的数量属于索引统计，契约没有按版本发布这一计数；这里不猜测它。
        </p>
      ) : null}
    </div>
  );
}
