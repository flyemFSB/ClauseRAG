/**
 * 检索调试页面
 *
 * 发起单次真实检索诊断，完整展示两通道召回（Dense / Keyword）、
 * RRF 融合排序、重排评分、证据门控判定及组装的上下文来源。
 */

import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { EmptyState, FailureNotice } from "../../components/failure-notice";
import { StatusMark } from "../../components/state-mark";
import { SkeletonRows } from "../../components/skeleton";
import { ApiError } from "../../lib/api";
import { createGeneration } from "../../lib/generation";
import { formatMillis, shortId } from "../../lib/format";
import { KnowledgeBaseSelect } from "../knowledge-bases/KnowledgeBaseSelect";
import { useKnowledgeBases } from "../knowledge-bases/api";
import { useDocumentSummaries } from "../documents/api";
import { intentLabel, useRetrievalDebug, type RetrievalReport } from "./api";
import { RetrievalFlowGraph } from "./RetrievalFlowGraph";
import { Channels, ContextSources, Fused, Gate } from "./CandidateTables";

export function RetrievalDebugPage(): ReactNode {
  const knowledgeBases = useKnowledgeBases();
  const [chosen, setChosen] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [report, setReport] = useState<RetrievalReport | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [cancelled, setCancelled] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const [generation] = useState(createGeneration);
  const startedAt = useRef<number>(0);
  const run = useRetrievalDebug();

  /** 中止在途请求并推进代次，保证响应不写入过时轮次 */
  const abandonRound = useCallback((): number => {
    controller.current?.abort();
    controller.current = null;
    return generation.begin();
  }, [generation]);

  // 组件卸载时中止在途请求
  useEffect(
    () => () => {
      abandonRound();
    },
    [abandonRound],
  );

  // 默认选中第一个知识库
  const knowledgeBaseId = chosen ?? knowledgeBases.data?.at(0)?.id ?? null;
  const documents = useDocumentSummaries(knowledgeBaseId);

  // 记录请求持续耗时
  useEffect(() => {
    if (!run.isPending) {
      return undefined;
    }
    startedAt.current = Date.now();
    const ticker = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt.current);
    }, 1000);
    return () => {
      window.clearInterval(ticker);
    };
  }, [run.isPending]);

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (knowledgeBaseId === null || question.trim() === "") {
      return;
    }
    setFailure(null);
    setCancelled(false);
    // 作废并中止上一轮请求，生成新的代次凭据
    const attempt = abandonRound();
    const current = new AbortController();
    controller.current = current;
    run
      .mutateAsync({ knowledgeBaseId, query: question.trim(), signal: current.signal })
      .then((result) => {
        if (!generation.isCurrent(attempt)) {
          return;
        }
        setReport(result);
      })
      .catch((error: unknown) => {
        if (!generation.isCurrent(attempt)) {
          return;
        }
        setReport(null);
        if (error instanceof ApiError && error.kind === "aborted") {
          setCancelled(true);
          return;
        }
        setFailure(error instanceof Error ? error.message : "检索请求失败");
      });
  }

  /** 候选命中项对应的文档标题映射（仅限最新版本） */
  const titles = new Map<string, string>();
  for (const document of documents.data ?? []) {
    if (document.latestVersion !== null) {
      titles.set(document.latestVersion.id, document.title);
    }
  }

  const canRun = knowledgeBaseId !== null && question.trim() !== "" && !run.isPending;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-5 px-4 py-4 sm:px-5 sm:py-5">
        <header>
          <h1 className="text-title font-semibold text-ink">检索诊断与召回分析</h1>
          <p className="mt-1 max-w-[92ch] text-body text-ink-secondary">
            对选定商业合同知识库发起真实检索测试：透视 BGE-M3 语义向量与 pg_trgm 关键词双通道召回、
            应用层 RRF 融合加权、Cross-Encoder 精排以及证据门控（Evidence Gate）准入裁决全流程。
          </p>
        </header>

        <form
          className="flex flex-col gap-3 rounded-lg border border-border bg-canvas p-4 md:flex-row md:items-center shadow-tactile"
          onSubmit={submit}
        >
          <KnowledgeBaseSelect
            knowledgeBases={knowledgeBases.data ?? []}
            value={knowledgeBaseId}
            onChange={(next) => {
              // 切换知识库重置状态并中止在途请求
              abandonRound();
              setChosen(next);
              setReport(null);
              setFailure(null);
              setCancelled(false);
            }}
          />
          <input
            aria-label="检索问题"
            value={question}
            onChange={(event) => {
              setQuestion(event.target.value);
            }}
            placeholder="例如：审查主服务协议第8条的责任上限与间接损失免责范围…"
            className="h-8 min-w-0 flex-1 rounded-md border border-control-border bg-canvas px-2.5 text-body text-ink tint hover:border-ink-muted"
          />
          {run.isPending ? (
            <button
              type="button"
              onClick={() => {
                controller.current?.abort();
              }}
              className="flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-md bg-surface px-3.5 text-label font-medium text-ink tint hover:bg-surface-hover active:scale-95"
            >
              停止
            </button>
          ) : (
            <button
              type="submit"
              disabled={!canRun}
              className="flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-md bg-accent-strong px-3.5 text-label font-medium text-canvas tint hover:bg-accent disabled:opacity-50 active:scale-95"
            >
              运行检索
            </button>
          )}
        </form>

        {knowledgeBases.isError ? (
          <FailureNotice
            title="读不到知识库列表"
            detail={knowledgeBases.error.message}
            action={
              <button
                type="button"
                onClick={() => {
                  void knowledgeBases.refetch();
                }}
                className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
              >
                重试
              </button>
            }
          />
        ) : null}

        {run.isPending ? (
          <section
            className="rounded-lg border border-border bg-canvas p-4 shadow-tactile"
            aria-label="检索结果"
          >
            <div className="flex items-center gap-2 pb-3">
              <StatusMark tone="running" label="正在双通道检索" />
              <span className="text-dense tabular-nums text-ink-secondary">
                已用 {formatMillis(elapsedMs)}，单轮上限 120 秒
              </span>
            </div>
            <SkeletonRows rows={4} rowHeight="h-8" />
          </section>
        ) : null}

        {cancelled ? (
          <p className="text-dense text-ink-secondary">已取消。这次请求被中止，未写入任何状态。</p>
        ) : null}

        {failure === null ? null : (
          <FailureNotice
            title="检索请求失败"
            detail={failure}
            action={
              <button
                type="button"
                onClick={() => {
                  setFailure(null);
                }}
                className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
              >
                知道了
              </button>
            }
          />
        )}

        {report === null && !run.isPending && failure === null && !cancelled ? (
          <EmptyState title="未运行检索诊断">
            选择合同知识库并输入条款核查语句，发起双通道混合检索与重排。系统将直观展示各通道召回拓扑、融合位次跳跃与证据门控过滤线。
          </EmptyState>
        ) : null}

        {report === null ? null : (
          <>
            <section
              className="rounded-lg border border-border bg-canvas shadow-tactile"
              aria-label="本次请求"
            >
              <dl className="flex flex-wrap items-baseline gap-x-8 gap-y-3 px-4 py-4">
                <Fact label="意图分类" value={`${intentLabel(report.intent)} · ${report.intent}`} />
                <Fact
                  label="检索知识库"
                  value={knowledgeBaseName(knowledgeBases.data, knowledgeBaseId)}
                />
                <Fact label="改写后的检索式" value={`${String(report.queries.length)} 条`} />
              </dl>
              {report.queries.length === 0 ? null : (
                <ul className="flex flex-col gap-1 border-t border-divider px-4 py-3 bg-surface/20">
                  {report.queries.map((rewritten, index) => (
                    <li key={`${rewritten}-${String(index)}`} className="text-dense text-ink">
                      <span className="mr-2 text-ink-muted tabular-nums font-mono">
                        {index + 1}.
                      </span>
                      {rewritten}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* 可视化管线流向图 */}
            <RetrievalFlowGraph report={report} />

            {/* 详细数据表格面板 */}
            <Channels report={report} titles={titles} />

            <Fused report={report} titles={titles} />

            <Gate report={report} />

            <ContextSources report={report} titles={titles} />
          </>
        )}
      </div>
    </div>
  );
}

function Fact({ label, value }: { readonly label: string; readonly value: string }): ReactNode {
  return (
    <div>
      <dt className="text-label font-medium text-ink-secondary">{label}</dt>
      <dd className="mt-0.5 text-dense font-semibold text-ink">{value}</dd>
    </div>
  );
}

function knowledgeBaseName(
  knowledgeBases: readonly { readonly id: string; readonly name: string }[] | undefined,
  id: string | null,
): string {
  if (id === null) {
    return "—";
  }
  return knowledgeBases?.find((entry) => entry.id === id)?.name ?? shortId(id);
}
