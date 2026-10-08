import { Drawer } from "@base-ui/react/drawer";
import type { ReactNode } from "react";

import type { Row } from "./rows";

interface MobileActionsDrawerProps {
  readonly row: Row | null;
  readonly onClose: () => void;
  readonly onOpenDocument: (documentId: string) => void;
  readonly onReparse: (versionId: string) => void;
  readonly onRequestDelete: (documentId: string) => void;
}

export function MobileActionsDrawer({
  row,
  onClose,
  onOpenDocument,
  onReparse,
  onRequestDelete,
}: MobileActionsDrawerProps): ReactNode {
  return (
    <Drawer.Root
      open={row !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <Drawer.Portal>
        <Drawer.Backdrop className="fixed inset-0 z-40 bg-[var(--scrim)] md:hidden" />
        <Drawer.Viewport className="fixed inset-0 z-50 flex items-end md:hidden">
          <Drawer.Popup className="w-full rounded-t-lg bg-float p-4 shadow-dialog outline-none focus-visible:shadow-none">
            <div className="mx-auto mb-3 h-1 w-9 rounded-full bg-ink-muted" />
            <Drawer.Title className="truncate text-dense font-medium text-ink">
              {row?.document.title}
            </Drawer.Title>
            <ul className="mt-3 flex flex-col">
              <li>
                <button
                  type="button"
                  onClick={() => {
                    const id = row?.document.id;
                    onClose();
                    if (id !== undefined) {
                      onOpenDocument(id);
                    }
                  }}
                  className="flex h-10 w-full items-center rounded-md px-2 text-left text-dense text-ink hover:bg-surface-hover"
                >
                  查看解析进度
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => {
                    const versionId = row?.version?.id;
                    onClose();
                    if (versionId !== undefined) {
                      onReparse(versionId);
                    }
                  }}
                  className="flex h-10 w-full items-center rounded-md px-2 text-left text-dense text-ink hover:bg-surface-hover"
                >
                  重新解析
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => {
                    const id = row?.document.id;
                    onClose();
                    if (id !== undefined) {
                      onRequestDelete(id);
                    }
                  }}
                  className="mt-2 flex h-10 w-full items-center rounded-md px-2 text-left text-dense text-error-ink hover:bg-error/10"
                >
                  删除文档
                </button>
              </li>
            </ul>
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
