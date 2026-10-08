import { Menu } from "@base-ui/react/menu";
import type { Dispatch, ReactNode, SetStateAction } from "react";

import {
  IconCheck,
  IconClose,
  IconFilter,
  IconReplay,
  IconSearch,
  IconTrash,
} from "../../components/icons";
import { EmptyState, FailureNotice } from "../../components/failure-notice";
import { SkeletonRows } from "../../components/skeleton";
import { FILTER_LABEL, type Row, type StatusFilter } from "./rows";
import { DocumentTable } from "./DocumentTable";

interface DocumentListSectionProps {
  readonly rows: readonly Row[];
  readonly visible: readonly Row[];
  readonly selected: readonly string[];
  readonly allVisibleSelected: boolean;
  readonly query: string;
  readonly filter: StatusFilter;
  readonly onQueryChange: (query: string) => void;
  readonly onFilterChange: (filter: StatusFilter) => void;
  readonly isPending: boolean;
  readonly errorMessage: string;
  readonly onRetry: () => void;
  readonly onSelectionChange: Dispatch<SetStateAction<readonly string[]>>;
  readonly onReparse: (versionId: string | null) => void;
  readonly onReparseSelection: () => void;
  readonly onOpenSheet: (row: Row) => void;
  readonly onRequestDelete: (documentId: string) => void;
  readonly onRequestDeleteSelection: () => void;
  readonly onOpenDocument: (documentId: string) => void;
}

export function DocumentListSection({
  rows,
  visible,
  selected,
  allVisibleSelected,
  query,
  filter,
  onQueryChange,
  onFilterChange,
  isPending,
  errorMessage,
  onRetry,
  onSelectionChange,
  onReparse,
  onReparseSelection,
  onOpenSheet,
  onRequestDelete,
  onRequestDeleteSelection,
  onOpenDocument,
}: DocumentListSectionProps): ReactNode {
  function renderListBody(): ReactNode {
    if (isPending) {
      return <SkeletonRows rows={5} />;
    }
    if (errorMessage.length > 0) {
      return (
        <div className="px-4 py-4">
          <FailureNotice
            title="文档列表没有读出来"
            detail={errorMessage}
            action={
              <button
                type="button"
                onClick={() => {
                  onRetry();
                }}
                className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
              >
                重试
              </button>
            }
          />
        </div>
      );
    }
    if (rows.length === 0) {
      return (
        <div className="px-4 py-4">
          <EmptyState title="这个知识库还没有文档">
            上传第一份指南或文献即可开始检索。上传后解析、分块、嵌入与索引会在后台依次执行。
          </EmptyState>
        </div>
      );
    }
    return null;
  }

  const bulkBar =
    selected.length === 0 ? null : (
      <div className="fixed inset-x-0 bottom-0 z-30 flex items-center gap-2 border-t border-border bg-float px-3 py-2 shadow-toast md:hidden">
        <span className="text-label tabular-nums text-ink">已选 {selected.length} 项</span>
        <button
          type="button"
          onClick={() => {
            onReparseSelection();
          }}
          className="ml-auto flex h-8 items-center gap-2 rounded-md px-2 text-label font-medium text-ink-secondary hover:bg-surface-hover hover:text-ink"
        >
          <IconReplay size={14} />
          批量解析
        </button>
        <button
          type="button"
          onClick={() => {
            onRequestDeleteSelection();
          }}
          className="flex h-8 items-center gap-2 rounded-md px-2 text-label font-medium text-error-ink hover:bg-error/10"
        >
          <IconTrash size={14} />
          删除
        </button>
      </div>
    );

  return (
    <>
      <section className="mt-6 rounded-lg border border-border">
        <header className="flex flex-wrap items-center gap-3 px-4 py-3">
          <h2 className="text-section font-semibold text-ink">文档列表</h2>

          <div className="ml-auto flex items-center gap-2">
            <div className="flex h-8 items-center gap-2 rounded-md border border-control-border bg-canvas px-2 focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent/25">
              <span className="text-ink-secondary">
                <IconSearch size={16} />
              </span>
              <label className="flex items-center">
                <span className="sr-only">搜索文件名</span>
                <input
                  value={query}
                  onChange={(event) => {
                    onQueryChange(event.target.value);
                  }}
                  placeholder="搜索文件名..."
                  className="w-[180px] border-0 bg-transparent text-dense text-ink outline-none"
                />
              </label>
              {query.length > 0 ? (
                <button
                  type="button"
                  aria-label="清除搜索"
                  onClick={() => {
                    onQueryChange("");
                  }}
                  className="text-label text-ink-secondary hover:text-ink"
                >
                  <IconClose size={14} />
                </button>
              ) : null}
            </div>

            <Menu.Root>
              <Menu.Trigger
                aria-label={`筛选：${FILTER_LABEL[filter]}`}
                title={FILTER_LABEL[filter]}
                className={`flex h-8 w-8 items-center justify-center rounded-md border tint ${
                  filter === "all"
                    ? "border-border text-ink-secondary hover:bg-surface-hover hover:text-ink"
                    : "border-accent bg-accent-soft text-accent-strong"
                }`}
              >
                <IconFilter size={16} />
              </Menu.Trigger>
              <Menu.Portal>
                <Menu.Positioner side="bottom" align="end" sideOffset={6} collisionPadding={12}>
                  <Menu.Popup className="min-w-[160px] rounded-lg bg-float p-1 shadow-popover">
                    {(Object.keys(FILTER_LABEL) as readonly StatusFilter[]).map((key) => (
                      <Menu.Item
                        key={key}
                        onClick={() => {
                          onFilterChange(key);
                        }}
                        className="flex h-8 cursor-default items-center gap-2 rounded-md px-2 text-dense text-ink outline-none data-[highlighted]:bg-surface-hover"
                      >
                        <span className="w-3 text-accent-strong">
                          {key === filter ? <IconCheck size={12} /> : null}
                        </span>
                        {FILTER_LABEL[key]}
                      </Menu.Item>
                    ))}
                  </Menu.Popup>
                </Menu.Positioner>
              </Menu.Portal>
            </Menu.Root>
          </div>
        </header>

        {selected.length > 0 ? (
          <div className="hidden flex-wrap items-center gap-3 border-t border-divider bg-accent-soft px-4 py-2 md:flex">
            <span className="text-label tabular-nums text-ink">已选 {selected.length} 项</span>
            <button
              type="button"
              onClick={() => {
                onSelectionChange([]);
              }}
              className="text-label text-ink-secondary hover:text-ink"
            >
              取消选择
            </button>
            <button
              type="button"
              onClick={() => {
                onReparseSelection();
              }}
              className="ml-auto flex h-7 items-center rounded-md px-3 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink"
            >
              批量解析
            </button>
            <button
              type="button"
              onClick={() => {
                onRequestDeleteSelection();
              }}
              className="flex h-7 items-center rounded-md px-3 text-label font-medium text-error-ink tint hover:bg-error/10"
            >
              删除所选
            </button>
          </div>
        ) : null}

        {renderListBody() ?? (
          <DocumentTable
            rows={rows}
            visible={visible}
            selected={selected}
            allVisibleSelected={allVisibleSelected}
            onSelectionChange={onSelectionChange}
            onReparse={onReparse}
            onOpenSheet={onOpenSheet}
            onRequestDelete={onRequestDelete}
            onOpenDocument={onOpenDocument}
          />
        )}
      </section>

      {bulkBar}
    </>
  );
}
