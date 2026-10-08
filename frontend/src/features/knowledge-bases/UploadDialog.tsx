import { type ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { IconDocument, IconInfo, IconTrash, IconUpload } from "../../components/icons";
import { formatBytes } from "../../lib/format";
import { type QueueItem, type Row } from "./rows";

/* — the upload dialog ——————————————————————————————————————————— */

export function UploadDialog({
  open,
  onOpenChange,
  knowledgeBaseName,
  rows,
  appendTo,
  onAppendToChange,
  queue,
  onAddFiles,
  onRemove,
  dragging,
  onDraggingChange,
  onUpload,
  uploading,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly knowledgeBaseName: string;
  readonly rows: readonly Row[];
  readonly appendTo: string;
  readonly onAppendToChange: (value: string) => void;
  readonly queue: readonly QueueItem[];
  readonly onAddFiles: (files: FileList | null) => void;
  readonly onRemove: (id: string) => void;
  readonly dragging: boolean;
  readonly onDraggingChange: (value: boolean) => void;
  readonly onUpload: () => void;
  readonly uploading: boolean;
}): ReactNode {
  const waiting = queue.filter((entry) => entry.state === "waiting").length;
  const finished = queue.filter((entry) => entry.state === "done").length;
  const failed = queue.filter(
    (entry) => entry.state === "failed" || entry.state === "rejected",
  ).length;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-[var(--scrim)]" />
        <Dialog.Viewport className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <Dialog.Popup className="w-[560px] max-w-full rounded-lg bg-float p-5 shadow-dialog">
            <Dialog.Title className="text-section font-semibold text-ink">上传文档</Dialog.Title>
            <Dialog.Description className="mt-1 text-dense text-ink-secondary">
              上传到「{knowledgeBaseName}」。解析、分块、嵌入与索引会在后台依次执行。
            </Dialog.Description>

            <label
              onDragOver={(event) => {
                event.preventDefault();
                onDraggingChange(true);
              }}
              onDragLeave={() => {
                onDraggingChange(false);
              }}
              onDrop={(event) => {
                event.preventDefault();
                onDraggingChange(false);
                onAddFiles(event.dataTransfer.files);
              }}
              className={`mt-4 flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center tint ${
                dragging ? "border-accent bg-accent-soft" : "border-control-border hover:bg-surface"
              }`}
            >
              <span className="text-ink-secondary">
                <IconUpload size={22} />
              </span>
              <span className="text-dense text-ink">
                将文件拖到这里，或<span className="text-accent-strong underline">选择文件</span>
              </span>
              <span className="text-label text-ink-secondary">
                支持 PDF、DOCX、PPTX、XLSX、TXT、Markdown、HTML 与图像；单文件不超过 100 MB
              </span>
              <input
                type="file"
                multiple
                aria-label="选择文件"
                onChange={(event) => {
                  onAddFiles(event.target.files);
                }}
                className="sr-only"
              />
            </label>

            {queue.length > 0 ? (
              <ul className="mt-3 flex max-h-[200px] flex-col gap-1 overflow-y-auto">
                {queue.map((item) => (
                  <li key={item.id} className="flex items-center gap-2 rounded-md bg-surface p-2">
                    <span className="shrink-0 text-ink-secondary">
                      <IconDocument size={16} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-dense text-ink">{item.file.name}</span>
                      <span className="mt-0.5 block text-label tabular-nums text-ink-secondary">
                        {formatBytes(item.file.size)} ·{" "}
                        {item.state === "waiting"
                          ? "等待上传"
                          : item.state === "uploading"
                            ? "上传中…"
                            : item.state === "done"
                              ? "已上传，解析已排队"
                              : "未上传"}
                      </span>
                      {item.reason === undefined ? null : (
                        <span className="mt-1 block text-label text-error-ink">
                          {item.reason} 这个文件不会被上传，其余文件不受影响。
                        </span>
                      )}
                    </span>
                    <button
                      type="button"
                      aria-label={`从队列移除 ${item.file.name}`}
                      onClick={() => {
                        onRemove(item.id);
                      }}
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-ink-secondary tint hover:bg-surface-hover hover:text-ink"
                    >
                      <IconTrash size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            {/* 目标文档选择：创建新文档或追加为已有文档的新版本 */}
            <label className="mt-3 flex flex-col gap-1">
              <span className="text-label font-medium text-ink-secondary">目标文档</span>
              <span className="flex items-center gap-2">
                <select
                  value={appendTo}
                  onChange={(event) => {
                    onAppendToChange(event.target.value);
                  }}
                  className="h-8 min-w-0 flex-1 rounded-md border border-control-border bg-canvas px-2 text-dense text-ink"
                >
                  <option value="">创建为新文档</option>
                  {rows.map((row) => (
                    <option key={row.document.id} value={row.document.id}>
                      追加为新版本：{row.document.title}
                    </option>
                  ))}
                </select>
              </span>
            </label>

            <p className="mt-3 flex items-start gap-2 text-label text-ink-secondary">
              <span className="mt-0.5 shrink-0">
                <IconInfo size={14} />
              </span>
              <span>
                上传请求体只有文件与可选的目标文档；分块策略是流水线的固定阶段，不接受每次上传的参数，
                因此这里没有「高级解析配置」。
              </span>
            </p>

            {failed > 0 || finished > 0 ? (
              <p className="mt-2 text-label tabular-nums text-ink-secondary">
                已上传 {finished} 个 · 失败 {failed} 个
              </p>
            ) : null}

            <div className="mt-4 flex justify-end gap-2">
              <Dialog.Close className="h-8 rounded-md px-3 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink">
                {finished > 0 && waiting === 0 ? "完成" : "取消"}
              </Dialog.Close>
              <button
                type="button"
                disabled={waiting === 0 || uploading}
                onClick={onUpload}
                className="h-8 rounded-md bg-accent-strong px-4 text-label font-medium text-canvas tint enabled:hover:bg-accent disabled:opacity-40"
              >
                {uploading ? "上传中…" : "开始上传"}
                {waiting > 0 && !uploading ? `（${String(waiting)}）` : ""}
              </button>
            </div>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
