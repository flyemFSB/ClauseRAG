/**
 * 对话历史侧栏组件。
 *
 * 展示用户历史会话列表，按时间分组（今天 / 过去 7 天）。
 * 支持新建会话、行内重命名与删除，以及极简图标导轨态收起。
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Menu } from "@base-ui/react/menu";
import { Tooltip } from "@base-ui/react/tooltip";
import {
  IconClose,
  IconEllipsis,
  IconFileSearch,
  IconPencil,
  IconPlus,
  IconSidebar,
  IconSidebarClose,
  IconTrash,
} from "../../components/icons";
import { FailureNotice } from "../../components/failure-notice";
import { SkeletonRows } from "../../components/skeleton";
import { groupsOf, useSessions, type ChatSession } from "./sessions";

function SessionRow({
  session,
  active,
  onSelect,
}: {
  readonly session: ChatSession;
  readonly active: boolean;
  readonly onSelect: () => void;
}): ReactNode {
  const { rename, remove } = useSessions();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(session.title ?? "");
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  function commit(): void {
    rename(session.id, draft);
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="py-1">
        <input
          ref={inputRef}
          value={draft}
          aria-label="会话名称"
          onChange={(event) => {
            setDraft(event.target.value);
          }}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commit();
            }
            if (event.key === "Escape") {
              event.preventDefault();
              setDraft(session.title ?? "");
              setEditing(false);
            }
          }}
          className="h-9 w-full rounded-md bg-canvas px-2 text-dense text-ink outline-[1px] outline-accent"
        />
      </div>
    );
  }

  return (
    <div className="group relative flex items-center">
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        className={`flex h-10 w-full min-w-0 items-center gap-2 rounded-md pr-8 pl-2 text-left text-dense tint ${
          active
            ? "bg-surface-hover text-ink"
            : "text-ink-secondary hover:bg-surface-hover hover:text-ink"
        }`}
      >
        <span className="min-w-0 flex-1 truncate">{session.title ?? "新对话"}</span>
        <span className="shrink-0 text-label tabular-nums text-ink-muted">{session.at}</span>
      </button>

      <Menu.Root>
        <Menu.Trigger
          aria-label={`${session.title ?? "新对话"} 的操作`}
          className="absolute right-1 flex h-7 w-7 items-center justify-center rounded-md text-ink-secondary opacity-0 tint group-hover:opacity-100 hover:bg-surface-strong hover:text-ink focus-visible:opacity-100"
        >
          <IconEllipsis size={16} />
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Positioner side="bottom" align="end" sideOffset={4} collisionPadding={12}>
            <Menu.Popup className="min-w-[168px] rounded-lg bg-float p-1 shadow-popover">
              <Menu.Item
                onClick={() => {
                  setDraft(session.title ?? "");
                  setEditing(true);
                }}
                className="flex h-8 cursor-default items-center gap-2 rounded-md px-2 text-dense text-ink outline-none data-[highlighted]:bg-surface-hover"
              >
                <IconPencil size={14} />
                重命名
              </Menu.Item>
              <span className="block px-2 py-1 text-label text-ink-secondary">{session.scope}</span>
              <Menu.Separator className="my-1 h-px bg-divider" />
              <Menu.Item
                onClick={() => {
                  remove(session.id);
                }}
                className="flex h-8 cursor-default items-center gap-2 rounded-md px-2 text-dense text-error-ink outline-none data-[highlighted]:bg-error/10"
              >
                <IconTrash size={14} />
                删除
              </Menu.Item>
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
    </div>
  );
}

export interface ConversationRailProps {
  readonly onClose?: () => void;
  readonly collapsed?: boolean;
  readonly onToggleCollapse?: () => void;
}

export function ConversationRail({
  onClose,
  collapsed = false,
  onToggleCollapse,
}: ConversationRailProps): ReactNode {
  const {
    sessions,
    activeId,
    start,
    select,
    conversationsPending,
    conversationsError,
    knowledgeBases,
    startPending,
    startError,
  } = useSessions();
  const groups = groupsOf(sessions);
  const canStart = knowledgeBases.length > 0;

  if (collapsed) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center py-3 gap-2">
        {onToggleCollapse === undefined ? null : (
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label="展开会话列表 (Ctrl/⌘ + [)"
            title="展开会话列表 (Ctrl/⌘ + [)"
            className="flex h-8.5 w-8.5 items-center justify-center rounded-md text-ink-secondary tint hover:bg-surface-hover hover:text-ink"
          >
            <IconSidebar size={18} />
          </button>
        )}
        <button
          type="button"
          onClick={start}
          disabled={!canStart || startPending}
          aria-label="新建对话"
          title={canStart ? "新建对话" : "暂无知识库"}
          className="flex h-8.5 w-8.5 items-center justify-center rounded-md bg-accent-strong text-canvas tint hover:bg-accent disabled:opacity-40"
        >
          <IconPlus size={16} />
        </button>
        <div className="h-px w-6 bg-divider my-1" />
        <nav
          aria-label="会话缩略"
          className="flex flex-1 flex-col items-center gap-1.5 overflow-y-auto px-1 w-full"
        >
          {sessions.map((session) => {
            const active = session.id === activeId;
            return (
              <Tooltip.Root key={session.id}>
                <Tooltip.Trigger
                  render={
                    <button
                      type="button"
                      onClick={() => {
                        select(session.id);
                      }}
                      className={`flex h-8.5 w-8.5 items-center justify-center rounded-md tint transition-colors ${
                        active
                          ? "bg-surface-hover text-accent-strong shadow-xs font-semibold"
                          : "text-ink-secondary hover:bg-surface-hover hover:text-ink"
                      }`}
                    >
                      <IconFileSearch size={15} />
                    </button>
                  }
                />
                <Tooltip.Portal>
                  <Tooltip.Positioner side="right" sideOffset={8}>
                    <Tooltip.Popup className="rounded-md bg-float px-2.5 py-1.5 text-label shadow-popover border border-border/80 max-w-[220px] truncate text-ink">
                      {session.title ?? "新对话"}
                    </Tooltip.Popup>
                  </Tooltip.Positioner>
                </Tooltip.Portal>
              </Tooltip.Root>
            );
          })}
        </nav>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-col gap-2 px-3 pt-3 pb-2">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={start}
            disabled={!canStart || startPending}
            title={canStart ? "新建对话" : "还没有知识库，新建对话需要先有一个知识库"}
            className="flex h-9 flex-1 items-center gap-2 rounded-md bg-accent-strong px-2 text-label font-medium text-canvas tint hover:bg-accent disabled:opacity-40"
          >
            <IconPlus size={16} />
            {startPending ? "正在新建…" : "新建对话"}
          </button>
          {onToggleCollapse === undefined ? null : (
            <button
              type="button"
              onClick={onToggleCollapse}
              aria-label="收起会话列表 (Ctrl/⌘ + [)"
              title="收起会话列表 (Ctrl/⌘ + [)"
              className="flex h-9 w-9 items-center justify-center rounded-md text-ink-secondary tint hover:bg-surface-hover hover:text-ink"
            >
              <IconSidebarClose size={17} />
            </button>
          )}
          {onClose === undefined ? null : (
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭会话列表"
              className="flex h-9 w-9 items-center justify-center rounded-md text-ink-secondary tint hover:bg-surface-hover hover:text-ink"
            >
              <IconClose size={16} />
            </button>
          )}
        </div>
        {canStart ? null : (
          <p className="px-1 text-label text-ink-secondary">
            还没有知识库。先在「控制台 → 知识库」里建一个。
          </p>
        )}
        {startError === null ? null : (
          <p className="px-1 text-label text-error-ink">{startError}</p>
        )}
      </div>

      <nav aria-label="会话历史" className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {conversationsError === null ? null : (
          <div className="px-1 py-2">
            <FailureNotice title="会话列表没有读出来" detail={conversationsError} />
          </div>
        )}
        {conversationsPending ? (
          <div className="px-1 py-2">
            <SkeletonRows rows={4} />
          </div>
        ) : null}
        {groups.map((group) => (
          <section key={group.label} className="mt-1">
            <h2 className="px-2 py-2 text-label font-medium text-ink-secondary">{group.label}</h2>
            <ul className="flex flex-col gap-1">
              {group.sessions.map((session) => (
                <li key={session.id}>
                  <SessionRow
                    session={session}
                    active={session.id === activeId}
                    onSelect={() => {
                      select(session.id);
                    }}
                  />
                </li>
              ))}
            </ul>
          </section>
        ))}
        {sessions.length === 0 && !conversationsPending && conversationsError === null ? (
          <p className="px-2 py-6 text-label text-ink-secondary">
            还没有会话。新建一个，或直接提问。
          </p>
        ) : null}
      </nav>
    </div>
  );
}
