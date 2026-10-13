# 平台质量保障与验证策略

验证只有两个层次，且第二层是唯一的运行时证据。平台不再有探针脚本套件——`scripts/probes/`、`smoke.ps1`、`e2e-final.ps1`、`doctor.ps1` 与配套 skill 已随本次交付删除，验证入口收敛到下面两条命令。

## 静态门禁（代码是否自洽）

```bash
uv sync --locked --group eval    # 依赖锁定同步
uv run ruff check backend/src
uv run ruff format --check backend/src
uv run pyright backend/src       # Strict 模式
uv run python scripts/check-architecture.py
uv run python scripts/build-goldenset.py --verify
pnpm --dir frontend run check   # 格式化 + lint + 类型（type-aware）
pnpm --dir frontend run test    # 纯逻辑测试（4 个文件）
```

静态门禁能证明的东西有明确边界：类型、格式、依赖方向，以及四个进程入口都能被导入。它证明不了任何一条业务不变量——引用是否指向真实条款、检索是否真的召回、队列是否真的送达，都要靠下一层。

## 运行时验收（系统是否真的跑起来）

```bash
docker compose --profile app up -d --build --wait
```

一条命令做完：构建后端与前端镜像 → 一次性 `schema-init` 服务从 ORM 模型建表并装好检索扩展 → 起 `api`、`agent`、`worker`、`web` 并等它们 healthy。随后核对 nginx 单一入口上的真实响应：

```bash
curl -fsS http://localhost:5173/health/ready    # 逐依赖就绪；503 表示某项依赖不可用，响应里带每项延迟
curl -fsS http://localhost:5173/api/v1/config   # 本进程实际生效的配置（密钥只报是否已配置）
```

还有一类检查只能人来做，也必须做：上传一份真实合同、等流水线跑完、提问、点开引用卡片核对行号与原文、确认 SSE 是逐帧到达而不是最后一次性吐出。交付前每个功能改动至少走一遍这条路径。

外部依赖的真实调用（SiliconFlow 嵌入/重排/对话、PaddleOCR-VL 的扫描件解析）属于运行时验收的一部分：它们是不可替换的合同方，冒烟一次比读文档有用。
