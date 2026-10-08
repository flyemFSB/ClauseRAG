/**
 * 会话单轮审查工件展示组件（审查指令卡片在右、AI审计报告在左、证据链仪表与操作栏）。
 */

import { type ReactNode } from "react";
import { motion } from "framer-motion";
import {
  IconError,
  IconFileSearch,
  IconInfo,
  IconReplay,
  IconShield,
  IconShieldAlert,
  IconShieldCheck,
  Spinner,
} from "../../components/icons";
import type { RunState } from "./run";

/** 审查指令卡片（用户消息在右侧布局）。 */
export function QuestionBubble({ question }: { readonly question: string }): ReactNode {
  return (
    <div className="flex justify-end">
      <div className="max-w-[88%] sm:max-w-[80%] rounded-lg border border-border/80 bg-surface px-4 py-3 shadow-sm transition-colors hover:border-border">
        <div className="flex items-center gap-1.5 border-b border-divider/60 pb-1.5 text-ink-secondary">
          <span className="flex h-4 w-4 items-center justify-center rounded bg-accent-soft text-accent-strong">
            <IconFileSearch size={11} />
          </span>
          <span className="text-[11px] font-medium text-ink">审查指令</span>
        </div>
        <p className="mt-2 text-body font-medium leading-relaxed text-ink select-text whitespace-pre-wrap">
          {question}
        </p>
      </div>
    </div>
  );
}

/** 证据链置信度与管线状态指示仪表组件。 */
export function StatusLine({ state }: { readonly state: RunState }): ReactNode {
  if (state.status === "streaming") {
    return (
      <div
        className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-accent/20 bg-accent-soft/40 px-3.5 py-2.5 text-label"
        aria-live="polite"
      >
        <div className="flex items-center gap-2 text-accent-strong">
          <Spinner />
          <span className="font-medium">条款审查分析进行中…</span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[11px] text-ink-secondary">
          <span>双通道召回</span>
          <span>→</span>
          <span>RRF 重排</span>
          <span>→</span>
          <span>原文防伪核验</span>
        </div>
      </div>
    );
  }

  if (state.status === "cancelled") {
    return (
      <div className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-label text-ink-secondary">
        <IconInfo size={15} />
        <span>已中止生成 · 以下为当前截断的已校验分析结果</span>
      </div>
    );
  }

  if (state.status === "failed") {
    return (
      <div
        className="flex items-center gap-2 rounded-md border border-error/20 bg-error/10 px-3.5 py-2 text-label text-error-ink"
        role="alert"
      >
        <IconError size={15} />
        <span>
          <span className="font-mono font-medium">{state.errorClass}</span> · {state.errorMessage}
        </span>
      </div>
    );
  }

  switch (state.evidenceStatus) {
    case "sufficient":
      return (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-success/20 bg-success/5 px-3.5 py-2 text-label">
          <div className="flex items-center gap-2 text-success-ink">
            <IconShieldCheck size={16} />
            <span className="font-medium">证据链闭环 (Sufficient Evidence)</span>
          </div>
          <div className="flex items-center gap-3 font-mono text-[11px] tabular-nums text-ink-secondary">
            <span>{state.citations.length} 条已核验条款引用</span>
            <span className="text-divider">|</span>
            <span>{state.retrievalRounds} 轮检索迭代</span>
            <span className="text-divider">|</span>
            <span className="text-success-ink font-semibold">100% 行级溯源</span>
          </div>
        </div>
      );
    case "degraded":
      return (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-warning/30 bg-warning-soft/40 px-3.5 py-2 text-label">
          <div className="flex items-center gap-2 text-warning-ink">
            <IconShieldAlert size={16} />
            <span className="font-medium">证据部分降级 (Degraded Evidence)</span>
          </div>
          <div className="flex items-center gap-2 font-mono text-[11px] tabular-nums text-ink-secondary">
            <span>{state.citations.length} 条可用引用 · 部分合同版本未覆盖</span>
          </div>
        </div>
      );
    case "insufficient":
      return (
        <div className="flex items-start gap-2.5 rounded-md border border-border bg-surface/70 p-3 text-label text-ink-secondary">
          <IconInfo size={16} />
          <div className="flex flex-col gap-0.5">
            <span className="font-medium text-ink">依据合规门控主动弃答 (Abstained)</span>
            <p className="text-dense text-ink-secondary">
              本次召回证据未达到合规决策门控阈值。平台严格执行防伪与免责协议，主动放弃生成推测性法律结论。
            </p>
          </div>
        </div>
      );
    default:
      return (
        <div className="flex items-center gap-2 rounded-md bg-surface px-3 py-2 text-label text-ink-secondary">
          <IconShield size={15} />
          <span>
            本次未执行外部向量检索（
            {state.intent === "direct_response" ? "直接回答" : String(state.intent)}）
          </span>
        </div>
      );
  }
}

function MessageActions({
  state,
  onReplay,
  onCancel,
}: {
  readonly state: RunState;
  readonly onReplay: () => void;
  readonly onCancel: () => void;
}): ReactNode {
  if (state.status === "streaming") {
    return (
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="flex h-7 items-center gap-1.5 rounded-md border border-border/80 px-2.5 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink active:scale-95"
        >
          中止审查
        </button>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={onReplay}
        className="flex h-7 items-center gap-1.5 rounded-md border border-border/80 px-2.5 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink active:scale-95"
      >
        <IconReplay size={13} />
        重新审查
      </button>
    </div>
  );
}

export interface ThreadProps {
  readonly state: RunState;
  readonly question: string;
  readonly answer: ReactNode;
  readonly onReplay: () => void;
  readonly onCancel: () => void;
  readonly className?: string;
}

/** 审查轮次工件容器：用户审查指令在右，AI条款审查报告在左。 */
export function Thread({
  state,
  question,
  answer,
  onReplay,
  onCancel,
  className,
}: ThreadProps): ReactNode {
  return (
    <article className={`flex flex-col gap-5 ${className ?? ""}`}>
      {/* 用户消息在右 */}
      <QuestionBubble question={question} />

      {/* AI消息在左 */}
      <div className="flex justify-start">
        <div className="w-full max-w-[95%] sm:max-w-[90%] lg:max-w-[88%] flex flex-col gap-3 rounded-lg border border-border bg-canvas p-5 shadow-tactile">
          <header className="flex items-center justify-between border-b border-divider pb-3">
            <div className="flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded bg-ink text-canvas font-mono text-[10px] font-bold">
                §
              </span>
              <h3 className="text-dense font-semibold text-ink">条款审查报告与风险洞察</h3>
            </div>
            <MessageActions state={state} onReplay={onReplay} onCancel={onCancel} />
          </header>

          {/* 回答生成流式渲染容器 */}
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="min-w-0"
          >
            {answer}
          </motion.div>

          <footer className="mt-2 border-t border-divider pt-3">
            <StatusLine state={state} />
          </footer>
        </div>
      </div>
    </article>
  );
}
