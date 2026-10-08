import { type ReactNode } from "react";
import { Menu } from "@base-ui/react/menu";
import { Link } from "@tanstack/react-router";
import { IconEllipsis } from "../../components/icons";
import { CONSOLE_PATHS } from "../shell/paths";
import type { Row } from "./rows";

/* — the row menu ——————————————————————————————————————————————— */

export function RowActions({
  row,
  onReparse,
  onOpenSheet,
  onDelete,
}: {
  readonly row: Row;
  readonly onReparse: () => void;
  readonly onOpenSheet: (row: Row) => void;
  readonly onDelete: () => void;
}): ReactNode {
  return (
    <Menu.Root>
      <Menu.Trigger
        aria-label={`${row.document.title} 的操作`}
        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-ink-secondary tint hover:bg-surface-hover hover:text-ink"
      >
        <IconEllipsis size={16} />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner side="bottom" align="end" sideOffset={6} collisionPadding={12}>
          <Menu.Popup className="min-w-[180px] rounded-lg bg-float p-1 shadow-popover">
            <Menu.LinkItem
              closeOnClick
              render={<Link to={CONSOLE_PATHS.documents} search={{ doc: row.document.id }} />}
              className="flex h-8 cursor-default items-center rounded-md px-2 text-dense text-ink outline-none data-[highlighted]:bg-surface-hover"
            >
              查看解析进度
            </Menu.LinkItem>
            <Menu.Item
              disabled={row.version === null}
              onClick={onReparse}
              className="flex h-8 cursor-default items-center rounded-md px-2 text-dense text-ink outline-none data-[highlighted]:bg-surface-hover data-[disabled]:opacity-50"
            >
              重新解析
            </Menu.Item>
            <Menu.Item
              onClick={() => {
                onOpenSheet(row);
              }}
              className="flex h-8 cursor-default items-center rounded-md px-2 text-dense text-ink outline-none data-[highlighted]:bg-surface-hover md:hidden"
            >
              更多操作
            </Menu.Item>
            <Menu.Item
              onClick={onDelete}
              className="flex h-8 cursor-default items-center rounded-md px-2 text-dense text-error-ink outline-none data-[highlighted]:bg-error/10"
            >
              删除文档
            </Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
