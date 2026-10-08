/**
 * 应用路由树与工作区路由分发配置
 *
 * 划分为合同审查对话工作区（ChatShell）与法务资产控制台（ConsoleShell），
 * 各业务模块按异步路由级代码切分（lazyRouteComponent）。
 *
 * 平台以展示为目的上线，没有登录页也没有路由守卫（ADR-0033），两个工作区直接可用。
 */

import { type ReactNode } from "react";
import { Outlet, createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { ChatShell } from "../features/shell/ChatShell";
import { ConsoleShell } from "../features/shell/ConsoleShell";
import { CHAT_PATH, CONSOLE_PATHS } from "../features/shell/paths";
import { rootRoute } from "./__root";

function ChatLayout(): ReactNode {
  return (
    <ChatShell>
      <Outlet />
    </ChatShell>
  );
}

export const chatLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "chat-shell",
  component: ChatLayout,
});

function ConsoleLayout(): ReactNode {
  return (
    <ConsoleShell>
      <Outlet />
    </ConsoleShell>
  );
}

export const consoleLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "console-shell",
  component: ConsoleLayout,
});

/** 根路径默认重定向至合同审查工作区 */
export const indexRedirectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: CHAT_PATH });
  },
});

export const chatRoute = createRoute({
  getParentRoute: () => chatLayoutRoute,
  path: CHAT_PATH,
  component: lazyRouteComponent(() => import("../features/chat/ChatModule"), "ChatModule"),
});

export const dashboardRoute = createRoute({
  getParentRoute: () => consoleLayoutRoute,
  path: CONSOLE_PATHS.dashboard,
  component: lazyRouteComponent(() => import("../features/dashboard/Dashboard"), "Dashboard"),
});

export const knowledgeBasesRoute = createRoute({
  getParentRoute: () => consoleLayoutRoute,
  path: CONSOLE_PATHS.knowledgeBases,
  component: lazyRouteComponent(
    () => import("../features/knowledge-bases/KnowledgeBaseOverview"),
    "KnowledgeBaseOverview",
  ),
});

export const documentsRoute = createRoute({
  getParentRoute: () => consoleLayoutRoute,
  path: CONSOLE_PATHS.documents,
  // 校验并解析当前选中的文档 ID 查询参数
  validateSearch: (search: Record<string, unknown>): { doc?: string } => ({
    doc: typeof search["doc"] === "string" ? search["doc"] : undefined,
  }),
  component: lazyRouteComponent(
    () => import("../features/documents/DocumentManagement"),
    "DocumentManagement",
  ),
});

export const jobsRoute = createRoute({
  getParentRoute: () => consoleLayoutRoute,
  path: CONSOLE_PATHS.jobs,
  component: lazyRouteComponent(() => import("../features/ingestion-jobs/JobsPage"), "JobsPage"),
});

export const retrievalRoute = createRoute({
  getParentRoute: () => consoleLayoutRoute,
  path: CONSOLE_PATHS.retrieval,
  component: lazyRouteComponent(
    () => import("../features/retrieval-debug/RetrievalDebugPage"),
    "RetrievalDebugPage",
  ),
});

export const modelsRoute = createRoute({
  getParentRoute: () => consoleLayoutRoute,
  path: CONSOLE_PATHS.models,
  component: lazyRouteComponent(
    () => import("../features/settings/ModelConfigPage"),
    "ModelConfigPage",
  ),
});

export const systemRoute = createRoute({
  getParentRoute: () => consoleLayoutRoute,
  path: CONSOLE_PATHS.system,
  component: lazyRouteComponent(
    () => import("../features/settings/SystemSettingsPage"),
    "SystemSettingsPage",
  ),
});

export const moduleRoutes = [
  chatLayoutRoute.addChildren([chatRoute]),
  consoleLayoutRoute.addChildren([
    dashboardRoute,
    knowledgeBasesRoute,
    documentsRoute,
    jobsRoute,
    retrievalRoute,
    modelsRoute,
    systemRoute,
  ]),
] as const;

export const rootRoutes = [indexRedirectRoute, ...moduleRoutes] as const;
