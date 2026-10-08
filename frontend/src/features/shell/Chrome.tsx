/**
 * 双工作区共享全局外壳部件
 *
 * 包含品牌标识、深浅主题切换与全局 Command Palette（文档与功能快速跳转）。
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { useNavigate } from "@tanstack/react-router";
import {
  BrandMark,
  IconCog,
  IconDatabase,
  IconDocument,
  IconFileSearch,
  IconGauge,
  IconLayers,
  IconMoon,
  IconPipeline,
  IconSearch,
  IconSliders,
  IconSun,
} from "../../components/icons";
import { useDocumentCatalogue } from "../documents/api";
import { CHAT_PATH, CONSOLE_PATHS } from "./paths";

/** 外壳通用图标按钮样式 */
export const ICON_BUTTON =
  "flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-secondary tint hover:bg-surface-hover hover:text-ink";

const THEME_KEY = "rag-theme";

/** 亮色 / 暗色主题管理 hook，自动持久化至 localStorage */
export function useTheme(): { readonly theme: "light" | "dark"; readonly toggle: () => void } {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try {
      return window.localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
    } catch {
      return "light";
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      window.localStorage.setItem(THEME_KEY, theme);
    } catch {
      // 存储受限时降级为内存会话状态
    }
  }, [theme]);

  return {
    theme,
    toggle: () => {
      setTheme((current) => (current === "dark" ? "light" : "dark"));
    },
  };
}

export function Brand({ tagline = false }: { readonly tagline?: boolean }): ReactNode {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <BrandMark size={26} />
      <span className="min-w-0">
        <span className="block truncate text-dense leading-tight font-semibold text-ink">
          ClauseRAG
        </span>
        {tagline ? (
          <span className="block truncate text-label text-ink-secondary">
            美国商业合同审查与法务资产管理
          </span>
        ) : null}
      </span>
    </span>
  );
}

