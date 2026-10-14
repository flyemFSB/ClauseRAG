/**
 * 检索调试候选表格与上下文详情模块（Channels / Fused / Gate / Context Panels）。
 */

import { Fragment, useState, type ReactNode } from "react";
import { Tabs } from "@base-ui/react/tabs";
import { StatusMark } from "../../components/state-mark";
import { formatMillis, shortId } from "../../lib/format";
import {
  channelLabel,
  channelStatusLabel,
  channelStatusTone,
  evidenceStatusLabel,
  evidenceStatusTone,
  rerankStatusLabel,
  rerankStatusTone,
  type Candidate,
  type ChannelReport,
  type RetrievalReport,
} from "./api";

const TH = "px-3 py-2 text-left text-label font-medium text-ink-secondary";
const TD = "px-3 py-2 align-top text-dense text-ink";
const ROW = "h-8 border-t border-divider hover:bg-surface";

/** 获取候选命中文档标题或版本标识 */
export function documentOf(versionId: string, titles: ReadonlyMap<string, string>): string {
  return titles.get(versionId) ?? `版本 ${shortId(versionId)}`;
}

export function location(source: { readonly lineStart: number; readonly lineEnd: number }): string {
  return `行 ${String(source.lineStart)}–${String(source.lineEnd)}`;
}

function formatRanks(candidate: Candidate): string {
  const entries = Object.entries(candidate.channelRanks);
  if (entries.length === 0) {
    return "—";
  }
  return entries.map(([channel, rank]) => `${channel} ${String(rank)}`).join(" · ");
}

/* --- 三通道召回面板 --- */

export function Channels({
  report,
  titles,
}: {
  readonly report: RetrievalReport;
  readonly titles: ReadonlyMap<string, string>;
}): ReactNode {
  const fusedIds = new Set(report.fused.map((candidate) => candidate.childId));
  const [channel, setChannel] = useState<string>(report.channels.at(0)?.channel ?? "dense");

  return (
    <section
      className="rounded-lg border border-border bg-canvas shadow-tactile"
      aria-label="召回通道"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 px-4 pt-4 pb-3">
        <h2 className="text-section font-semibold text-ink">召回通道明细</h2>
        <p className="text-label text-ink-secondary">
          各通道独立检索命中详情；高亮底色代表进入 RRF 融合范围
        </p>
      </header>

      <Tabs.Root
        value={channel}
        onValueChange={(next) => {
          setChannel(String(next));
        }}
      >
        <Tabs.List className="flex gap-1 border-b border-border px-4" aria-label="召回通道">
          {report.channels.map((entry) => (
            <Tabs.Tab
              key={entry.channel}
              value={entry.channel}
              className="-mb-px h-8 border-b-2 border-transparent px-2.5 text-label font-medium text-ink-secondary tint hover:text-ink data-[active]:border-accent data-[active]:text-ink"
            >
              {channelLabel(entry.channel)}
            </Tabs.Tab>
          ))}
        </Tabs.List>

        {report.channels.map((entry) => (
          <Tabs.Panel key={entry.channel} value={entry.channel} className="outline-none">
            <ChannelPanel channel={entry} fusedIds={fusedIds} titles={titles} />
          </Tabs.Panel>
        ))}
      </Tabs.Root>
    </section>
  );
}

