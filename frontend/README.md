# 前端工程规范与架构说明

本项目基于 React 19 + TypeScript，运行于 Vite+（`vp`）工具链（Node 24、pnpm 12、单一 lockfile）。**视觉设计系统与页面编排规范**由系统设计白皮书统一管理（详见 `../DESIGN.md` 与 ADR-0006）；`src/styles/theme.css` 是视觉变量的唯一可执行定义（基于 Tailwind v4 原生 CSS 配置，无多余 `tailwind.config.*` 文件）。

前端各页面严格对接真实后端契约，代码内无任何硬编码伪数据。控制台指标基于后端返回的文档数据实时聚合计算，对话流基于 Agent 运行时真实 SSE 事件驱动；对于协议层尚未开放入口的非核心能力（如附件直接投递、全文阅读器、输入模式切换等），遵循 `DESIGN.md` 原则在界面原地明确标注未接入状态，不伪造返回结果。

---

## 目录结构

```text
src/
├── app/main.tsx            # 应用入口：组装路由树、挂载 Router、加载全局样式
├── routes/                 # 声明式路由定义（详见下方路由表）
├── components/             # 原子控件：图标库、骨架屏、状态指示器、缺省/错误提示、通用 Button
├── features/               # 业务特性模块（按业务领域内聚）
│   ├── shell/              # 双工作区外壳（审查外壳与控制台外壳）、公共导航栏及工作区切换器
│   ├── chat/               # 合同审查岛屿：会话管理、流式问答、引用溯源与证据检视台
│   ├── knowledge-bases/    # 控制台 · 知识库：度量统计、文档列表、上传入口、创建/重命名/删除
│   ├── documents/          # 控制台 · 文档与流水线：版本列表、阶段状态胶囊、解析产物查看
│   ├── ingestion-jobs/     # 异步摄取任务：阶段状态与重试操作
│   ├── retrieval-debug/    # 检索诊断调试：单轮检索通道召回、RRF 融合、重排打分、证据与上下文透视
│   ├── dashboard/          # 控制台 · 资产看板：实时度量指标与运行监控
│   └── settings/           # 控制台 · 模型配置 / 系统设置：实例运行参数与依赖就绪探针
├── lib/api.ts              # 网络传输封装：支持显式超时、取消与统一 ApiError 异常抛出
├── lib/sse.ts              # Agent 流式执行专属 SSE 客户端
├── lib/contract.ts         # 契约响应校验原语（在业务边界阻断畸变响应，杜绝静默失败）
├── lib/format.ts           # 统一业务度量格式化工具
├── styles/theme.css        # 全局设计 Token（Tailwind v4 主题变量及深色模式配置）
└── types/                  # 环境与全局类型声明
```

---

## 路由拓扑

| 路由路径                   | 对应视图与职责                                                                       |
| :------------------------- | :----------------------------------------------------------------------------------- |
| `/`                        | 根路径，自动重定向至 `/chat`                                                         |
| `/chat`                    | **合同审查工作区**：空状态欢迎页、对话流、行内引用定位及右侧证据溯源检视台           |
| `/admin/dashboard`         | **控制台 · 资产看板**：知识库存储分布、流水线执行情况与待人工介入列表                |
| `/admin/knowledge-bases`   | **控制台 · 知识库管理**：知识库 CRUD、度量概览、文档列表与批量操作                   |
| `/admin/documents`         | **控制台 · 文档与流水线**：支持通过 `?doc=` 选中具体文档，查看多版本及各处理阶段状态 |
| `/admin/jobs`              | **控制台 · 摄取任务**：各文档最新版本的五个处理阶段状态监控与单任务重试              |
| `/admin/retrieval`         | **控制台 · 检索调试**：单轮独立检索执行，全景透视双通道召回、RRF 融合与重排分值      |
| `/admin/models`, `/system` | **控制台 · 模型配置与系统设置**：展示进程启动配置快照及各外部依赖就绪报告            |

---

## 开发与校验命令

