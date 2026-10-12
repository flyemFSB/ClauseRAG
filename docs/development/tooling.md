# 开发环境与工程工具链规范

## 后端技术栈与命令

```text
Python 3.12 (>=3.12,<3.13)
uv 包管理器 (权威锁定 uv.lock)
Ruff (代码格式化、导入排序、静态检查)
Pyright (Strict 严格模式类型推断)
FastAPI + Pydantic v2
SQLAlchemy 2.0 (Async) + schema-init CLI (ADR-0035)
```

常用命令：
```bash
uv sync --locked                     # 依据锁文件极速同步虚拟环境
uv run ruff check backend/src        # 执行代码规范检查
uv run ruff format --check backend/src # 检查代码格式化状态
uv run pyright backend/src           # 执行严格模式类型检查
```

---

## 前端技术栈与命令

```text
Node.js 24
pnpm 12
Vite+ (统一 CLI: vp)
TypeScript 严格模式
React 19 + TanStack Router/Query + Base UI + Tailwind v4
```

常用命令：
```bash
pnpm exec vp check     # 运行格式化、Lint 与 TypeScript 类型检查
pnpm exec vp dev       # 启动开发服务器（反向代理双端后端）
pnpm exec vp build     # 生产环境打包构建
pnpm exec vp test      # 运行测试
```

---

## 国内镜像源配置 (Aliyun)

为保障依赖高速稳定下载，项目默认配置国内高速镜像源：
- **uv**：根目录 `pyproject.toml` 中已声明 `[[tool.uv.index]]` 默认指向 `https://mirrors.aliyun.com/pypi/simple/`，无需手动修改全局配置。
- **pip**（直接调用时）：可在 `%APPDATA%\pip\pip.ini` 中配置 `index-url = https://mirrors.aliyun.com/pypi/simple/`。
- **pnpm/npm**：用户级 `~/.npmrc` 中配置 `registry=https://registry.npmmirror.com`。

`uv.lock` 与 `frontend/pnpm-lock.yaml` 为全仓依赖解析的唯一事实来源。

---

## 运行时验收

静态检查（Ruff / Pyright / 架构方向）与前端 `vp check` / `vp test` 只回答"代码是否自洽"。系统是否真的跑起来由容器路径回答：

```bash
docker compose -f infra/compose.yaml --profile app up -d --build --wait
```

`--wait` 会等四个应用服务 healthy；`schema-init` 是一次性容器，负责 `python -m cli schema-init`（从 ORM 模型建表并装好检索扩展）；两个后端进程只在拓扑内部可达，浏览器只与 `rag-web`（默认 http://localhost:5173）通信。宿主开发循环没有任何一键脚本：容器只跑依赖（`docker compose up -d --wait`），API/agent/worker 与前端用下面的原生命令跑在宿主上。
