import type { Dispatch, ReactNode, SetStateAction } from "react";

import { IconDocument, IconEllipsis } from "../../components/icons";
import { StatusBadge } from "../ingestion-jobs/IngestionStatus";
import { CELL, HEAD_CELL, type Row } from "./rows";
import { RowActions } from "./RowActions";

interface DocumentTableProps {
  readonly rows: readonly Row[];
  readonly visible: readonly Row[];
  readonly selected: readonly string[];
  readonly allVisibleSelected: boolean;
  readonly onSelectionChange: Dispatch<SetStateAction<readonly string[]>>;
  readonly onReparse: (versionId: string | null) => void;
  readonly onOpenSheet: (row: Row) => void;
  readonly onRequestDelete: (documentId: string) => void;
  readonly onOpenDocument: (documentId: string) => void;
}

export function DocumentTable({
  rows,
  visible,
  selected,
  allVisibleSelected,
  onSelectionChange,
  onReparse,
  onOpenSheet,
  onRequestDelete,
  onOpenDocument,
}: DocumentTableProps): ReactNode {
  return (
    <>
      <div className="hidden overflow-x-auto border-t border-border md:block">
        <table className="w-full border-collapse">
          <thead>
            <tr className="h-10 bg-surface">
              <th className="w-10 pl-3">
                <input
                  type="checkbox"
                  aria-label="选择本页全部文档"
                  checked={allVisibleSelected}
                  onChange={() => {
                    onSelectionChange(
                      allVisibleSelected ? [] : visible.map((row) => row.document.id),
                    );
                  }}
                  className="h-4 w-4 accent-[var(--color-accent)]"
                />
              </th>
              <th className={HEAD_CELL}>文件名</th>
              <th className={`${HEAD_CELL} w-[90px]`}>类型</th>
              <th className={`${HEAD_CELL} w-[100px] text-right`}>大小</th>
              <th className={`${HEAD_CELL} w-[160px]`}>上传时间</th>
              <th className={`${HEAD_CELL} w-[150px]`}>状态</th>
              <th className={`${HEAD_CELL} w-[56px] text-right`}>操作</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-dense text-ink-secondary">
                  没有符合当前搜索与筛选条件的文档。
                </td>
              </tr>
            ) : (
              visible.map((row) => {
                const isSelected = selected.includes(row.document.id);
                return (
                  <tr
                    key={row.document.id}
                    className={`h-10 border-t border-divider ${isSelected ? "bg-accent-soft" : "hover:bg-surface"}`}
                  >
                    <td className="pl-3">
                      <input
                        type="checkbox"
                        aria-label={`选择 ${row.document.title}`}
                        checked={isSelected}
                        onChange={() => {
                          onSelectionChange((current) =>
                            current.includes(row.document.id)
                              ? current.filter((id) => id !== row.document.id)
                              : [...current, row.document.id],
                          );
                        }}
                        className="h-4 w-4 accent-[var(--color-accent)]"
                      />
                    </td>
                    <td className={CELL}>
                      <span className="flex items-center gap-2">
                        <span className="text-ink-secondary">
                          <IconDocument size={16} />
                        </span>
                        <span className="truncate">{row.document.title}</span>
                      </span>
                    </td>
                    <td className={`${CELL} text-ink-secondary`}>{row.kind}</td>
                    <td className={`${CELL} text-right tabular-nums text-ink-secondary`}>
                      {row.size}
                    </td>
                    <td className={`${CELL} tabular-nums text-ink-secondary`}>{row.uploadedAt}</td>
                    <td className={CELL}>
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="px-3 text-right">
                      <RowActions
                        row={row}
                        onReparse={() => {
                          if (row.version !== null) {
                            onReparse(row.version?.id ?? null);
                          }
                        }}
                        onOpenSheet={onOpenSheet}
                        onDelete={() => {
                          onRequestDelete(row.document.id);
                        }}
                      />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* 移动端视图：单卡片展示与底部操作 */}
      <ul className="border-t border-border md:hidden">
        {visible.length === 0 ? (
          <li className="px-4 py-8 text-center text-dense text-ink-secondary">
            没有符合当前搜索与筛选条件的文档。
          </li>
        ) : (
          visible.map((row) => {
            const isSelected = selected.includes(row.document.id);
            return (
              <li
                key={row.document.id}
                className={`border-t border-divider p-3 first:border-t-0 ${isSelected ? "bg-accent-soft" : ""}`}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    aria-label={`选择 ${row.document.title}`}
                    checked={isSelected}
                    onChange={() => {
                      onSelectionChange((current) =>
                        current.includes(row.document.id)
                          ? current.filter((id) => id !== row.document.id)
                          : [...current, row.document.id],
                      );
                    }}
                    className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-accent)]"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="flex items-start gap-2 text-dense font-medium text-ink">
                      <span className="mt-0.5 shrink-0 text-ink-secondary">
                        <IconDocument size={16} />
                      </span>
                      <span className="min-w-0 flex-1">{row.document.title}</span>
                    </p>
                    <p className="mt-1 text-label tabular-nums text-ink-secondary">
                      {row.kind} · {row.size} · {row.uploadedAt}
                    </p>
                    <div className="mt-2 flex items-center gap-2">
                      <StatusBadge status={row.status} />
                    </div>
                    <div className="mt-2 flex items-center gap-1 border-t border-divider pt-2">
                      <button
                        type="button"
                        onClick={() => {
                          onOpenDocument(row.document.id);
                        }}
                        className="flex h-7 items-center rounded-md px-2 text-label font-medium text-ink-secondary hover:bg-surface-hover hover:text-ink"
                      >
                        查看解析进度
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (row.version !== null) {
                            onReparse(row.version?.id ?? null);
                          }
                        }}
                        className="flex h-7 items-center rounded-md px-2 text-label font-medium text-ink-secondary hover:bg-surface-hover hover:text-ink"
                      >
                        重新解析
                      </button>
                      <button
                        type="button"
                        aria-label={`${row.document.title} 的更多操作`}
                        onClick={() => {
                          onOpenSheet(row);
                        }}
                        className="ml-auto flex h-7 w-7 items-center justify-center rounded-md text-ink-secondary hover:bg-surface-hover hover:text-ink"
                      >
                        <IconEllipsis size={16} />
                      </button>
                    </div>
                  </div>
                </div>
              </li>
            );
          })
        )}
      </ul>

      <footer className="border-t border-divider px-4 py-2 text-label tabular-nums text-ink-secondary">
        显示 {visible.length} / {rows.length} 个文档
      </footer>
    </>
  );
}
