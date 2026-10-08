import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { MotionConfig } from "framer-motion";
import { RouterProvider, createRouter, type ErrorComponentProps } from "@tanstack/react-router";
import { queryClient } from "../app/query";
import { FailureNotice } from "../components/failure-notice";
import { SkeletonLines } from "../components/skeleton";
import { rootRoute } from "../routes/__root";
import { rootRoutes } from "../routes/app-routes";
import "../styles/theme.css";

const routeTree = rootRoute.addChildren(rootRoutes);

/** 路由代码块异步加载中的占位骨架屏。 */
function RoutePending(): ReactNode {
  return (
    <div className="mx-auto w-full max-w-[1240px] px-6 py-6">
      <SkeletonLines lines={6} />
    </div>
  );
}

/** 页面加载失败时的降级展示与重试引导。 */
function RouteFailure({ error }: ErrorComponentProps): ReactNode {
  return (
    <div className="mx-auto w-full max-w-[1240px] px-6 py-6">
      <FailureNotice
        title="这个页面没有加载出来"
        detail={error instanceof Error ? error.message : String(error)}
        action={
          <button
            type="button"
            onClick={() => {
              window.location.reload();
            }}
            className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
          >
            重新加载
          </button>
        }
      />
    </div>
  );
}

// 初始化全局路由实例，注入 React Query 客户端上下文
const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: "intent",
  defaultPreloadStaleTime: 0,
  defaultPendingComponent: RoutePending,
  defaultErrorComponent: RouteFailure,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const container = document.getElementById("root");
if (container === null) {
  throw new Error("index.html has no #root element");
}

createRoot(container).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <RouterProvider router={router} />
    </MotionConfig>
  </StrictMode>,
);
