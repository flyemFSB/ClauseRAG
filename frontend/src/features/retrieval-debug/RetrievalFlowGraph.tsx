/**
 * 双通道召回与证据门控管线流向图（Parallel Retrieval Flow Diagram）。
 *
 * 以空间拓扑取代密集数字表格，直观呈现 Dense/Keyword 双通道并发召回、
 * RRF 融合排序、BGE 重排打分以及证据门控裁决的完整数据流向。
 */

import { type ReactNode } from "react";
import { IconActivity, IconClose, IconShieldAlert, IconShieldCheck } from "../../components/icons";
import { formatMillis, shortId } from "../../lib/format";
import type { RetrievalReport } from "./api";

export interface RetrievalFlowGraphProps {
  readonly report: RetrievalReport;
}

export function RetrievalFlowGraph({ report }: RetrievalFlowGraphProps): ReactNode {
  const denseChannel = report.channels.find((c) => c.channel === "dense");
  const keywordChannel = report.channels.find((c) => c.channel === "keyword");
  const acceptedSet = new Set(report.evidence.accepted);

  const isGateSufficient = report.evidence.status === "sufficient";
  const isGateDegraded = report.evidence.status === "degraded";
  const channelLatency = Math.max(denseChannel?.latencyMs ?? 0, keywordChannel?.latencyMs ?? 0);

  return (
    <section
      className="overflow-hidden rounded-lg border border-border bg-canvas shadow-tactile"
      aria-label="双通道召回管线流向图"
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-divider bg-surface/50 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded bg-accent-soft text-accent-strong">
            <IconActivity size={13} />
          </span>
          <h2 className="text-dense font-semibold text-ink">双通道混合召回与门控流向拓扑</h2>
        </div>
        <div className="flex items-center gap-2 text-label tabular-nums text-ink-secondary">
          <span>召回耗时: {formatMillis(channelLatency)}</span>
          <span className="text-divider">|</span>
          <span>上下文: {report.contextTokens} Tokens</span>
        </div>
      </header>

      <div className="p-4 sm:p-5">
        <div className="grid gap-4 lg:grid-cols-4">
          {/* 阶段 1：双通道召回 */}
          <div className="flex flex-col gap-2.5 rounded-lg border border-border/80 bg-surface/30 p-3.5">
            <div className="flex items-center justify-between border-b border-divider/60 pb-2">
              <span className="text-label font-semibold text-ink">1. 双通道并发召回</span>
              <span className="font-mono text-[10px] text-ink-muted">Channel Recall</span>
            </div>

            {/* Dense 通道卡片 */}
            <div className="rounded-md border border-border bg-canvas p-2.5">
              <div className="flex items-center justify-between text-label">
                <span className="font-medium text-ink">Dense (BGE-M3 向量)</span>
                <span className="font-mono tabular-nums text-ink-secondary">
                  {denseChannel ? formatMillis(denseChannel.latencyMs) : "—"}
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px] text-ink-muted">
                <span>命中: {String(denseChannel?.hits.length ?? 0)} 条</span>
                <span className="font-mono text-accent-strong">
                  Top 1: {denseChannel?.hits[0]?.rawScore?.toFixed(3) ?? "—"}
                </span>
              </div>
            </div>

            {/* Keyword 通道卡片 */}
            <div className="rounded-md border border-border bg-canvas p-2.5">
              <div className="flex items-center justify-between text-label">
                <span className="font-medium text-ink">Keyword (BM25 词项)</span>
                <span className="font-mono tabular-nums text-ink-secondary">
                  {keywordChannel ? formatMillis(keywordChannel.latencyMs) : "—"}
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px] text-ink-muted">
                <span>命中: {String(keywordChannel?.hits.length ?? 0)} 条</span>
                <span className="font-mono text-accent-strong">
                  Top 1: {keywordChannel?.hits[0]?.rawScore?.toFixed(2) ?? "—"}
                </span>
              </div>
            </div>
          </div>

          {/* 阶段 2：应用层 RRF 融合 */}
          <div className="flex flex-col gap-2.5 rounded-lg border border-border/80 bg-surface/30 p-3.5">
            <div className="flex items-center justify-between border-b border-divider/60 pb-2">
              <span className="text-label font-semibold text-ink">2. 应用层 RRF 融合</span>
              <span className="font-mono text-[10px] text-ink-muted">k = 60</span>
            </div>

            <div className="flex min-h-0 flex-1 flex-col justify-between rounded-md border border-border bg-canvas p-2.5">
              <div>
                <p className="text-label text-ink-secondary leading-snug">
                  统一对齐异构分数，倒数加权生成全局融合候选序列。
                </p>
                <div className="mt-3 flex flex-col gap-1.5">
                  {report.fused.slice(0, 3).map((item) => (
                    <div
                      key={item.childId}
                      className="flex items-center justify-between rounded bg-surface/60 px-2 py-1 font-mono text-[11px]"
                    >
                      <span className="text-ink">
                        #{item.ordinal} {shortId(item.childId)}
                      </span>
                      <span className="text-ink-secondary">{item.rrfScore.toFixed(4)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-2 border-t border-divider pt-2 text-[11px] text-ink-muted">
                共聚合 {String(report.fused.length)} 个候选切片
              </div>
            </div>
          </div>

          {/* 阶段 3：精排评分 */}
          <div className="flex flex-col gap-2.5 rounded-lg border border-border/80 bg-surface/30 p-3.5">
            <div className="flex items-center justify-between border-b border-divider/60 pb-2">
              <span className="text-label font-semibold text-ink">3. BGE-Reranker 精排</span>
              <span className="font-mono text-[10px] text-ink-muted">Cross-Encoder</span>
            </div>

            <div className="flex min-h-0 flex-1 flex-col justify-between rounded-md border border-border bg-canvas p-2.5">
              <div>
                <div className="flex items-center justify-between text-label">
                  <span className="font-medium text-ink">打分模型</span>
                  <span className="font-mono text-[11px] text-ink-secondary">
                    {report.rerank.model ?? "内置重排"}
                  </span>
                </div>
                <div className="mt-3 flex flex-col gap-1.5">
                  {report.reranked.slice(0, 3).map((item, idx) => (
                    <div
                      key={item.childId}
                      className="flex items-center justify-between rounded bg-surface/60 px-2 py-1 font-mono text-[11px]"
                    >
                      <span className="text-ink font-semibold">
                        #{idx + 1} {shortId(item.childId)}
                      </span>
                      <span className="text-accent-strong">
                        {item.rerankScore?.toFixed(4) ?? "—"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-2 border-t border-divider pt-2 text-[11px] text-ink-muted">
                完成 {String(report.rerank.scored)} 条候选精排评分
              </div>
            </div>
          </div>

          {/* 阶段 4：证据门控裁决 */}
          <div className="flex flex-col gap-2.5 rounded-lg border border-border/80 bg-surface/30 p-3.5">
            <div className="flex items-center justify-between border-b border-divider/60 pb-2">
              <span className="text-label font-semibold text-ink">4. 证据门控裁决</span>
              <span className="font-mono text-[10px] text-ink-muted">Evidence Gate</span>
            </div>

            <div
              className={`flex min-h-0 flex-1 flex-col justify-between rounded-md border p-2.5 ${
                isGateSufficient
                  ? "border-success/30 bg-success/5"
                  : isGateDegraded
                    ? "border-warning/30 bg-warning-soft/30"
                    : "border-border bg-canvas"
              }`}
            >
              <div>
                <div className="flex items-center gap-1.5">
                  {isGateSufficient ? (
                    <IconShieldCheck size={16} className="text-success-ink" />
                  ) : isGateDegraded ? (
                    <IconShieldAlert size={16} className="text-warning-ink" />
                  ) : (
                    <IconClose size={16} className="text-error-ink" />
                  )}
                  <span
                    className={`text-dense font-semibold ${
                      isGateSufficient
                        ? "text-success-ink"
                        : isGateDegraded
                          ? "text-warning-ink"
                          : "text-ink"
                    }`}
                  >
                    {isGateSufficient
                      ? "门控通过 (Sufficient)"
                      : isGateDegraded
                        ? "证据降级 (Degraded)"
                        : "依据门控弃答 (Abstained)"}
                  </span>
                </div>

                <p className="mt-2 text-label text-ink-secondary leading-snug">
                  {report.evidence.reason}
                </p>
              </div>

              <div className="mt-3 border-t border-divider/60 pt-2 flex items-center justify-between text-[11px] font-mono">
                <span className="text-ink-secondary">接受候选:</span>
                <span className="font-bold text-ink">{String(acceptedSet.size)} 条注入上下文</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
