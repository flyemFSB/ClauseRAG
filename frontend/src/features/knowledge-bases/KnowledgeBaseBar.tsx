import { Menu } from "@base-ui/react/menu";
import type { ReactNode } from "react";

import { IconEllipsis } from "../../components/icons";
import { formatTimestamp } from "../../lib/format";
import { KnowledgeBaseSelect } from "./KnowledgeBaseSelect";
import type { KnowledgeBase } from "./api";

interface KnowledgeBaseBarProps {
  readonly knowledgeBases: readonly KnowledgeBase[];
  readonly value: string | null;
  readonly knowledgeBase: KnowledgeBase | null;
  readonly onSelect: (id: string) => void;
  readonly onRename: () => void;
  readonly onDelete: () => void;
}

export function KnowledgeBaseBar({
  knowledgeBases,
  value,
  knowledgeBase,
  onSelect,
  onRename,
  onDelete,
}: KnowledgeBaseBarProps): ReactNode {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-canvas px-4 py-3">
      <KnowledgeBaseSelect
        knowledgeBases={knowledgeBases}
        value={value}
        onChange={(next) => {
          onSelect(next);
        }}
      />

      {knowledgeBase === null ? null : (
        <>
          <span className="text-label text-ink-secondary">
            创建于 {formatTimestamp(knowledgeBase.createdAt)}
          </span>
          {knowledgeBase.description === null ? null : (
            <span className="max-w-[52ch] truncate text-label text-ink-secondary">
              {knowledgeBase.description}
            </span>
          )}
          <Menu.Root>
            <Menu.Trigger
              aria-label="知识库操作"
              className="ml-auto flex h-8 w-8 items-center justify-center rounded-md text-ink-secondary tint hover:bg-surface-hover hover:text-ink"
            >
              <IconEllipsis size={16} />
            </Menu.Trigger>
            <Menu.Portal>
              <Menu.Positioner side="bottom" align="end" sideOffset={6} collisionPadding={12}>
                <Menu.Popup className="min-w-[180px] rounded-lg bg-float p-1 shadow-popover">
                  <Menu.Item
                    onClick={() => {
                      onRename();
                    }}
                    className="flex h-8 cursor-default items-center rounded-md px-2 text-dense text-ink outline-none data-[highlighted]:bg-surface-hover"
                  >
                    重命名知识库
                  </Menu.Item>
                  <Menu.Item
                    onClick={() => {
                      onDelete();
                    }}
                    className="flex h-8 cursor-default items-center rounded-md px-2 text-dense text-error-ink outline-none data-[highlighted]:bg-error/10"
                  >
                    删除知识库
                  </Menu.Item>
                </Menu.Popup>
              </Menu.Positioner>
            </Menu.Portal>
          </Menu.Root>
        </>
      )}
    </div>
  );
}
