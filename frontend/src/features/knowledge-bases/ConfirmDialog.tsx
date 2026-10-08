import { Dialog } from "@base-ui/react/dialog";
import type { ReactNode } from "react";

interface ConfirmDialogProps {
  readonly open: boolean;
  readonly title: string;
  readonly description: ReactNode;
  readonly confirmLabel: string;
  readonly notice?: ReactNode;
  readonly onOpenChange: (open: boolean) => void;
  readonly onConfirm: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  notice,
  onOpenChange,
  onConfirm,
}: ConfirmDialogProps): ReactNode {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-[var(--scrim)]" />
        <Dialog.Viewport className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <Dialog.Popup className="w-[440px] max-w-full rounded-lg bg-float p-5 shadow-dialog">
            <Dialog.Title className="text-section font-semibold text-ink">{title}</Dialog.Title>
            <Dialog.Description className="mt-1 text-dense text-ink-secondary">
              {description}
            </Dialog.Description>
            <div className="mt-5 flex items-center gap-3">
              {notice ?? null}
              <div className="ml-auto flex gap-2">
                <Dialog.Close className="h-8 rounded-md px-3 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink">
                  取消
                </Dialog.Close>
                <button
                  type="button"
                  onClick={onConfirm}
                  className="h-8 rounded-md border border-error px-4 text-label font-medium text-error-ink tint hover:bg-error/10"
                >
                  {confirmLabel}
                </button>
              </div>
            </div>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