export function ThemeToggle({
  theme,
  onToggle,
}: {
  readonly theme: "light" | "dark";
  readonly onToggle: () => void;
}): ReactNode {
  return (
    <button
      type="button"
      aria-label={theme === "dark" ? "切换到浅色" : "切换到深色"}
      title={theme === "dark" ? "浅色" : "深色"}
      onClick={onToggle}
      className={ICON_BUTTON}
    >
      {theme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
    </button>
  );
}

interface NavigationAction {
  readonly id: string;
  readonly title: string;
  readonly path: string;
  readonly category: string;
  readonly icon: ReactNode;
}

const NAV_ACTIONS: readonly NavigationAction[] = [
  {
    id: "nav-chat",
    title: "工作台",
    path: CHAT_PATH,
    category: "核心工作区",
    icon: <IconFileSearch size={15} />,
  },
  {
    id: "nav-dash",
    title: "法务资产看板",
    path: CONSOLE_PATHS.dashboard,
    category: "控制台",
    icon: <IconLayers size={15} />,
  },
  {
    id: "nav-kb",
    title: "商业合同知识库",
    path: CONSOLE_PATHS.knowledgeBases,
    category: "控制台",
    icon: <IconDatabase size={15} />,
  },
  {
    id: "nav-docs",
    title: "文档与摄取流水线",
    path: CONSOLE_PATHS.documents,
    category: "控制台",
    icon: <IconDocument size={15} />,
  },
  {
    id: "nav-jobs",
    title: "摄取流水线任务监控",
    path: CONSOLE_PATHS.jobs,
    category: "编排与调试",
    icon: <IconPipeline size={15} />,
  },
  {
    id: "nav-retrieval",
    title: "两通道检索与重排调试",
    path: CONSOLE_PATHS.retrieval,
    category: "编排与调试",
    icon: <IconGauge size={15} />,
  },
  {
    id: "nav-models",
    title: "模型与向量参数配置",
    path: CONSOLE_PATHS.models,
    category: "系统基础设施",
    icon: <IconSliders size={15} />,
  },
  {
    id: "nav-sys",
    title: "系统健康状态与参数",
    path: CONSOLE_PATHS.system,
    category: "系统基础设施",
    icon: <IconCog size={15} />,
  },
];

/** 全局指令与文档快速搜索弹窗（Command Palette） */
export function GlobalSearchDialog({
  open,
  onOpenChange,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}): ReactNode {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  // 仅在对话框打开时加载全量文档目录
  const catalogue = useDocumentCatalogue(open);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onOpenChange, open]);

  const actionResults = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle.length === 0) {
      return NAV_ACTIONS.slice(0, 4);
    }
    return NAV_ACTIONS.filter(
      (action) =>
        action.title.toLowerCase().includes(needle) ||
        action.category.toLowerCase().includes(needle) ||
        action.path.toLowerCase().includes(needle),
    );
  }, [query]);

  const documentResults = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle.length === 0
      ? catalogue.entries.slice(0, 10)
      : catalogue.entries.filter((entry) => entry.document.title.toLowerCase().includes(needle));
  }, [catalogue.entries, query]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-[var(--scrim)]" />
        <Dialog.Viewport className="fixed inset-0 z-50 flex items-start justify-center p-6 pt-[12vh]">
          <Dialog.Popup
            className="w-[580px] max-w-full rounded-xl bg-float shadow-dialog border border-black/[0.08] dark:border-white/[0.1] overflow-hidden"
            aria-label="全局指令与文档检索"
          >
            <Dialog.Title className="sr-only">全局指令与文档检索</Dialog.Title>
            <div className="flex items-center gap-2 border-b border-divider px-3.5 bg-surface/30">
              <span className="text-ink-secondary">
                <IconSearch size={16} />
              </span>
              <input
                autoFocus
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                }}
                placeholder="搜索文档、法务功能或快速跳转 (支持 Ctrl/⌘ + K)..."
                className="h-11 flex-1 border-0 bg-transparent text-body text-ink outline-none"
              />
              <kbd className="hidden sm:inline-block rounded border border-border px-1.5 py-0.5 text-[10px] font-mono text-ink-muted">
                ESC 关闭
              </kbd>
            </div>

            <div className="max-h-[380px] overflow-y-auto p-1.5">
              {actionResults.length > 0 ? (
                <div className="mb-2">
                  <span className="px-2 pt-1 pb-1 block text-[11px] font-semibold text-ink-muted tracking-wider">
                    功能与工作区跳转
                  </span>
                  <ul className="flex flex-col gap-0.5">
                    {actionResults.map((action) => (
                      <li key={action.id}>
                        <button
                          type="button"
                          onClick={() => {
                            onOpenChange(false);
                            void navigate({ to: action.path });
                          }}
                          className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left tint hover:bg-surface-hover"
                        >
                          <span className="text-accent-strong">{action.icon}</span>
                          <span className="min-w-0 flex-1 truncate text-dense text-ink font-medium">
                            {action.title}
                          </span>
                          <span className="shrink-0 text-[11px] text-ink-secondary">
                            {action.category}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div>
                <span className="px-2 pt-1 pb-1 block text-[11px] font-semibold text-ink-muted tracking-wider border-t border-divider mt-1">
                  合同与法务文档
                </span>
                <ul className="flex flex-col gap-0.5">
                  {catalogue.pending ? (
                    <li className="px-2 py-4 text-center text-dense text-ink-secondary">
                      正在读取文档目录…
                    </li>
                  ) : documentResults.length === 0 ? (
                    <li className="px-2 py-4 text-center text-dense text-ink-secondary">
                      没有匹配「{query}」的合同文档。
                    </li>
                  ) : (
                    documentResults.map((entry) => (
                      <li key={entry.document.id}>
                        <button
                          type="button"
                          onClick={() => {
                            onOpenChange(false);
                            void navigate({
                              to: CONSOLE_PATHS.documents,
                              search: { doc: entry.document.id },
                            });
                          }}
                          className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left tint hover:bg-surface-hover"
                        >
                          <span className="text-ink-secondary">
                            <IconDocument size={15} />
                          </span>
                          <span className="min-w-0 flex-1 truncate text-dense text-ink">
                            {entry.document.title}
                          </span>
                          <span className="shrink-0 text-[11px] text-ink-secondary">
                            {entry.knowledgeBaseName}
                          </span>
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              </div>
            </div>

            <p className="border-t border-divider px-3.5 py-2 text-label text-ink-secondary bg-surface/20 flex justify-between items-center">
              <span>
                {catalogue.error ??
                  `已索引 ${String(catalogue.entries.length)} 份文档 · 全部知识库检索`}
              </span>
              <span className="font-mono text-[10px] text-ink-muted">
                ClauseRAG Command Palette
              </span>
            </p>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function SearchTrigger({ onOpen }: { readonly onOpen: () => void }): ReactNode {
  return (
    <button
      type="button"
      aria-label="全局搜索 (Ctrl/⌘ + K)"
      title="全局搜索 (Ctrl/⌘ + K)"
      onClick={onOpen}
      className={`${ICON_BUTTON} relative`}
    >
      <IconSearch size={17} />
    </button>
  );
}
