import { useState, type ReactNode } from "react";
import { Popover } from "@base-ui/react/popover";
import { IconCheck, IconCopy, IconDocument, IconExternalLink } from "../../components/icons";
import type { CitationPayload } from "../../lib/sse";
import { locationLabel } from "./AnswerBody";

/** 商业合同专属高价值法律实体与条款关键词模式 */
const CONTRACT_ENTITY_SPLIT =
  /(\$[\d,]+(?:\.\d+)?(?:\s?(?:million|billion|k|USD))?|USD\s+[\d,]+|\b\d+\s+(?:calendar\s+|business\s+)?(?:days|months|years|weeks)\b|\bNet\s+\d+\b|\bwithin\s+\d+\s+days\b|\b\d+-day\b|Limitation of Liability|Material Breach|Indemnification|Gross Negligence|Governing Law|Force Majeure|Non-Solicitation|Exclusivity|Confidentiality|Change of Control|Cure Period|Delaware|New York|Arbitration)/gi;

const RISK_CLAUSE_REGEX =
  /^(?:Limitation of Liability|Material Breach|Gross Negligence|Indemnification)$/i;
const NUMERIC_CLAUSE_REGEX =
  /^(?:\$[\d,]+|USD|\b\d+\s+(?:calendar|business)?\s*(?:days|months|years|weeks)|Net\s+\d+|within\s+\d+\s+days|\d+-day)/i;

function HighlightedContractText({ text }: { readonly text: string }): ReactNode {
  return (
    <>
      {text.split(CONTRACT_ENTITY_SPLIT).map((part, index) => {
        if (RISK_CLAUSE_REGEX.test(part)) {
          return (
            <mark
              key={`${String(index)}-${part}`}
              className="rounded-sm bg-error/15 px-1 font-medium text-error-ink"
            >
              {part}
            </mark>
          );
        }
        if (NUMERIC_CLAUSE_REGEX.test(part)) {
          return (
            <mark
              key={`${String(index)}-${part}`}
              className="rounded-sm bg-warning-soft px-1 font-medium tabular-nums text-ink"
            >
              {part}
            </mark>
          );
        }
        if (CONTRACT_ENTITY_SPLIT.test(part)) {
          return (
            <mark
              key={`${String(index)}-${part}`}
              className="rounded-sm bg-accent-soft px-1 font-medium text-accent-strong"
            >
              {part}
            </mark>
          );
        }
        return part;
      })}
    </>
  );
}

export interface CitationPopoverProps {
  readonly citation: CitationPayload;
  readonly rank: number;
  readonly total: number;
  readonly onCopy: (citation: CitationPayload) => void;
  readonly onOpenSource: (citation: CitationPayload) => void;
}

/** 引文悬浮卡片组件：就地呈现权威引述原文、章节路径与位置信息。 */
export function CitationPopover({
  citation,
  rank,
  total,
  onCopy,
  onOpenSource,
}: CitationPopoverProps): ReactNode {
  const [copiedQuote, setCopiedQuote] = useState(false);
  const [copiedMemo, setCopiedMemo] = useState(false);

  function handleCopyQuote(): void {
    onCopy(citation);
    setCopiedQuote(true);
    window.setTimeout(() => {
      setCopiedQuote(false);
    }, 2000);
  }

  function handleCopyMemo(): void {
    const memoFormat = `*${citation.documentName}, ${locationLabel(citation)}* — "${citation.quote}"`;
    void navigator.clipboard.writeText(memoFormat);
    setCopiedMemo(true);
    window.setTimeout(() => {
      setCopiedMemo(false);
    }, 2000);
  }

  return (
    <div className="w-[430px] max-w-[calc(100vw-24px)] overflow-hidden rounded-lg border border-black/[0.08] bg-float shadow-popover dark:border-white/[0.1]">
      <header className="border-b border-divider bg-surface/40 px-4 py-3">
        <div className="flex items-start gap-2 text-dense font-medium text-ink">
          <span className="mt-0.5 shrink-0 text-accent-strong">
            <IconDocument size={16} />
          </span>
          <span className="min-w-0 font-semibold leading-snug">{citation.documentName}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="inline-flex h-5 items-center rounded-sm bg-accent-soft px-1.5 font-mono text-label font-medium text-accent-strong">
            §{citation.citationId}
          </span>
          {citation.headingPath.length === 0 ? null : (
            <span className="min-w-0 max-w-[200px] truncate rounded bg-surface px-1.5 py-0.5 text-label text-ink-secondary">
              {citation.headingPath.join(" / ")}
            </span>
          )}
          <span className="rounded bg-surface px-1.5 py-0.5 text-label tabular-nums text-ink-secondary">
            {locationLabel(citation)}
          </span>
        </div>
      </header>

      <div className="border-b border-divider bg-surface/15 px-4 py-2">
        <div className="flex items-center justify-between text-label text-ink-secondary">
          <span>
            本次引用排序：第 {String(rank)} / {String(total)} 条
          </span>
          <span className="inline-flex items-center gap-1 font-mono text-[11px] font-medium text-accent-strong">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-strong animate-pulse" />
            权威法务证据
          </span>
        </div>
      </div>

      <div className="max-h-[240px] overflow-y-auto px-4 py-3">
        <h3 className="text-label font-medium text-ink-secondary">后端权威校验原文引述</h3>
        <p className="mt-2 rounded-md border-l-2 border-accent-strong bg-surface/50 p-2.5 text-answer leading-relaxed text-ink select-text">
          <HighlightedContractText text={citation.quote} />
        </p>
        <p className="mt-2 text-label text-ink-secondary">
          规范化 Markdown 行号区间：行 {citation.lineStart}–{citation.lineEnd}
        </p>
      </div>

      <footer className="flex flex-wrap items-center gap-1.5 border-t border-divider bg-surface/20 px-3 py-2">
        <button
          type="button"
          onClick={handleCopyQuote}
          title="复制原始引文摘录"
          className="flex h-7 items-center gap-1.5 rounded-md px-2 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink active:scale-95"
        >
          {copiedQuote ? <IconCheck size={14} /> : <IconCopy size={14} />}
          {copiedQuote ? "已复制原文" : "复制原文"}
        </button>

        <button
          type="button"
          onClick={handleCopyMemo}
          title="复制标准法务备忘录引用格式（文档名、条款行号与引文）"
          className="flex h-7 items-center gap-1.5 rounded-md px-2 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink active:scale-95"
        >
          {copiedMemo ? <IconCheck size={14} /> : <IconCopy size={14} />}
          {copiedMemo ? "已复制引用" : "复制法务引用"}
        </button>

        <Popover.Close
          render={
            <button
              type="button"
              onClick={() => {
                onOpenSource(citation);
              }}
              className="ml-auto flex h-7 items-center gap-1.5 rounded-md bg-surface px-2.5 text-label font-medium text-ink tint hover:bg-surface-strong active:scale-95"
            />
          }
        >
          <IconExternalLink size={13} />
          查看溯源
        </Popover.Close>
      </footer>
    </div>
  );
}
