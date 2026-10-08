import { useEffect, useRef, useState, type ReactNode } from "react";
import { Menu } from "@base-ui/react/menu";
import { Popover } from "@base-ui/react/popover";
import { IconArrowRight, IconCheck, IconChevronDown, IconPaperclip } from "../../components/icons";
import type { KnowledgeBase } from "../knowledge-bases/api";

export const DISCLAIMER =
  "本回答基于商业合同文档与法律条款分析，仅供参考，不构成正式的法律意见或执业律师代理意见。";

export interface ComposerProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly onSubmit: () => void;
  readonly knowledgeBases: readonly KnowledgeBase[];
  readonly knowledgeBaseId: string | null;
  readonly onKnowledgeBaseChange: (knowledgeBaseId: string) => void;
  readonly busy?: boolean;
  readonly autoFocus?: boolean;
}

const CAPSULE =
  "flex h-7 items-center gap-1.5 rounded-md px-2 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink";

const TOOL_ICON =
  "flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-ink-secondary tint hover:bg-surface-hover hover:text-ink";

const TEXT_MAX = 240;

/** 审查输入工作台组件：支持多行自适应伸缩、知识库检索范围切换与快捷键发送。 */
export function Composer({
  value,
  onChange,
  onSubmit,
  knowledgeBases,
  knowledgeBaseId,
  onKnowledgeBaseChange,
  busy = false,
  autoFocus = false,
}: ComposerProps): ReactNode {
  const field = useRef<HTMLTextAreaElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const canSend = value.trim().length > 0 && !busy;
  const currentKb = knowledgeBases.find((entry) => entry.id === knowledgeBaseId);
  const scopeLabel = currentKb?.name ?? "未选择知识库";

  // 根据输入文本高度自适应伸缩，最大高度封顶后内部滚动
  useEffect(() => {
    const element = field.current;
    if (element === null) {
      return;
    }
    element.style.height = "auto";
    element.style.height = `${String(Math.min(element.scrollHeight, TEXT_MAX))}px`;
  }, [value]);

  return (
    <div className="relative">
      <form
        className={`group relative rounded-[var(--radius-island)] bg-float shadow-workbench border transition-all duration-200 ${
          dragging
            ? "border-accent ring-2 ring-accent/30 bg-accent-soft/30"
            : "border-black/[0.08] dark:border-white/[0.08] focus-within:ring-2 focus-within:ring-accent/25 focus-within:border-accent"
        }`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => {
          setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
        }}
        onSubmit={(event) => {
          event.preventDefault();
          if (canSend) {
            onSubmit();
          }
        }}
      >
        <div className="px-4 pt-3.5">
          <label className="block">
            <span className="sr-only">输入合同审查指令</span>
            <textarea
              ref={field}
              value={value}
              autoFocus={autoFocus}
              rows={2}
              onChange={(event) => {
                onChange(event.target.value);
              }}
              onKeyDown={(event) => {
                // Enter 直接发送，Shift+Enter 换行，输入法打字时不触发
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  if (canSend) {
                    onSubmit();
                  }
                }
              }}
              placeholder="输入合同审查指令或争议焦点，按 Enter 发送，Shift + Enter 换行…"
              className="block max-h-[240px] w-full resize-none overflow-y-auto border-0 bg-transparent text-[15px] leading-[1.6] text-ink outline-none focus-visible:shadow-none"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 px-3 pt-1.5 pb-2.5">
          <Popover.Root>
            <Popover.Trigger
              aria-label="上传待审查合同或协议附件作为提问上下文"
              title="上传合同附件"
              className={TOOL_ICON}
            >
              <IconPaperclip size={16} />
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Positioner side="top" align="start" sideOffset={6} collisionPadding={12}>
                <Popover.Popup className="w-[300px] rounded-lg bg-float p-3 text-dense text-ink shadow-popover border border-border/80">
                  <p className="font-medium text-ink">上传合同附件</p>
                  <p className="mt-1 text-label text-ink-secondary">
                    当前版本请直接在「知识资产管理 → 知识库」中上传完整合同。
                  </p>
                </Popover.Popup>
              </Popover.Positioner>
            </Popover.Portal>
          </Popover.Root>

          {knowledgeBases.length > 0 ? (
            <Menu.Root>
              <Menu.Trigger
                aria-label={`当前检索知识库：${scopeLabel}。点击切换`}
                title="选择检索知识库"
                className={CAPSULE}
              >
                <span className="max-w-[200px] truncate">{scopeLabel}</span>
                <IconChevronDown size={13} />
              </Menu.Trigger>
              <Menu.Portal>
                <Menu.Positioner side="top" align="start" sideOffset={6} collisionPadding={12}>
                  <Menu.Popup className="min-w-[220px] rounded-lg bg-float p-1 shadow-popover border border-border/80">
                    {knowledgeBases.map((entry) => (
                      <Menu.Item
                        key={entry.id}
                        onClick={() => {
                          onKnowledgeBaseChange(entry.id);
                        }}
                        className="flex h-8 cursor-default items-center justify-between rounded-md px-2 text-dense text-ink outline-none data-[highlighted]:bg-surface-hover"
                      >
                        <span className="truncate">{entry.name}</span>
                        {entry.id === knowledgeBaseId ? (
                          <span className="text-accent-strong">
                            <IconCheck size={14} />
                          </span>
                        ) : null}
                      </Menu.Item>
                    ))}
                  </Menu.Popup>
                </Menu.Positioner>
              </Menu.Portal>
            </Menu.Root>
          ) : null}

          <div className="ml-auto flex items-center gap-2">
            <span className="hidden font-mono text-[11px] text-ink-muted sm:inline select-none">
              Enter 发送 · Shift+Enter 换行
            </span>
            <button
              type="submit"
              disabled={!canSend}
              aria-label="发送审查指令"
              className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-strong text-canvas shadow-sm tint transition-all hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed active:scale-95"
            >
              <IconArrowRight size={15} />
            </button>
          </div>
        </div>
      </form>

      <p className="mt-2 text-center text-label text-ink-muted select-none">{DISCLAIMER}</p>
    </div>
  );
}
