# 官方文档核对：FastAPI（Official docs cross-check）

日期：2026-10-03 · 抓取方式：context7 REST API（`https://context7.com/api/v1/{library}?type=txt&topic=…`）。
本机未配置 context7 MCP，故用其公开 HTTP 接口；原始文本存于 `.probe/c7/fastapi-2{1..4}.txt`（`.probe/` 已 gitignore）。

- 库 ID：`/websites/fastapi_tiangolo`（`totalSnippets: 3457`）。注意 `/websites/fastapi_tiangolo_com` 不存在（404），
  本次先踩了一次这个坑，记在这里。
- 抓取主题（均 200）：
  1. dependency overrides → `fastapi-21.txt`
  2. lifespan events and resource cleanup → `fastapi-22.txt`
  3. dependencies with yield → `fastapi-23.txt`
  4. router level dependencies → `fastapi-24.txt`

本文件服务于按进程拆分 composition（`composition/{api,agent,worker,cli}/runtime.py`，见
`docs/architecture/system-overview.md` 的 Process Composition）的依赖注入取舍。
只记录官方文档声明与本次取舍；文档没写的写明“文档未给”。

---

## 1. `Depends` + 依赖提供函数（官方生产用法）

官方在 router 级别依赖、路径操作依赖等页把 `Depends(callable)` 作为生产用法；依赖由 FastAPI 在请求时解析并缓存
（同一请求内同一依赖只求值一次，`use_cache` 可关）。本项目沿用：每个 router 声明自己需要的依赖，handler 签名
不变。

## 2. `app.dependency_overrides`：官方文档把它写在 **测试** 章节

官方 reference 页原文：

> Maintains a dictionary mapping original dependency callables to **testing** versions for overriding
> dependencies during tests.
>
> ```python
> dependency_overrides = {}
> ```
>
> —— <https://fastapi.tiangolo.com/reference/fastapi>

以及 advanced/testing-dependencies 页给出的重置方式 `app.dependency_overrides = {}`。

**含义（对本计划）**：机制本身公开且稳定（以“原依赖 callable”为键），但官方文档只在“测试时替换依赖”的语境里
介绍它；把构造好的实例在生产 composition 里用同一机制绑定，**属于超出文档推荐语境的用法**。本次仍选择它，
理由与代价如下：

- 计划要求“routers 不要通过通用 container 取依赖”，并给出 `create_documents_router(document_catalog)` 的
  示例（把模块交给 router 工厂）；
- 但本项目有一个**跨 router 的共享依赖**：`CurrentUser = Annotated[AuthUser, Depends(current_user)]`，而
  `current_user` 自己需要 `AuthService`。若每个 router 只通过工厂闭包拿到自己的模块，这个共享依赖无法从任何
  一个工厂拿到服务，除非把它复制成每个 router 自己的变体（重复）或引入全局可变状态（更差）；
- `dependency_overrides` 以 provider 函数为键，正好允许“router 声明 + 工厂绑定”，从而**完全移除 `app.state`**；
- 代价：漏绑定时在请求期抛 `RuntimeError`（provider 体显式抛出，消息点名缺失的服务），而不是启动期报错。
  这是本项目接受的取舍，并记录在此。

**计划文档示例未采用的部分**：`create_documents_router(documents, ingestion)` 这类“工厂收模块”写法只覆盖了
“每个 router 自己的模块”，无法覆盖上面的共享依赖。若将来把 `current_user` 改为由 `AuthService` 无关的
token→user 解析器承担，则可以退回文档示例的写法。

## 3. `lifespan`：启动/关闭期资源（官方推荐）

> Uses an `@asynccontextmanager` function to load an ML model before yielding and clean it up upon
> application shutdown.
>
> ```python
> @asynccontextmanager
> async def lifespan(app: FastAPI):
>     ml_models["..."] = ...
>     yield
>     ml_models.clear()
>
> app = FastAPI(lifespan=lifespan)
> ```
>
> —— <https://fastapi.tiangolo.com/advanced/events>

**含义（对本计划）**：本项目的 lifespan 保留，并且职责更窄：它只关闭进程 runtime 已拥有的资源
（`ApiRuntime.close()`），agent runtime 额外负责“必须在服务请求的同一个 loop 里打开”的 checkpointer
（`GraphCheckpoints`），并把编译好的 graph 交给
`ConversationAgent`，再用绑定机制交给 router。把 checkpointer 放到 composition 里提前打开会把它绑到一个临时
loop 上，HTTP 请求期间不可用——这是本次保留 lifespan 的实质原因，而不是形式原因。

## 4. `dependencies with yield` 与 router 级依赖

官方给出 yield 依赖的清理与异常捕获语义（`try/finally`、可捕获 `HTTPException` 后回滚再抛出），以及
`APIRouter(dependencies=[Depends(...)])` / `app.include_router(router, dependencies=[...])` 的两种 router 级依赖
写法。

**含义（对本计划）**：本项目的 handler 不使用 yield 依赖——数据库事务由 store 适配器在方法内部以
`async with session.begin()` 管理（Phase 4 的不变量），不跨请求持有；也不使用 router 级依赖，因为需要区分
“需要登录”和“不需要登录”的端点（`/health/*`、`/auth/login`），而 router 级依赖会无差别地施加到全部路径操作。

## 5. 文档未给

- 官方未给“生产 composition 是否该用 dependency_overrides”的建议（只有测试语境）。
- 官方未给“router 工厂接收模块”或“app.state 存服务”的取舍建议；两种在文档里都能看到，取舍由本项目记录
  （第 2 节）。

## 6. 可行性结论（Phase 5）

| 计划动作 | 官方依据 | 结论 |
|---|---|---|
| 保留 `Depends`、app factory、lifespan | 第 1、3 节 | 保留，且 lifespan 只做资源释放 |
| 路由不再通过 `app.state.container` 取依赖 | 第 2 节（机制）+ 计划要求 | 采用 provider + `dependency_overrides`；`app.state` 全部移除 |
| 每进程一个 composition 函数 | 计划要求 | 采用：`composition/{api,agent,worker,cli}.py` + `resources.py` |
| 用 yield 依赖管事务/会话 | 第 4 节 | 不使用：事务边界属于 store 适配器 |
| router 级依赖 | 第 4 节 | 不使用：需要区分需登录/不需登录的端点 |

未验证项（留待 task-8 的真容器运行）：两个 HTTP 进程在只绑定了自己用到的 provider 时仍能完整服务各自的路由；
漏绑定时的 `RuntimeError` 不会在正常路径上出现。
