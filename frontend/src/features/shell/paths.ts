/**
 * 前端应用路由路径与快捷键定义
 *
 * 划分为合同审查对话工作区（`/chat`）与法务资产控制台（`/admin/*`）。
 *
 * 平台以展示为目的上线，没有登录页（ADR-0033）。
 */

export const CHAT_PATH = "/chat";

export const CONSOLE_PATHS = {
  /** 控制台总览：知识资产与运行健康状况 */
  dashboard: "/admin/dashboard",
  knowledgeBases: "/admin/knowledge-bases",
  documents: "/admin/documents",
  /** 任务编排状态看板 */
  jobs: "/admin/jobs",
  /** 检索调试分析 */
  retrieval: "/admin/retrieval",
  models: "/admin/models",
  system: "/admin/system",
} as const;

export function isConsolePath(pathname: string): boolean {
  return pathname.startsWith("/admin");
}
