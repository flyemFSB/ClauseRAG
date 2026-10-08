import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "../lib/api";

/** 全局 React Query 客户端实例，配置有限瞬态错误重试与缓存策略。 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => failureCount < 2 && isTransient(error),
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 4000),
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
    mutations: { retry: false },
  },
});

/** 判断请求错误是否属于网络或超时等可重试的瞬态错误。 */
export function isTransient(error: unknown): boolean {
  return error instanceof ApiError && (error.kind === "network" || error.kind === "timeout");
}
