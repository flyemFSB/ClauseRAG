# 本地开发与运维管理指南

## 本地基础设施拓扑

系统基于 Docker Compose（`infra/compose.yaml`）一键编排底层中间件：
- **PostgreSQL 16**：存储业务数据、版本、切片、任务流水线事实及 LangGraph 检查点；
- **Qdrant**：存储子切片密集向量（`rag_child_chunks`）；
- **RabbitMQ 4**：平台唯一业务异步任务队列；
- **RustFS / S3**：存储原始文件与不可变解析 Markdown 及切片制品；
- **Langfuse 栈**（ClickHouse、Web 及 Worker）：提供 LLM 调用与检索追踪（复用外部 PG、Redis 与 RustFS）。

---

## 物理进程划分与启动入口

平台由四个独立边界的进程组成：

```powershell
# 1. 业务 API 服务 (端口 8000: 认证、知识库、文档管理、任务监控)
uv run python -m api.main

# 2. Agent 运行时服务 (端口 8001: 会话管理、流式问答、单轮检索诊断)
uv run python -m agent_runtime.main

# 3. 后台 Worker 消费进程 (任务认领、文档解析、分块、向量化与清理调度)
uv run python -m worker.main

# 4. 前端应用 (端口 5173: 双工作区 UI 与反向代理)
cd frontend
pnpm exec vp dev
```

---

## 一键式开发循环脚本 (dev.ps1)

推荐使用根目录 PowerShell 便捷脚本管理本地开发进程（支持容器与应用进程联动）：

```powershell
pwsh -NoProfile -File scripts/dev.ps1            # 启动容器 + 后端三进程 + 前端开发服务
pwsh -NoProfile -File scripts/dev.ps1 -NoWorker  # 纯前端 UI 调试模式：不启动流水线 Worker
pwsh -NoProfile -File scripts/dev.ps1 -NoFrontend# 仅启动后端多进程
pwsh -NoProfile -File scripts/dev.ps1 -Stop      # 安全停止本轮脚本启动的所有进程树
```

---

## 运维管理 CLI (Operator CLI)

平台不开放登录，因此也没有账号开通步骤（ADR-0033）：首次启动只需要初始化环境。

```powershell
# 1. 初始化对象存储存储桶 (幂等操作)
uv run python -m cli storage-init

# 2. 初始化 Langfuse 数据库与存储桶 (幂等操作)
uv run python -m cli observability-init

# 3. 同步单阶段任务执行 (绕过队列直接运行，便于排查特定版本解析/分块问题)
uv run python -m cli run-stage parse <document_version_id>
uv run python -m cli run-stage chunk <document_version_id>

# 4. 手动执行挂起的清理意图 (清理物理对象与向量索引)
uv run python -m cli cleanup-pending --limit 50

# 5. 重新执行向量化与索引构建
uv run python -m cli reindex <document_version_id>

# 6. 查看当前编译的 Agent 状态图节点与边拓扑
uv run python -m cli graph-topology
```

---

## 验证：静态门禁与容器路径

平台不再有探针脚本套件（`scripts/probes/`、`smoke.ps1`、`e2e-final.ps1`、`doctor.ps1` 已随本次交付删除）。验证分两层，第二层是唯一的运行时证据：

```powershell
# 1. 静态门禁（必须 100% 通过）
./scripts/check.ps1
pnpm --dir frontend run check
pnpm --dir frontend run test

# 2. 运行时验收（全栈）
docker compose -f infra/compose.yaml --profile app up -d --build --wait
Invoke-WebRequest http://localhost:5173/health/ready
Invoke-WebRequest http://localhost:5173/api/v1/config
```

`--wait` 等 `api`、`agent`、`worker`、`web` 全部 healthy；`migrate` 幂等且只跑一次。看日志用 `docker compose -f infra/compose.yaml logs -f rag-api`；停栈用同命令的 `down`（去掉 `-v` 以免连数据卷一起删）。


## 异常任务排查与状态恢复原则

1. **唯一事实源**：PostgreSQL 与 RustFS 存储权威事实，Qdrant 可依据切片和嵌入模型随时重建。
2. **卡顿任务恢复**：
   - 当 Worker 进程意外崩溃导致任务停滞在 `running` 状态时，后台调度器会在超出 `JOB_STALE_AFTER_SECONDS` 后自动回收租约并重新投递；
   - 亦可通过接口或界面主动发起重试：
     ```bash
     curl -X POST "http://127.0.0.1:8000/api/v1/document-versions/{version_id}/retry"
     ```
3. **阶段失败恢复**：若任务处于 `chunk_failed` 或 `index_failed`，可使用运维 CLI 针对该阶段单独重跑：
   ```powershell
   uv run python -m cli run-stage chunk <document_version_id>
   uv run python -m cli reindex <document_version_id>
   ```
