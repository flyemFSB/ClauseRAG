import { useState, type ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";

/* — creating and renaming a knowledge base —————————————————————— */

export function KnowledgeBaseNameDialog({
  title,
  confirmLabel,
  initial,
  pending,
  onOpenChange,
  onSubmit,
}: {
  readonly title: string;
  readonly confirmLabel: string;
  readonly initial: string;
  readonly pending: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onSubmit: (name: string) => void;
}): ReactNode {
  const [name, setName] = useState(initial);

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        onOpenChange(open);
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-[var(--scrim)]" />
        <Dialog.Viewport className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <Dialog.Popup className="w-[420px] max-w-full rounded-lg bg-float p-5 shadow-dialog">
            <Dialog.Title className="text-section font-semibold text-ink">{title}</Dialog.Title>
            <Dialog.Description className="mt-1 text-dense text-ink-secondary">
              知识库是一次检索的范围：会话在它里面创建，文档上传到它里面。名称 1–200 字。
            </Dialog.Description>
            <label className="mt-4 flex flex-col gap-1">
              <span className="text-label font-medium text-ink-secondary">名称</span>
              <input
                value={name}
                autoFocus
                maxLength={200}
                onChange={(event) => {
                  setName(event.target.value);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && name.trim().length > 0) {
                    event.preventDefault();
                    onSubmit(name.trim());
                  }
                }}
                className="h-8 rounded-md border border-control-border bg-canvas px-2 text-dense text-ink focus:border-accent focus:ring-[3px] focus:ring-accent/25 focus:outline-none"
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <Dialog.Close className="h-8 rounded-md px-3 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink">
                取消
              </Dialog.Close>
              <button
                type="button"
                disabled={name.trim().length === 0 || pending}
                onClick={() => {
                  onSubmit(name.trim());
                }}
                className="h-8 rounded-md bg-accent-strong px-4 text-label font-medium text-canvas tint enabled:hover:bg-accent disabled:opacity-40"
              >
                {pending ? "处理中…" : confirmLabel}
              </button>
            </div>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
