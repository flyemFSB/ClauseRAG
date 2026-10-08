/**
 * 顶栏双工作区切换组件
 *
 * 两个工作区各自一个入口，没有键盘快捷键：全局监听会抢走浏览器与输入法的组合键，而这里的切换本来
 * 就在顶栏一眼可见。
 */

import type { ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import { IconChat, IconGrid } from "../../components/icons";
import { CHAT_PATH, CONSOLE_PATHS, isConsolePath } from "./paths";

const SWITCHER_CONTAINER =
  "flex items-center gap-0.5 rounded-md border border-border/70 bg-surface/70 p-0.5 shadow-xs";
const ITEM =
  "flex h-7 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-dense font-medium tint transition-colors sm:px-2.5";
const ITEM_ACTIVE =
  "bg-canvas text-ink shadow-xs border border-border/50 font-semibold dark:bg-surface-hover dark:border-border";
const ITEM_IDLE = "text-ink-secondary hover:bg-surface-hover hover:text-ink";

export function WorkspaceSwitcher(): ReactNode {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const inConsole = isConsolePath(pathname);

  return (
    <nav aria-label="工作区" className={SWITCHER_CONTAINER}>
      <Link
        to={CHAT_PATH}
        aria-current={inConsole ? undefined : "page"}
        aria-label="工作台"
        title="工作台"
        className={`${ITEM} ${inConsole ? ITEM_IDLE : ITEM_ACTIVE}`}
      >
        <IconChat size={14} />
        <span className={`${inConsole ? "hidden sm:inline" : ""}`}>工作台</span>
      </Link>
      <Link
        to={CONSOLE_PATHS.dashboard}
        aria-current={inConsole ? "page" : undefined}
        aria-label="控制台"
        title="控制台"
        className={`${ITEM} ${inConsole ? ITEM_ACTIVE : ITEM_IDLE}`}
      >
        <IconGrid size={14} />
        <span className={`${inConsole ? "" : "hidden sm:inline"}`}>控制台</span>
      </Link>
    </nav>
  );
}