function ChannelPanel({
  channel,
  fusedIds,
  titles,
}: {
  readonly channel: ChannelReport;
  readonly fusedIds: ReadonlySet<string>;
  readonly titles: ReadonlyMap<string, string>;
}): ReactNode {
  return (
    <div className="pt-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 pb-3">
        <StatusMark
          tone={channelStatusTone(channel.status)}
          label={channelStatusLabel(channel.status)}
          title={channel.status}
          variant="pill"
        />
        <span className="text-label tabular-nums text-ink-secondary">
          耗时 {formatMillis(channel.latencyMs)}
        </span>
        <span className="text-label tabular-nums text-ink-secondary">
          {String(channel.hits.length)} 条候选
        </span>
        {channel.errorType === null ? null : (
          <span className="font-mono text-quote text-ink-secondary">{channel.errorType}</span>
        )}
      </div>

      {channel.status === "failed" ? (
        <p className="px-4 pb-4 text-dense text-ink-secondary">
          这个通道没有答上来，因此它在这一轮里没有排名。其余通道与融合结果不受影响。
        </p>
      ) : null}

      {channel.status === "unavailable" ? (
        <p className="px-4 pb-4 text-dense text-ink-secondary">
          这个通道在本部署没有启用，所以它不是「没有命中」，而是根本没有参与这一轮。
        </p>
      ) : null}

      {channel.status === "ok" ? (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-surface">
                <th className={`${TH} w-14 text-right`}>排名</th>
                <th className={`${TH} w-28 text-right`}>原始分</th>
                <th className={TH}>child 后 8 位</th>
                <th className={TH}>所属文档</th>
              </tr>
            </thead>
            <tbody>
              {channel.hits.map((hit) => (
                <tr
                  key={hit.childId}
                  className={`${ROW} ${fusedIds.has(hit.childId) ? "bg-accent-soft/40" : ""}`}
                >
                  <td className={`${TD} text-right tabular-nums font-medium`}>{hit.rank}</td>
                  <td className={`${TD} text-right font-mono tabular-nums text-ink-secondary`}>
                    <div className="flex items-center justify-end gap-2">
                      <span>{hit.rawScore === null ? "—" : hit.rawScore.toFixed(4)}</span>
                      {hit.rawScore !== null ? (
                        <div className="h-1.5 w-10 overflow-hidden rounded-full bg-surface-hover">
                          <div
                            className="h-full rounded-full bg-accent"
                            style={{
                              width: `${String(
                                Math.min(
                                  100,
                                  Math.max(
                                    0,
                                    hit.rawScore > 1
                                      ? (hit.rawScore / 30) * 100
                                      : hit.rawScore * 100,
                                  ),
                                ),
                              )}%`,
                            }}
                          />
                        </div>
                      ) : null}
                    </div>
                  </td>
                  <td className={`${TD} font-mono text-quote`}>{shortId(hit.childId)}</td>
                  <td className={`${TD} truncate`}>{documentOf(hit.documentVersionId, titles)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

/* --- 融合与重排面板 --- */

export function Fused({
  report,
  titles,
}: {
  readonly report: RetrievalReport;
  readonly titles: ReadonlyMap<string, string>;
}): ReactNode {
  const accepted = new Set(report.evidence.accepted);
  const rerankedOrder = new Map<string, number>();
  report.reranked.forEach((candidate, index) => {
    rerankedOrder.set(candidate.childId, index + 1);
  });

  return (
    <section
      className="rounded-lg border border-border bg-canvas shadow-tactile"
      aria-label="融合与重排"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 px-4 pt-4 pb-3">
        <h2 className="text-section font-semibold text-ink">融合与重排结果</h2>
        <p className="max-w-[52ch] text-label text-ink-secondary">
          融合常量 k=60，结合多通道倒数排名加权；重排使用 Cross-Encoder 计算精准语义相关度。
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 pb-3">
        <StatusMark
          tone={rerankStatusTone(report.rerank.status)}
          label={rerankStatusLabel(report.rerank.status)}
          title={report.rerank.status}
          variant="pill"
        />
        <span className="font-mono text-quote text-ink-secondary">
          {report.rerank.model === null || report.rerank.model === "" ? "—" : report.rerank.model}
        </span>
        <span className="text-label tabular-nums text-ink-secondary">
          已打分 {String(report.rerank.scored)} 条
        </span>
        {report.rerank.reason === null ? null : (
          <span className="text-label text-ink-secondary">{report.rerank.reason}</span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-surface">
              <th className={`${TH} w-12 text-right`}>序</th>
              <th className={TH}>child 后 8 位</th>
              <th className={TH}>所属文档</th>
              <th className={`${TH} w-24 text-right`}>RRF</th>
              <th className={`${TH} w-24 text-right`}>重排分</th>
              <th className={TH}>通道排名</th>
              <th className={`${TH} w-20 text-right`}>重排后</th>
              <th className={`${TH} w-24`}>证据门控</th>
            </tr>
          </thead>
          <tbody>
            {report.fused.map((candidate, index) => {
              const kept = accepted.has(candidate.childId);
              const isLastKept =
                kept &&
                (index === report.fused.length - 1 ||
                  !accepted.has(report.fused[index + 1]?.childId));
              return (
                <Fragment key={candidate.childId}>
                  <tr className={`${ROW} ${kept ? "bg-accent-soft/40" : ""}`}>
                    <td className={`${TD} text-right tabular-nums font-mono`}>
                      {candidate.ordinal}
                    </td>
                    <td className={`${TD} font-mono text-quote`}>{shortId(candidate.childId)}</td>
                    <td className={`${TD} truncate`}>
                      {documentOf(candidate.documentVersionId, titles)}
                    </td>
                    <td className={`${TD} text-right font-mono tabular-nums font-medium`}>
                      {candidate.rrfScore.toFixed(4)}
                    </td>
                    <td className={`${TD} text-right font-mono tabular-nums text-ink-secondary`}>
                      {candidate.rerankScore === null ? "—" : candidate.rerankScore.toFixed(4)}
                    </td>
                    <td className={`${TD} text-ink-secondary text-[12px]`}>
                      {formatRanks(candidate)}
                    </td>
                    <td className={`${TD} text-right tabular-nums text-ink-secondary`}>
                      {(() => {
                        const rerankRank = rerankedOrder.get(candidate.childId);
                        if (rerankRank === undefined) {
                          return <span className="text-ink-muted text-[11px]">未获重排分值</span>;
                        }
                        const delta = candidate.ordinal - rerankRank;
                        return (
                          <div className="flex items-center justify-end gap-1.5 font-mono">
                            <span className="font-semibold text-ink">#{rerankRank}</span>
                            {delta > 0 ? (
                              <span
                                className="inline-flex items-center rounded-sm bg-success/15 px-1 font-mono text-[11px] font-semibold text-success-ink"
                                title={`重排上升 ${String(delta)} 位`}
                              >
                                ▲{delta}
                              </span>
                            ) : delta < 0 ? (
                              <span
                                className="inline-flex items-center rounded-sm bg-warning/15 px-1 font-mono text-[11px] font-semibold text-warning-ink"
                                title={`重排下降 ${String(Math.abs(delta))} 位`}
                              >
                                ▼{Math.abs(delta)}
                              </span>
                            ) : (
                              <span className="text-[11px] text-ink-muted font-mono">—</span>
                            )}
                          </div>
                        );
                      })()}
                    </td>
                    <td className={TD}>
                      <StatusMark
                        tone={kept ? "success" : "muted"}
                        label={kept ? "纳入上下文" : "门控过滤"}
                        title={kept ? "通过证据门控注入上下文" : "低于证据门控阈值，未纳入"}
                      />
                    </td>
                  </tr>
                  {isLastKept ? (
                    <tr className="border-y-2 border-dashed border-accent/40 bg-accent-soft/20 text-[11px]">
                      <td colSpan={8} className="px-3 py-1 text-accent-strong font-medium">
                        <span className="flex items-center gap-2">
                          <span className="h-1.5 w-1.5 rounded-full bg-accent-strong animate-pulse" />
                          <span>
                            ── 上方候选已通过证据门控（Evidence Gating Cutoff）· 组装注入 LLM
                            问答上下文 ──
                          </span>
                        </span>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {report.fused.length === 0 ? (
        <p className="px-4 py-4 text-dense text-ink-secondary">
          融合结果为空：本次没有任何候选进入融合，通常意味着两个通道都没有命中。
        </p>
      ) : null}
    </section>
  );
}

/* --- 证据门控面板 --- */

export function Gate({ report }: { readonly report: RetrievalReport }): ReactNode {
  const status = report.evidence.status;
  return (
    <section
      className="rounded-lg border border-border bg-canvas shadow-tactile"
      aria-label="证据门控"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 px-4 pt-4 pb-3">
        <h2 className="text-section font-semibold text-ink">证据门控判定</h2>
        <span className="text-label tabular-nums text-ink-secondary">
          接受 {String(report.evidence.accepted.length)} 条候选
        </span>
      </header>
      <div className="flex flex-col gap-2 px-4 pb-4">
        <StatusMark
          tone={evidenceStatusTone(status)}
          label={evidenceStatusLabel(status)}
          title={status}
          variant="pill"
        />
        <p className="font-mono text-quote break-words text-ink-secondary">
          {report.evidence.reason}
        </p>
        {status === "insufficient" ? (
          <p className="max-w-[92ch] text-dense text-ink">
            这次证据不足以作答，所以在对话中系统将主动依约弃答，杜绝臆测。可选方案：补充相关商业合同文档或重构检索范围。
          </p>
        ) : null}
        {status === "degraded" ? (
          <p className="max-w-[92ch] text-dense text-ink">
            这次重排服务不可用：候选未经条款相关性核验，无法判定证据质量，所以系统在对话中主动弃答，不生成审查结论。可选方案：稍后重试。
          </p>
        ) : null}
      </div>
    </section>
  );
}

/* --- 上下文来源面板 --- */

export function ContextSources({
  report,
  titles,
}: {
  readonly report: RetrievalReport;
  readonly titles: ReadonlyMap<string, string>;
}): ReactNode {
  return (
    <section
      className="rounded-lg border border-border bg-canvas shadow-tactile"
      aria-label="上下文来源"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 px-4 pt-4 pb-3">
        <h2 className="text-section font-semibold text-ink">上下文来源切片</h2>
        <span className="text-label tabular-nums text-ink-secondary">
          {String(report.contextTokens)} context tokens
        </span>
      </header>

      {report.contextSources.length === 0 ? (
        <p className="px-4 pb-4 text-dense text-ink-secondary">
          没有上下文来源：门控未接受任何候选，因此没有交付生成步骤的条文。
        </p>
      ) : (
        <ul className="divide-y divide-divider border-t border-border">
          {report.contextSources.map((source) => (
            <li key={source.citationId} className="flex flex-col gap-2 px-4 py-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <span className="inline-flex h-5 items-center rounded-sm bg-accent-soft px-1.5 font-mono text-label font-medium text-accent-strong">
                  {source.citationId}
                </span>
                <span className="text-dense font-medium text-ink">
                  {titles.get(source.documentVersionId) ?? source.documentName}
                </span>
                {source.headingPath.length === 0 ? null : (
                  <span className="text-label text-ink-secondary">
                    {source.headingPath.join(" / ")}
                  </span>
                )}
                <span className="text-label tabular-nums text-ink-secondary font-mono">
                  {location(source)}
                </span>
              </div>
              <p className="font-mono text-quote text-ink bg-surface/40 p-2.5 rounded border border-divider">
                {source.quote}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
