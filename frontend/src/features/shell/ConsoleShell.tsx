/**
 * 知识资产管理控制台外壳组件
 *
 * 采用与合同审查相同的独立浮动岛（Island）底层结构，集成左侧管理导航侧边栏、
 * 移动端抽屉导航、顶栏品牌标识、工作区切换器、全局搜索与主题切换。
 */

import { useState, type ReactNode } from "react";
import { Drawer } from "@base-ui/react/drawer";
import { Tooltip } from "@base-ui/react/tooltip";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  IconCog,
  IconDatabase,
  IconDocument,
  IconGauge,
  IconLayers,
  IconMenu,
  IconPipeline,
  IconSliders,
} from "../../components/icons";
import {
  Brand,
  GlobalSearchDialog,
  ICON_BUTTON,
  SearchTrigger,
  ThemeToggle,
  useTheme,
} from "./Chrome";
import { CONSOLE_PATHS } from "./paths";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

interface ConsoleEntry {
  readonly to: string;
  readonly label: string;
  readonly icon: ReactNode;
}

interface NavGroup {
  readonly title: string;
  readonly entries: readonly ConsoleEntry[];
}

const NAV_GROUPS: readonly NavGroup[] = [
  {
    title: "法务知识资产",
    entries: [
      { to: CONSOLE_PATHS.dashboard, label: "看板", icon: <IconLayers /> },
      { to: CONSOLE_PATHS.knowledgeBases, label: "知识库", icon: <IconDatabase /> },
      { to: CONSOLE_PATHS.documents, label: "文档与流水线", icon: <IconDocument /> },
    ],
  },
  {
    title: "任务与调试",
    entries: [
      { to: CONSOLE_PATHS.jobs, label: "摄取任务", icon: <IconPipeline /> },
      { to: CONSOLE_PATHS.retrieval, label: "检索调试", icon: <IconGauge /> },
    ],
  },
  {
    title: "系统基础设施",
    entries: [
      { to: CONSOLE_PATHS.models, label: "模型配置", icon: <IconSliders /> },
      { to: CONSOLE_PATHS.system, label: "系统设置", icon: <IconCog /> },
    ],
  },
];

const NAV_ITEM = "flex h-8 items-center gap-2 rounded-md px-2 text-dense font-medium tint";

function ConsoleNav({
  pathname,
  onNavigate,
}: {
  readonly pathname: string;
  readonly onNavigate?: () => void;
}): ReactNode {
  return (
    <nav className="flex flex-1 flex-col gap-3 px-2.5 pb-3" aria-label="管理模块">
      {NAV_GROUPS.map((group) => (
        <div key={group.title} className="flex flex-col gap-0.5">
          <span className="px-2 pt-1 pb-1 text-[11px] font-semibold text-ink-muted tracking-wider">
            {group.title}
          </span>
          {group.entries.map((entry) => {
            const active = pathname.startsWith(entry.to);
            return (
              <Link
                key={entry.to}
                to={entry.to}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={`${NAV_ITEM} ${
                  active
                    ? "bg-surface-hover text-ink font-semibold"
                    : "text-ink-secondary hover:bg-surface-hover hover:text-ink"
                }`}
              >
                {entry.icon}
                {entry.label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

export function ConsoleShell({ children }: { readonly children: ReactNode }): ReactNode {
  const { theme, toggle } = useTheme();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const [searchOpen, setSearchOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);

  return (
    <Tooltip.Provider>
      <div className="flex h-dvh flex-col bg-desk text-ink">
        <header className="flex h-13 shrink-0 items-center gap-2 px-2.5 sm:gap-3 sm:px-3">
          <button
            type="button"
            aria-label="打开管理导航"
            onClick={() => {
              setNavOpen(true);
            }}
            className={`${ICON_BUTTON} md:hidden`}
          >
            <IconMenu size={18} />
          </button>

          <span className="hidden min-w-0 sm:block">
            <Brand />
          </span>
          <span className="mx-1 hidden h-5 w-px bg-border sm:block" aria-hidden="true" />
          <WorkspaceSwitcher />

          <span className="ml-auto flex shrink-0 items-center gap-1">
            <SearchTrigger
              onOpen={() => {
                setSearchOpen(true);
              }}
            />
            <ThemeToggle theme={theme} onToggle={toggle} />
          </span>
        </header>

        <div className="min-h-0 flex-1 px-2 pb-2 sm:px-2.5 sm:pb-2.5">
          <div className="flex h-full min-h-0 overflow-hidden rounded-[var(--radius-island)] border border-island-edge bg-canvas shadow-island">
            <aside className="hidden w-[210px] shrink-0 flex-col border-r border-divider bg-rail md:flex">
              <div className="pt-3">
                <ConsoleNav pathname={pathname} />
              </div>
            </aside>

            <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-canvas">
              {children}
            </main>
          </div>
        </div>

        <Drawer.Root open={navOpen} onOpenChange={setNavOpen}>
          <Drawer.Portal>
            <Drawer.Backdrop className="fixed inset-0 z-40 bg-[var(--scrim)] md:hidden" />
            <Drawer.Viewport className="fixed inset-0 z-50 flex items-stretch md:hidden">
              <Drawer.Popup className="flex w-[260px] flex-col bg-rail shadow-dialog outline-none focus-visible:shadow-none">
                <div className="px-4 pt-4 pb-3">
                  <Brand tagline />
                </div>
                <div className="px-3 pb-2">
                  <WorkspaceSwitcher />
                </div>
                <ConsoleNav
                  pathname={pathname}
                  onNavigate={() => {
                    setNavOpen(false);
                  }}
                />
              </Drawer.Popup>
            </Drawer.Viewport>
          </Drawer.Portal>
        </Drawer.Root>

        <GlobalSearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
      </div>
    </Tooltip.Provider>
  );
}