```powershell
pnpm exec vp check    # 执行代码格式化 (Oxfmt)、类型安全感知 Lint 及 TypeScript 检查
pnpm exec vp dev      # 启动开发服务器（自动反向代理双后端进程）
pnpm exec vp build    # 生产环境打包构建
pnpm exec vp test     # 执行单元测试与组件交互测试
```

从仓库根目录启动时，可直接通过 PowerShell 便捷脚本一键拉起容器、后端多进程及前端服务：

```powershell
pwsh scripts/dev.ps1            # 一键拉起基础设施容器、三个后端服务进程与前端 dev server
pwsh scripts/dev.ps1 -NoWorker  # 纯 UI 开发模式：跳过摄取流水线 Worker
pwsh scripts/dev.ps1 -Stop      # 依进程树安全停止本轮启动的所有实例
```

> **提示**：`vp dev` 默认仅绑定 `localhost`，访问 `http://localhost:5173` 即可，使用 `http://127.0.0.1:5173` 可能会被拒绝连接。

---

## 后端接口映射

| 业务模块         | 接口路由与规范                                                                                                                                                                                                                                           |
| :--------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **知识库**       | `GET/POST /knowledge-bases`, `GET/PATCH/DELETE /knowledge-bases/{id}`                                                                                                                                                                                    |
| **文档与流水线** | `GET /knowledge-bases/{id}/documents`, `POST` 同路径（multipart 上传，可选携带 `document_id`），`GET /documents/{id}`, `DELETE /documents/{id}`, `GET /document-versions/{id}`, `GET /document-versions/{id}/jobs`, `POST /document-versions/{id}/retry` |
| **合同审查问答** | `GET/POST /conversations`, `GET/PATCH/DELETE /conversations/{id}`, `POST /conversations/{id}/messages` (SSE 流式推流)                                                                                                                                    |
| **检索调试**     | `POST /retrieval-debug/query`                                                                                                                                                                                                                            |
| **系统设置**     | `GET /health/ready`                                                                                                                                                                                                                                      |

合同审查问答与检索诊断由 **Agent Runtime 进程**（8001）承载；其余资产管理与元数据操作由 **业务 API 进程**（8000）承载。平台不提供登录（ADR-0033），所有请求都是同一个平台主体。

---

## 双后端端口反向代理（ADR-0020）

架构上将后端 HTTP 接口按计算特性解耦为两个独立进程。开发服务器自动将二者反向代理至单一前端源，确保浏览器仅与统一源通信，避免跨域策略（CORS）复杂度：

| 路由前缀                                           | 代理目标进程                  | 环境变量覆盖   |
| :------------------------------------------------- | :---------------------------- | :------------- |
| `/api/v1/conversations`, `/api/v1/retrieval-debug` | Agent 运行时进程（端口 8001） | `AGENT_ORIGIN` |
| `/api` 其余接口及 `/health`                        | 业务 API 进程（端口 8000）    | `API_ORIGIN`   |

代理规则配置在 `vite.config.ts` 中；接口网络契约请查阅 `docs/architecture/frontend-contract.md` 与 `docs/architecture/citation-protocol.md`。

---

## 传输层工程保证

1. **强类型与边界校验**：由 `lib/contract.ts` 提供轻量级解析原语，所有接口响应在进入 UI 前完成类型与结构核验；一旦契约不符立即抛出结构化错误，杜绝未定义字段向下泄漏引发级联崩溃。
2. **显式有界超时与代际撤销**：`lib/api.ts` 结合上层调用者的 `AbortSignal` 与显式超时定时器；`lib/sse.ts` 实时消费 Agent 流式事件。结合前端代际栅栏（Generation Fence），用户重新提问或离开视图时立即中止在途网络请求，彻底消除异步时序竞态。
3. **服务端状态统一接管**：服务端异步数据统一由 **TanStack Query** 托管，杜绝在全局组件树中手动维护第二份缓存状态，保障加载中（loading）、空状态（empty）、错误归因（error）与重试（retry）流程的严谨完备。
