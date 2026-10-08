/**
 * 合同审查工作区外壳组件
 *
 * 采用独立浮动岛（Island）容器承载会话轨迹，集成历史会话栏（小屏幕抽屉式折叠）、
 * 顶栏品牌标识、工作区切换器与主题切换。
 */

import { useEffect, useState, type ReactNode } from "react";
import { Drawer } from "@base-ui/react/drawer";
import { Tooltip } from "@base-ui/react/tooltip";
import { IconMenu } from "../../components/icons";
import { ConversationRail } from "../chat/ConversationRail";
import { SessionProvider } from "../chat/sessions";
import { Brand, ICON_BUTTON, ThemeToggle, useTheme } from "./Chrome";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

export function ChatShell({ children }: { readonly children: ReactNode }): ReactNode {
  const { theme, toggle } = useTheme();
  const [railOpen, setRailOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if ((event.metaKey || event.ctrlKey) && event.key === "[") {
        event.preventDefault();
        setCollapsed((current) => !current);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  return (
    <SessionProvider>
      <Tooltip.Provider>
        <div className="flex h-dvh flex-col bg-desk text-ink">
          <header className="flex h-13 shrink-0 items-center gap-2 px-2.5 sm:gap-3 sm:px-3">
            <button
              type="button"
              aria-label="打开会话列表"
              onClick={() => {
                setRailOpen(true);
              }}
              className={`${ICON_BUTTON} lg:hidden`}
            >
              <IconMenu size={18} />
            </button>
            <span className="hidden min-w-0 sm:block">
              <Brand />
            </span>
            <span className="mx-1 hidden h-5 w-px bg-border sm:block" aria-hidden="true" />
            <WorkspaceSwitcher />
            <span className="ml-auto flex shrink-0 items-center gap-1">
              <ThemeToggle theme={theme} onToggle={toggle} />
            </span>
          </header>

          <div className="min-h-0 flex-1 px-2 pb-2 sm:px-2.5 sm:pb-2.5">
            <div className="flex h-full min-h-0 overflow-hidden rounded-[var(--radius-island)] border border-island-edge bg-canvas shadow-island">
              <aside
                className={`hidden shrink-0 flex-col border-r border-divider bg-rail transition-[width] duration-150 lg:flex ${
                  collapsed ? "w-[56px]" : "w-[260px]"
                }`}
              >
                <ConversationRail
                  collapsed={collapsed}
                  onToggleCollapse={() => {
                    setCollapsed((current) => !current);
                  }}
                />
              </aside>
              <div className="flex min-w-0 flex-1 flex-col">{children}</div>
            </div>
          </div>
        </div>

        <Drawer.Root open={railOpen} onOpenChange={setRailOpen}>
          <Drawer.Portal>
            <Drawer.Backdrop className="fixed inset-0 z-40 bg-[var(--scrim)] lg:hidden" />
            <Drawer.Viewport className="fixed inset-0 z-50 flex items-stretch lg:hidden">
              <Drawer.Popup className="flex w-[280px] flex-col bg-rail shadow-dialog outline-none focus-visible:shadow-none">
                <ConversationRail
                  onClose={() => {
                    setRailOpen(false);
                  }}
                />
              </Drawer.Popup>
            </Drawer.Viewport>
          </Drawer.Portal>
        </Drawer.Root>
      </Tooltip.Provider>
    </SessionProvider>
  );
}
