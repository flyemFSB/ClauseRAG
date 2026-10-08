# 官方文档核对：SQLAlchemy 2.0 asyncio（Official docs cross-check）

日期：2026-10-03 · 抓取方式：context7 REST API（`https://context7.com/api/v1/{library}?type=txt&topic=…`）。
原始文本存于 `.probe/c7/sa-3{1..4}.txt`（`.probe/` 已 gitignore）。

- 库 ID：`/websites/sqlalchemy_en_20`（`totalSnippets: 7656`）。注意 `/websites/sqlalchemy` 不存在（404），
  本次先踩了这个坑，记在这里备用。
- 抓取主题（均 200）：
  1. asyncio session per task concurrency → `sa-31.txt`
  2. async_sessionmaker and begin transaction → `sa-32.txt`
  3. unit of work session lifecycle commit rollback → `sa-33.txt`
  4. asyncio Session is not safe to share between tasks → `sa-34.txt`

本文件服务于 Phase 4（split PostgreSQL persistence by use case）与 Phase 6 之后的 store/事务边界核对。
只记录官方文档声明与本次取舍；文档没写的写明“文档未给”。

---

## 1. Session 本身就是 Unit of Work（不要包一层）

官方 ORM 文档把一次 flush 的事务上下文直接称为 Unit of Work：

> - **flush_context** (`UOWTransaction`) - Internal Unit of Work transaction context object.
>
> —— <https://docs.sqlalchemy.org/en/20/orm/session_api.html>（via context7）

**含义（对本计划）**：计划明确“不要引入自定义 Unit of Work 包装”（Explicitly Not Planned），本文支持这个判断：
SQLAlchemy 的 `Session`/`AsyncSession` 就是工作单元，`async_sessionmaker` 是它的工厂；再加一层 UoW 只会把
flush/commit 的语义遮起来。

## 2. 一个并发任务一个 Session：官方给了“另开一个 session”的并发范式

官方在 asyncio 并发一节给出的范式是：要在同一时间跑多条语句时，**另开一个 session**，而不是共用一个：

> ```python
> async def run_out_of_band(async_sessionmaker, statement, merge_results=True):
>     ...
>     async with async_sessionmaker() as oob_session:
>         ...
> ```
>
> —— <https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html>（via context7）

同页还记录 2.0 的**主动并发保护**：对处于活动状态的 Session 做并发或可重入修改时，抛出
`InvalidRequestError`（2.0 之前是难以诊断的 `AttributeError`）：

> Shows the `InvalidRequestError` raised by the initiating state-changing method when an unexpected
> concurrent or reentrant modification is detected during an active Session operation.

**含义（对本计划）**：计划的不变量“绝不在并发任务之间共享一个 `AsyncSession`”与官方范式一致，并且 2.0 会主动报错
而不是悄悄串台。Phase 4 的 store 因此保持“每次调用一个 session”（读用 `async with sessions()`，写用
`async with sessions.begin()`），没有任何 store 把 session 存成实例字段。

## 3. `async_sessionmaker` 与 `async_sessionmaker.begin()`（事务的官方写法）

> ### async_sessionmaker.begin()
>
> `sqlalchemy.ext.asyncio.async_sessionmaker.begin() -> _AsyncSessionContextManager[_AS]`
>
> ```python
> Session = async_sessionmaker(some_engine)
> ```
>
> —— <https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html>（via context7）

以及 `sessionmaker.begin()`：“Use `sessionmaker.begin()` to create a Session and begin/commit a
transaction automatically within a single context block.”

**含义（对本计划）**：计划要求“保留 `async_sessionmaker` 与 `async with session.begin()`，不要自定义 UoW”。
本项目的写路径正是 `async with self._sessions.begin() as session:`（创建 session、开启事务、退出时提交/回滚），
读路径是 `async with self._sessions() as session:`（无事务的必要开启）。Phase 4 拆分前后这一写法完全不变。

## 4. 跨 store 共用同一个事务（本项目需要，文档未直接给写法）

Phase 4 的 `ChunkStore.replace_version_chunks(session, ...)` 接收**调用方的 session**，以便“chunk 行 + artifact 行
+ job 状态”落在同一个事务里提交。官方文档给的是“并发时另开 session”，没有直接讨论“一个适配器把 session 交给
另一个适配器以合并到一个事务”；文档也没有给“事务不要跨越网络调用”的明文规定。

**本项目据此的判断**（记录为项目不变量，而非官方要求）：

- 共享 session 只发生在**同一个事务内**的两个 PostgreSQL 适配器之间（`SqlAlchemyIngestionStore` →
  `SqlAlchemyChunkStore`），并且是显式参数传递，不是模块级或实例级的共享；
- 该 session 不跨越任何外部调用：chunk 写入与 job 状态更新之间没有 provider 调用；
- 并发任务各自从 `async_sessionmaker` 取自己的 session（第 2 节），因此这条共享不违反第 2 节。

## 5. 文档未给

- 官方未给“短事务”的具体长度建议；本项目把“外部调用不在事务内”作为项目不变量（`docs/architecture/data-flow.md`），
  并把事务边界放在 store 方法内部。
- 官方未给“一个 store 接收另一个 store 的 session”的推荐/反对意见（第 4 节）。
- 官方未给 `async_sessionmaker` 的 `expire_on_commit` 取值建议（本项目默认值不变）。

## 6. 可行性结论（Phase 4）

| 计划动作 | 官方依据 | 结论 |
|---|---|---|
| 保留 `async_sessionmaker` + `async with session.begin()` | 第 3 节 | 保留，未改动 |
| 每次调用一个 session，不与并发任务共享 | 第 2 节（官方并发范式 + 2.0 保护） | 采用；拆分后 4 个 store 都是每次调用一个 session |
| 不引入自定义 Unit of Work | 第 1 节（Session 即 UoW） | 不引入 |
| chunk 行与 job 状态同一事务（跨 store 传 session） | 第 4 节（文档未给） | 采用，记录为项目不变量并说明其约束 |
| 事务不跨外部调用 | 第 5 节（文档未给） | 保留现有项目不变量 |

未验证项（留待 task-8 的真容器运行）：拆分后每个 store 的写路径仍是一个事务、重复交付不会重复执行、
以及 `scripts/probes/queue.ps1` 断言的重试与终态不变。
