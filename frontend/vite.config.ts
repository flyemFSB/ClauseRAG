import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, lazyPlugins } from "vite-plus";

// 开发服务器反向代理：将两个后端进程聚合至同一源，避免跨域并统一网络出口。
// 依据 ADR-0020：Agent 运行时处理对话、流式回复与召回诊断；业务 API 处理其他通用管理接口。
// 匹配规则按声明顺序生效，特异路由需声明在通用捕获规则之前。
const apiOrigin = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";
const agentOrigin = process.env.AGENT_ORIGIN ?? "http://127.0.0.1:8001";

// Vite+ 工具链配置
export default defineConfig({
  server: {
    proxy: {
      // 知识库会话创建接口由 Agent 运行时提供；以 ^ 开头的键会被 Vite 解析为正则，必须置于通用 /api 规则前
      "^/api/v1/knowledge-bases/[^/]+/conversations$": {
        target: agentOrigin,
        changeOrigin: false,
      },
      "/api/v1/conversations": { target: agentOrigin, changeOrigin: false },
      "/api/v1/retrieval-debug": { target: agentOrigin, changeOrigin: false },
      "/api": { target: apiOrigin, changeOrigin: false },
      "/health": { target: apiOrigin, changeOrigin: false },
    },
  },
  lint: {
    plugins: ["react", "typescript", "oxc"],
    rules: {
      "react/rules-of-hooks": "error",
    },
    options: {
      typeAware: true,
      typeCheck: true,
    },
  },
  // 插件配置：React 快速刷新与 Tailwind v4 编译（样式由 src/styles/theme.css 单源驱动）。
  // lazyPlugins 保证在仅读取配置元数据的命令（如 vp check）下延迟加载。
  plugins: lazyPlugins(() => [react(), tailwindcss()]),
  // 路径别名：与 tsconfig 保持一致，映射 @/ 至 src/
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
