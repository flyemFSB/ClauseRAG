# 官方文档核对：LangGraph（Official docs cross-check）

日期：2026-10-03 · 抓取方式：context7 REST API（`https://context7.com/api/v1/{library}?type=txt&topic=…`）。
本机没有配置 context7 MCP server，因此用它的公开 HTTP 接口取文档，原始文本存于 `.probe/c7/`（`.probe/` 已 gitignore）。

- 库 ID：`/websites/langchain_oss_python_langgraph`（`verified: true`，`lastUpdateDate: 2026-09-28`）
- 抓取主题（每个 200，均为官方文档 `docs.langchain.com/oss/python/langgraph/*` 的上下文片段）：
  1. state schema and reducers → `langgraph-1.txt`
  2. checkpointer persistence → `langgraph-2.txt`
  3. streaming stream_mode → `langgraph-3.txt`
  4. runtime context injection → `langgraph-4.txt`
  5. durability and resuming → `langgraph-5.txt`

本文件只记录**官方文档声明**与**对重构计划的可行性判断**；文档没写的部分写明“文档未给”，不用推测值填空。
它服务于检索深模块与 seam 边界的可行性判断（见 `docs/architecture/system-overview.md` 的
Deep Module Interfaces 与 Seam Policy）。

---

## 1. checkpoint 持久化的是什么

官方在 checkpointers 页给出的自定义 saver 实现里，一次 checkpoint 是
`checkpoints` 行 + 该 `checkpoint_id` 下的若干 `writes` 行，每条 write 单独带
`(task_id, channel, type, value)`，读取时逐条 `serde.loads_typed` 反序列化：

> ```python
> writes = await self.db.fetchall(
>     "SELECT task_id, channel, type, value FROM writes "
>     "WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=? ..."
> )
> ```
>
> —— <https://docs.langchain.com/oss/python/langgraph/checkpointers>

**含义（对本计划）**：状态里的每个 channel 值都会按步写入 `checkpoint_blobs`/`writes`，所以“state 里放什么”
直接决定每一步的写放大。计划要求把 `records`、`merged_hits`、`fused_candidates`、`reranked_candidates`
从 checkpoint 状态里拿掉 —— 文档支持这个方向，因为 `Candidate` 携带 `ChunkRecord.content`（整块正文），
它们是纯粹的写放大，而不是恢复所需的事实。官方还提供了 `EncryptedSerializer`
（`langgraph.checkpoint.serde.encrypted`）用于加密持久化状态；本项目不需要它（trace/日志已排除正文），
记在这里以备将来合规要求。

## 2. 私有通道：`input_schema` / `output_schema` 与 `EphemeralValue`

官方 graph-api 页明确支持“对外接口受限、内部节点用私有 state channel 通信”：

> Use `StateGraph` with explicit `input_schema` and `output_schema` to restrict the external interface
> while allowing internal nodes to communicate using private state channels.
>
> ```python
> builder = StateGraph(OverallState, input_schema=InputState, output_schema=OutputState)
> ```
>
> —— <https://docs.langchain.com/oss/python/langgraph/graph-api>

pregel 页的 channel 列表里另有 `EphemeralValue`（“仅在一步内可见”的值），与
`BinaryOperatorAggregate`（自定义 reducer）并列：

> ```python
> from langgraph.channels import EphemeralValue, BinaryOperatorAggregate
> ```
>
> —— <https://docs.langchain.com/oss/python/langgraph/pregel>

**含义（对本计划）**：官方确实给了两种“不要把中间量落盘”的机制。但本计划的取舍是**减少概念**，而不是
保留中间量再想办法不落盘：把检索的 7 个节点收敛成 1 个节点后，`records`/`merged_hits`/
`fused_candidates`/`reranked_candidates` 这些 key 直接不存在了，既不用 `EphemeralValue`，也不用
`input_schema`/`output_schema` 把接口切三份。检索的各级中间结果是**请求级**事实（诊断读取要它们、
checkpoint 不要它们），因此它们属于 `RetrievalResult.diagnostics`，而不是 state。

## 3. Runtime context：长生命周期依赖的注入方式

官方 graph-api 与 stores 页都给出同一模式：节点签名第二参数标注 `Runtime[ContextSchema]`，
从 `runtime.context` 取过程级依赖（进程内只构造一次），而不是在构图时闭包捕获：

> ```python
> from langgraph.runtime import Runtime
>
> def node_a(state: State, runtime: Runtime[ContextSchema]):
>     llm = get_llm(runtime.context.llm_provider)
> ```
>
> —— <https://docs.langchain.com/oss/python/langgraph/graph-api>

**含义（对本计划）**：现有实现（`RunContext` 经 `context=` 注入、一个编译好的 graph 服务所有会话）与官方
推荐一致，**Phase 2 不改这一层**。计划要求的“`RunContext` 暴露一个 `ConversationAgent` 协作对象而不是若干
互不相关的 application service”属于“谁是节点的世界”的问题，不是 LangGraph 机制问题。

