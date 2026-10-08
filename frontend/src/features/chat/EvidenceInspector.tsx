/**
 * 权威合同底稿溯源视口组件。
 *
 * 呈现引用来源文档信息、带行号槽位的权威原文摘录、以及父子切片树状拓扑图。
 */

import { useState, type ReactNode } from "react";
import {
  IconCheck,
  IconClose,
  IconCopy,
  IconDocument,
  IconListTree,
  IconShieldCheck,
} from "../../components/icons";
import type { CitationPayload } from "../../lib/sse";
import { locationLabel } from "./AnswerBody";

export interface EvidenceInspectorProps {
  readonly citation: CitationPayload;
  /** 当前引用在答案引用集合中的序号。 */
  readonly rank: number;
  readonly total: number;
  readonly onClose: () => void;
  readonly onCopy: (citation: CitationPayload) => void;
  readonly onOpenDocument: (citation: CitationPayload) => void;
}

export function EvidenceInspector({
  citation,
  rank,
  total,
  onClose,
  onCopy,
  onOpenDocument,
}: EvidenceInspectorProps): ReactNode {
  const [copied, setCopied] = useState(false);
  const [copiedMemo, setCopiedMemo] = useState(false);

  function handleCopy(): void {
    onCopy(citation);
    setCopied(true);
    window.setTimeout(() => {
      setCopied(false);
    }, 2000);
  }

  function handleCopyMemo(): void {
    const heading = citation.headingPath.length > 0 ? citation.headingPath.join(" > ") : "";
    const memo = `*${citation.documentName}${heading ? ` (${heading})` : ""}, ${locationLabel(citation)}* — "${citation.quote}"`;
    void navigator.clipboard.writeText(memo);
    setCopiedMemo(true);
    window.setTimeout(() => {
      setCopiedMemo(false);
    }, 2000);
  }

  // 计算行号范围并生成模拟槽位展示
  const quoteLines = citation.quote.split("\n");
  const startLine = citation.lineStart;

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas border-l border-divider select-text">
      {/* 视口顶栏：权威印章与序号 */}
      <header className="flex shrink-0 items-center justify-between border-b border-divider bg-surface/50 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-5 items-center rounded-sm bg-accent-soft px-1.5 font-mono text-[11px] font-semibold text-accent-strong">
            §{citation.citationId}
          </span>
          <h2 className="text-dense font-semibold text-ink">权威底稿核验视口</h2>
          <span className="font-mono text-label tabular-nums text-ink-secondary">
            [{String(rank)} / {String(total)}]
          </span>
        </div>
        <button
          type="button"
          aria-label="关闭底稿视口"
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-md text-ink-secondary tint hover:bg-surface-hover hover:text-ink active:scale-95"
        >
          <IconClose size={15} />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {/* 文档与章节坐标锚点 */}
        <section className="border-b border-divider p-4">
          <div className="flex items-start gap-2.5">
            <span className="mt-0.5 shrink-0 text-accent-strong">
              <IconDocument size={16} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-dense font-semibold text-ink break-words leading-snug">
                {citation.documentName}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-label">
                <span className="inline-flex items-center gap-1 rounded bg-accent-soft px-2 py-0.5 font-mono font-medium tabular-nums text-accent-strong">
                  <span className="opacity-70">坐标:</span>
                  <span>{locationLabel(citation)}</span>
                </span>
                {citation.headingPath.length > 0 ? (
                  <span className="inline-flex items-center rounded bg-surface px-2 py-0.5 text-ink-secondary">
                    {citation.headingPath.join(" / ")}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        </section>

        {/* 带行号槽位的合同原件片段（Gutter-based Document Excerpt） */}
        <section className="border-b border-divider p-4">
          <div className="flex items-center justify-between pb-2">
            <div className="flex items-center gap-1.5">
              <IconShieldCheck size={14} className="text-success-ink" />
              <h3 className="text-label font-medium text-ink">规范化 Markdown 权威校验切片</h3>
            </div>
            <span className="font-mono text-[11px] tabular-nums text-ink-muted">
              L{citation.lineStart}–L{citation.lineEnd}
            </span>
          </div>

          <div className="mt-2 overflow-x-auto rounded-lg border border-border bg-rail font-mono text-[12px] shadow-tactile">
            <div className="flex min-w-full">
              {/* 行号槽位 */}
              <div className="flex select-none flex-col border-r border-divider/80 bg-surface/80 py-2.5 pr-2.5 pl-3 text-right tabular-nums text-ink-muted">
                {quoteLines.map((_, i) => (
                  <div key={i} className="leading-relaxed">
                    {startLine + i}
                  </div>
                ))}
              </div>
              {/* 原文内容 */}
              <div className="flex-1 py-2.5 px-3 leading-relaxed text-ink whitespace-pre-wrap">
                {citation.quote}
              </div>
            </div>
          </div>
          <p className="mt-2 text-label text-ink-muted leading-tight">
            此摘录直接抽取自底层对象存储中的解析规范制品，由后端确定性防伪门控通过。
          </p>
        </section>

        {/* 父子切片拓扑树 (Parent-Child Topology) */}
        <section className="border-b border-divider p-4">
          <div className="flex items-center gap-1.5 pb-2">
            <IconListTree size={14} className="text-accent-strong" />
            <h3 className="text-label font-medium text-ink">分块架构拓扑 (Parent/Child Tree)</h3>
          </div>

          <div className="mt-2 rounded-lg border border-border bg-surface/30 p-3 text-dense">
            {/* 父块 */}
            <div className="flex items-start gap-2">
              <span className="mt-0.5 flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded bg-accent-soft font-mono text-[10px] font-bold text-accent-strong">
                P
              </span>
              <div className="min-w-0 flex-1">
                <span className="text-label font-medium text-ink">父块上下文 (Parent Context)</span>
                <p className="font-mono text-label break-all text-ink-secondary">
                  {citation.parentId}
                </p>
              </div>
            </div>

            {/* 子块连线与节点 */}
            <div className="relative mt-2 ml-2 border-l-2 border-divider pl-4">
              <div className="flex items-start gap-2">
                <span className="mt-0.5 flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded bg-success/15 font-mono text-[10px] font-bold text-success-ink">
                  C
                </span>
                <div className="min-w-0 flex-1">
                  <span className="text-label font-medium text-ink">
                    命中的检索锚点 (Child Chunk Match)
                  </span>
                  <div className="mt-1 flex flex-col gap-1">
                    {citation.childIds.map((id) => (
                      <span key={id} className="font-mono text-label break-all text-ink-secondary">
                        • {id}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 审计技术元数据 */}
        <section className="p-4">
          <h3 className="text-label font-medium text-ink-secondary">审计防伪元数据</h3>
          <dl className="mt-2 flex flex-col gap-1.5 text-label">
            <div className="flex justify-between gap-2">
              <dt className="text-ink-secondary">文档版本 ID</dt>
              <dd className="font-mono text-ink-muted">{citation.documentVersionId}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-ink-secondary">文档全局 ID</dt>
              <dd className="font-mono text-ink-muted">{citation.documentId}</dd>
            </div>
          </dl>
        </section>
      </div>

      {/* 底部操作栏 */}
      <footer className="flex flex-wrap shrink-0 items-center justify-end gap-2 border-t border-divider bg-surface/30 p-3">
        <button
          type="button"
          onClick={handleCopy}
          className="flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink active:scale-95"
        >
          {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
          <span>{copied ? "已复制原文" : "复制条款"}</span>
        </button>
        <button
          type="button"
          onClick={handleCopyMemo}
          title="复制标准法务备忘录引用格式（文档名、章节、行号与引文）"
          className="flex h-8 items-center gap-1.5 rounded-md bg-accent-soft px-2.5 text-label font-medium text-accent-strong tint hover:bg-accent/20 active:scale-95"
        >
          {copiedMemo ? <IconCheck size={14} /> : <IconCopy size={14} />}
          <span>{copiedMemo ? "已复制引用" : "复制法务引用"}</span>
        </button>
        <button
          type="button"
          onClick={() => {
            onOpenDocument(citation);
          }}
          className="flex h-8 items-center gap-1.5 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-strong active:scale-95"
        >
          <IconDocument size={14} />
          <span>查看文档</span>
        </button>
      </footer>
    </div>
  );
}
