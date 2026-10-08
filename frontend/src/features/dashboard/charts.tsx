/**
 * 控制台资产看板纯 SVG 图表组件。
 *
 * 包含置信度仪表盘（GaugeArc）、采纳率进度条（MeterBar）、合同类型分布环形图（DonutChart）与吞吐柱状/折线图（ThroughputChart）。
 */

import { type ReactNode } from "react";
import { formatCount, type ContractTypeShare } from "./analytics";
import type { DayThroughput } from "./api";

export function GaugeArc({
  value,
  className,
}: {
  /** 取值区间 0–1。 */
  readonly value: number;
  readonly className?: string;
}): ReactNode {
  const percent = Math.max(0, Math.min(1, value)) * 100;
  return (
    <svg viewBox="0 0 120 66" className={className} aria-hidden="true">
      <path
        d="M10 60a50 50 0 0 1 100 0"
        fill="none"
        stroke="var(--color-surface-strong)"
        strokeWidth={8}
        strokeLinecap="round"
      />
      <path
        d="M10 60a50 50 0 0 1 100 0"
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth={8}
        strokeLinecap="round"
        pathLength={100}
        strokeDasharray={`${String(percent)} 100`}
      />
    </svg>
  );
}

export function MeterBar({ value }: { readonly value: number }): ReactNode {
  const percent = Math.max(0, Math.min(1, value)) * 100;
  return (
    <span className="block h-1 w-full overflow-hidden rounded-[var(--radius-pill)] bg-surface-strong">
      <span
        className="block h-full rounded-[var(--radius-pill)] bg-accent"
        style={{ width: `${String(percent)}%` }}
      />
    </span>
  );
}

/** 环形图扇区透明度阶梯配置。 */
const SLICE_OPACITY = [1, 0.62, 0.38, 0.2] as const;

export function DonutChart({
  slices,
  centerLabel,
  centerCaption,
}: {
  readonly slices: readonly ContractTypeShare[];
  readonly centerLabel: string;
  readonly centerCaption: string;
}): ReactNode {
  // 计算各扇区起始偏移量与对应比例
  const segments = slices.map((slice, index) => ({
    slice,
    opacity: SLICE_OPACITY[index] ?? 0.2,
    percent: slice.share * 100,
    offset: slices.slice(0, index).reduce((sum, previous) => sum + previous.share * 100, 0),
  }));

  return (
    <svg viewBox="0 0 140 140" className="h-[140px] w-[140px] shrink-0" aria-hidden="true">
      <g transform="rotate(-90 70 70)">
        <circle cx={70} cy={70} r={56} fill="none" stroke="var(--color-surface)" strokeWidth={16} />
        {segments.map((segment) => (
          <circle
            key={segment.slice.label}
            cx={70}
            cy={70}
            r={56}
            fill="none"
            stroke="var(--color-accent)"
            strokeOpacity={segment.opacity}
            strokeWidth={16}
            pathLength={100}
            strokeDasharray={`${String(segment.percent)} ${String(100 - segment.percent)}`}
            strokeDashoffset={-segment.offset}
          />
        ))}
      </g>
      <text
        x={70}
        y={68}
        textAnchor="middle"
        className="fill-[var(--color-ink)] text-[20px] font-semibold tabular-nums"
      >
        {centerLabel}
      </text>
      <text
        x={70}
        y={86}
        textAnchor="middle"
        className="fill-[var(--color-ink-secondary)] text-[11px]"
      >
        {centerCaption}
      </text>
    </svg>
  );
}

const WIDTH = 340;
const HEIGHT = 156;
const LEFT = 38;
const RIGHT = 12;
const TOP = 10;
const BOTTOM = 32;

export function ThroughputChart({ days }: { readonly days: readonly DayThroughput[] }): ReactNode {
  // 根据实际数据动态计算 Y 轴标尺上限
  const maxStages = Math.max(4, ...days.map((day) => day.stages));
  const plotWidth = WIDTH - LEFT - RIGHT;
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const step = plotWidth / days.length;
  const barWidth = Math.min(16, step / 3);
  const yOfStages = (value: number): number => TOP + plotHeight - (value / maxStages) * plotHeight;
  const gridlines = [0, 0.25, 0.5, 0.75, 1].map((fraction) => fraction * maxStages);

  return (
    <svg viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`} className="w-full" aria-hidden="true">
      {gridlines.map((value) => {
        const y = yOfStages(value);
        return (
          <g key={value}>
            <line
              x1={LEFT}
              x2={WIDTH - RIGHT}
              y1={y}
              y2={y}
              stroke="var(--color-divider)"
              strokeWidth={1}
            />
            <text
              x={LEFT - 6}
              y={y + 3}
              textAnchor="end"
              className="fill-[var(--color-ink-secondary)] text-[10px] tabular-nums"
            >
              {formatCount(value)}
            </text>
          </g>
        );
      })}

      {days.map((day, index) => {
        const center = LEFT + step * index + step / 2;
        return (
          <g key={day.day}>
            {day.stages === 0 ? null : (
              <rect
                x={center - barWidth / 2}
                y={yOfStages(day.stages)}
                width={barWidth}
                height={TOP + plotHeight - yOfStages(day.stages)}
                rx={2}
                fill="var(--color-accent)"
                opacity={0.85}
              />
            )}
            <text
              x={center}
              y={HEIGHT - 18}
              textAnchor="middle"
              className="fill-[var(--color-ink-secondary)] text-[10px]"
            >
              {day.day}
            </text>
            <text
              x={center}
              y={HEIGHT - 5}
              textAnchor="middle"
              className="fill-[var(--color-ink-muted)] text-[10px] tabular-nums"
            >
              {day.stages} 阶段
            </text>
          </g>
        );
      })}
    </svg>
  );
}
