import { memo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Popover } from "@base-ui/react/popover";
import { IconCheck, IconCopy, IconGitCompare, IconShieldAlert } from "../../components/icons";
import type { CitationPayload } from "../../lib/sse";
import { CitationPopover } from "./CitationPopover";

const MARK_PATTERN = /\[(S\d+)\]/g;

export function markDomId(citationId: string): string {
  return `cite-${citationId}`;
}

export interface MarkProps {
  readonly citationId: string;
  readonly citation: CitationPayload | null;
  readonly order: readonly string[];
  readonly onCopy: (citation: CitationPayload) => void;
  readonly onOpenSource: (citation: CitationPayload) => void;
}

const MARK_BASE =
  "mx-0.5 inline-flex h-5 items-center gap-0.5 rounded-sm px-1.5 align-baseline font-mono text-[11px] font-semibold tracking-tight transition-all duration-150 active:scale-95 cursor-pointer";

/** 回答正文中的行内引文角标组件。 */
export function CitationMark({
  citationId,
  citation,
  order,
  onCopy,
  onOpenSource,
}: MarkProps): ReactNode {
  if (citation === null) {
    return (
      <span
        className={`${MARK_BASE} border border-divider bg-surface text-ink-secondary`}
        title="引用校验中：后端尚未确认这条引用"
      >
        <span>§</span>
        <span>{citationId}</span>
        <span className="sr-only">（引用校验中）</span>
      </span>
    );
  }

  const className = `${MARK_BASE} border border-accent/25 bg-accent-soft text-accent-strong shadow-xs hover:bg-accent-strong hover:text-canvas hover:border-transparent hover:shadow-sm`;
  const rank = order.indexOf(citationId) + 1;

  return (
    <Popover.Root>
      <Popover.Trigger
        render={
          <button
            id={markDomId(citationId)}
            type="button"
            className={className}
            aria-label={`条款引用 §${citationId}：${citation.documentName}。打开来源详情`}
          />
        }
      >
        <span className="opacity-80">§</span>
        <span>{citationId}</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="right" align="start" sideOffset={8} collisionPadding={16}>
          <Popover.Popup>
            <CitationPopover
              citation={citation}
              rank={rank}
              total={order.length}
              onCopy={onCopy}
              onOpenSource={onOpenSource}
            />
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** 格式化引文在源文档中的行号区间位置。 */
export function locationLabel(citation: CitationPayload): string {
  return `行 ${citation.lineStart}–${citation.lineEnd}`;
}

/** 建议红线条款对照组件（Redline Diff Viewer）。 */
const RedlineBlock = memo(function RedlineBlock({ raw }: { readonly raw: string }): ReactNode {
  const [copied, setCopied] = useState(false);
  const lines = raw.split("\n");

  function copyCode(): void {
    void navigator.clipboard.writeText(raw);
    setCopied(true);
    window.setTimeout(() => {
      setCopied(false);
    }, 2000);
  }

  return (
    <div className="my-4 overflow-hidden rounded-lg border border-border bg-canvas shadow-tactile">
      <div className="flex items-center justify-between border-b border-divider bg-surface/80 px-3.5 py-2">
        <div className="flex items-center gap-2">
          <IconGitCompare size={14} className="text-accent-strong" />
          <span className="text-label font-medium text-ink">
            建议修改红线条款 (Redline Revision)
          </span>
        </div>
        <button
          type="button"
          onClick={copyCode}
          className="flex h-6 items-center gap-1 rounded px-2 text-label text-ink-secondary tint hover:bg-surface-hover hover:text-ink active:scale-95"
        >
          {copied ? <IconCheck size={13} /> : <IconCopy size={13} />}
          <span>{copied ? "已复制" : "复制"}</span>
        </button>
      </div>
      <div className="overflow-x-auto p-3 font-mono text-[12px] leading-relaxed">
        {lines.map((line, idx) => {
          const isAdd = line.startsWith("+");
          const isDel = line.startsWith("-");
          return (
            <div
              key={idx}
              className={`flex items-start px-1.5 py-0.5 rounded-xs ${
                isAdd
                  ? "bg-success/10 text-success-ink font-medium"
                  : isDel
                    ? "bg-error/10 text-error-ink line-through opacity-85"
                    : "text-ink"
              }`}
            >
              <span className="w-5 shrink-0 select-none opacity-50 tabular-nums">
                {isAdd ? "+" : isDel ? "-" : " "}
              </span>
              <span className="flex-1 whitespace-pre-wrap">{line.replace(/^[+-]\s?/, "")}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
});

export interface AnswerBodyProps {
  readonly text: string;
  readonly citationById: ReadonlyMap<string, CitationPayload>;
  readonly order: readonly string[];
  readonly onCopy: (citation: CitationPayload) => void;
  readonly onOpenSource: (citation: CitationPayload) => void;
  readonly isStreaming?: boolean;
  readonly className?: string;
}

/** 将 Markdown 文本中的 [S1] 等角标解析并替换为交互式 CitationMark 组件。 */
function renderWithCitations(
  content: ReactNode,
  citationById: ReadonlyMap<string, CitationPayload>,
  order: readonly string[],
  onCopy: (citation: CitationPayload) => void,
  onOpenSource: (citation: CitationPayload) => void,
): ReactNode {
  if (typeof content === "string") {
    if (!content.includes("[S")) {
      return content;
    }
    const nodes: ReactNode[] = [];
    let lastIndex = 0;
    for (const match of content.matchAll(MARK_PATTERN)) {
      const citationId = match[1];
      const matchIndex = match.index;
      if (citationId === undefined || matchIndex === undefined) {
        continue;
      }
      if (matchIndex > lastIndex) {
        nodes.push(content.slice(lastIndex, matchIndex));
      }
      nodes.push(
        <CitationMark
          key={`${citationId}-${matchIndex}`}
          citationId={citationId}
          citation={citationById.get(citationId) ?? null}
          order={order}
          onCopy={onCopy}
          onOpenSource={onOpenSource}
        />,
      );
      lastIndex = matchIndex + match[0].length;
    }
    if (lastIndex < content.length) {
      nodes.push(content.slice(lastIndex));
    }
    return nodes;
  }

  if (Array.isArray(content)) {
    return content.map((item, idx) => (
      <span key={idx} className="contents">
        {renderWithCitations(item, citationById, order, onCopy, onOpenSource)}
      </span>
    ));
  }

  return content;
}

/** 结构化回答正文渲染组件（集成 Markdown 解析、红线对比与交互式引文标记）。 */
export function AnswerBody({
  text,
  citationById,
  order,
  onCopy,
  onOpenSource,
  isStreaming = false,
  className,
}: AnswerBodyProps): ReactNode {
  return (
    <div className={`text-answer text-ink leading-relaxed ${className ?? ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <p className="mb-3 leading-[1.75] text-ink last:mb-0">
              {renderWithCitations(children, citationById, order, onCopy, onOpenSource)}
            </p>
          ),
          h1: ({ children }) => (
            <div className="mt-6 mb-3 flex items-center gap-2 border-b border-divider pb-2">
              <span className="flex h-5 w-5 items-center justify-center rounded bg-accent-soft text-accent-strong font-mono text-[11px] font-bold">
                §1
              </span>
              <h1 className="text-title font-semibold tracking-tight text-ink">
                {renderWithCitations(children, citationById, order, onCopy, onOpenSource)}
              </h1>
            </div>
          ),
          h2: ({ children }) => (
            <div className="mt-5 mb-2.5 flex items-center gap-2">
              <span className="h-4 w-1 rounded-full bg-accent-strong" aria-hidden="true" />
              <h2 className="text-section font-semibold tracking-tight text-ink">
                {renderWithCitations(children, citationById, order, onCopy, onOpenSource)}
              </h2>
            </div>
          ),
          h3: ({ children }) => (
            <h3 className="mt-4 mb-2 text-dense font-semibold tracking-tight text-ink">
              {renderWithCitations(children, citationById, order, onCopy, onOpenSource)}
            </h3>
          ),
          ul: ({ children }) => (
            <ul className="mb-3 list-disc list-outside pl-5 space-y-1.5 text-ink">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-3 list-decimal list-outside pl-5 space-y-1.5 text-ink">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="leading-[1.75]">
              {renderWithCitations(children, citationById, order, onCopy, onOpenSource)}
            </li>
          ),
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto rounded-lg border border-border bg-canvas shadow-tactile">
              <table className="w-full min-w-[500px] border-collapse text-left text-dense">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="border-b border-border bg-surface text-ink-secondary">
              {children}
            </thead>
          ),
          th: ({ children }) => (
            <th className="px-3.5 py-2.5 text-label font-medium tracking-tight">
              {renderWithCitations(children, citationById, order, onCopy, onOpenSource)}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-t border-divider px-3.5 py-2.5 text-ink tabular-nums leading-normal">
              {renderWithCitations(children, citationById, order, onCopy, onOpenSource)}
            </td>
          ),
          tr: ({ children }) => <tr className="hover:bg-surface/50 tint">{children}</tr>,
          blockquote: ({ children }) => (
            <blockquote className="my-4 rounded-lg border-l-3 border-accent-strong bg-surface/70 px-4 py-3 text-dense text-ink shadow-sm">
              <div className="flex items-start gap-2.5">
                <span className="mt-0.5 shrink-0 text-accent-strong">
                  <IconShieldAlert size={16} />
                </span>
                <div className="flex-1">
                  {renderWithCitations(children, citationById, order, onCopy, onOpenSource)}
                </div>
              </div>
            </blockquote>
          ),
          code: ({ className: codeClass, children }) => {
            const isDiff = Boolean(codeClass?.includes("language-diff"));
            const rawContent =
              typeof children === "string"
                ? children
                : Array.isArray(children)
                  ? children.join("")
                  : "";
            if (isDiff) {
              return <RedlineBlock raw={rawContent} />;
            }
            const isBlock = Boolean(codeClass?.includes("language-"));
            return isBlock ? (
              <pre className="my-3.5 overflow-x-auto rounded-lg border border-border bg-rail p-3.5 font-mono text-[12px] leading-relaxed text-ink shadow-tactile">
                <code>{children}</code>
              </pre>
            ) : (
              <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-[12px] text-accent-strong border border-divider/60">
                {children}
              </code>
            );
          },
          strong: ({ children }) => (
            <strong className="font-semibold text-ink">
              {renderWithCitations(children, citationById, order, onCopy, onOpenSource)}
            </strong>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent-strong underline underline-offset-2 hover:text-accent tint"
            >
              {renderWithCitations(children, citationById, order, onCopy, onOpenSource)}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
      {isStreaming ? (
        <span
          aria-hidden="true"
          className="inline-block h-4 w-1.5 ml-1 rounded-xs bg-accent-strong animate-pulse align-middle"
        />
      ) : null}
    </div>
  );
}
