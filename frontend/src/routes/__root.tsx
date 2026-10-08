import { type ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";

interface RouterContext {
  readonly queryClient: QueryClient;
}

/**
 * 根路由布局组件
 *
 * 挂载全局 QueryClientProvider，确保路由导航守卫（beforeLoad）与各页面组件共享统一的服务端状态缓存。
 */
function RootLayout(): ReactNode {
  const { queryClient } = rootRoute.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <Outlet />
    </QueryClientProvider>
  );
}

export const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
});
