/**
 * 知识库下拉选择组件。
 *
 * 供控制台各业务模块切换检索范围；支持空态禁用与键盘导航。
 */

import type { ReactNode } from "react";
import { Select } from "@base-ui/react/select";
import { IconCheck, IconChevronDown } from "../../components/icons";
import type { KnowledgeBase } from "./api";

export function KnowledgeBaseSelect({
  knowledgeBases,
  value,
  onChange,
  label = "知识库",
}: {
  readonly knowledgeBases: readonly KnowledgeBase[];
  readonly value: string | null;
  readonly onChange: (knowledgeBaseId: string) => void;
  readonly label?: string;
}): ReactNode {
  const empty = knowledgeBases.length === 0;
  const items: Record<string, ReactNode> = {};
  for (const knowledgeBase of knowledgeBases) {
    items[knowledgeBase.id] = knowledgeBase.name;
  }

  return (
    <Select.Root
      items={items}
      value={value}
      onValueChange={(next) => {
        if (typeof next === "string") {
          onChange(next);
        }
      }}
    >
      <Select.Trigger
        aria-label={label}
        disabled={empty}
        className="flex h-8 min-w-[200px] items-center justify-between gap-2 rounded-md border border-control-border bg-canvas px-2.5 text-left text-body text-ink tint hover:bg-surface disabled:border-border disabled:bg-surface disabled:text-ink-muted"
      >
        <Select.Value placeholder={empty ? "还没有知识库" : "选择知识库"} />
        <Select.Icon className="text-ink-muted">
          <IconChevronDown size={14} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner sideOffset={4} alignItemWithTrigger={false} className="z-50">
          <Select.Popup className="max-h-[280px] min-w-[var(--anchor-width)] overflow-y-auto rounded-lg bg-float p-1 shadow-popover">
            <Select.List>
              {knowledgeBases.map((knowledgeBase) => (
                <Select.Item
                  key={knowledgeBase.id}
                  value={knowledgeBase.id}
                  className="flex h-8 cursor-default items-center gap-2 rounded-md px-2 text-dense text-ink-secondary tint select-none data-[highlighted]:bg-surface-hover data-[highlighted]:text-ink data-[selected]:text-ink"
                >
                  <span className="flex w-4 shrink-0 items-center text-accent">
                    <Select.ItemIndicator>
                      <IconCheck size={14} />
                    </Select.ItemIndicator>
                  </span>
                  <Select.ItemText className="min-w-0 flex-1 truncate">
                    {knowledgeBase.name}
                  </Select.ItemText>
                </Select.Item>
              ))}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}