## 4. 流式：`stream_mode`

官方文档的 `custom`（`get_stream_writer()` 推送自定义 chunk）、`updates`（节点进度）、`values`（完整状态）三种模式如下：

> Use stream_mode="custom" alongside get_stream_writer to emit and receive streaming chunks from
> external clients or services that do not implement the LangChain interface.
> —— <https://docs.langchain.com/oss/python/langgraph/streaming>
>
> Streams the full state object after each step of graph execution.
> —— <https://docs.langchain.com/oss/python/langgraph/streaming>

**含义（对本计划）**：本项目的 SSE 契约只消费 `custom` 模式的 `AnswerDelta`；`updates` 的载荷在
`runner.py` 里被显式忽略（`mode == "custom"` 才读）。因此**节点名字不在对外契约里**，把 7 个检索节点
合并成 1 个不会改动 `docs/architecture/citation-protocol.md` 的任何一帧；`scripts/probes/agent.ps1`
与 `observability.ps1` 也只断言 `agent.run` observation 与结构化日志事件，不引用节点名（本次实测 grep 确认）。

## 5. 恢复/重放语义

官方 time-travel 页给出重放规则：从某个 checkpoint 重放会**跳过该点之前的节点**，**重新执行其后的节点**；
从一个没有后继节点的终态 checkpoint 重放是 no-op。

> Demonstrates replaying graph execution by retrieving state history and passing a prior checkpoint
> config to invoke. Nodes before the checkpoint are skipped while subsequent nodes re-execute.
> Note that replaying from a terminal checkpoint with no next nodes is a no-op.
>
> —— <https://docs.langchain.com/oss/python/langgraph/use-time-travel>

**含义（对本计划）**：合并节点后，“进程在检索中途崩溃”会从检索节点之前重放整轮检索（而非从中途续跑）。
检索是只读的（PostgreSQL / ParadeDB 向量与关键词查询，无副作用），重放安全；代价是失去“检索内部步骤级”的恢复点，
而这正是计划明确要放弃的东西（`max_retrieval_rounds` 仍是唯一的环路上限，`rounds` 由 `plan_retrieval` 计数）。
恢复**所需**的事实因此只剩：`evidence`、`citation_sources`、`context`、`context_tokens` —— 即
`generate`/`validate_citations`/runner 会读的那一份记录。

## 6. 文档未给（因此不由文档决定）

- **durability 模式**（`durability="sync"|"async"|"exit"`）的具体语义：本次抓取的主题没有返回对应正文，
  文档未给。本项目保持框架默认值不动：`agent.ps1` 断言“4 次 run 至少 4 个 checkpoint 且至少 1 条 write”，
  改成只在退出时落盘会让崩溃中的 run 记录消失，与 `docs/architecture/data-flow.md` 的“run 可检查/可恢复”
  相冲突，且计划没有要求改它。
- **状态大小 / 节点粒度的具体阈值**：文档未给任何“state 应该多大”或“多少节点合适”的数值建议。
  因此本计划的判断依据是**本站实测**（`Candidate` 含正文，每步一次 checkpoint 写入）与
  “run 需要什么才能恢复”这一功能判据，而不是文档条文。
- **是否推荐把多个步骤合并成一个节点**：文档未给。文档只描述 `private state channels` 与 `EphemeralValue`
  两种机制。合并节点的理由来自本计划的设计目标（更少的调用方知识、更少的落盘），不是官方指引。

## 7. 可行性结论（Phase 2）

| 计划动作 | 官方依据 | 结论 |
|---|---|---|
| 检索收敛为一个 `RetrievalService.retrieve()`，节点只调一次 | graph-api / streaming（节点名不在对外契约） | 可行 |
| checkpoint 状态删除 `records`/`merged_hits`/`fused_candidates`/`reranked_candidates` | checkpointers（每步按 channel 落盘） | 可行 |
| 保留 `RunContext` + `Runtime` 注入 | graph-api / stores（官方推荐模式） | 不变 |
| 保留 LangGraph 的 `StateGraph`/checkpointer/streaming，不手写引擎 | graph-api / streaming / checkpointers | 不变 |
| 不引入 `EphemeralValue`/三段 schema | pregel（机制存在，但计划要求更少概念） | 不使用 |
| 不改 durability、不改 checkpointer 表结构 | 文档未给，且探针断言现状 | 不动 |

未验证项（留待本阶段真容器探针）：合并后 `rewrite_once → plan_retrieval` 环路仍受
`max_retrieval_rounds` 限制（`retrieval.ps1` 与 `agent.ps1` 会实测轮数与终态事件），以及
`checkpoints`/`checkpoint_writes` 行数在同样 4 次 run 下不再随候选数量增长（`agent.ps1` 步骤 9）。
