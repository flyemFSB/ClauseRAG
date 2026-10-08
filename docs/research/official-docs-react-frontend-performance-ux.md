# React 前端性能与用户体验优化方案

> 目标：在当前 React + TypeScript + Vite+ + TanStack Router/Query/Table/Virtual/Form + Base UI + assistant-ui 技术栈上，保障完整前端体验，同时控制渲染成本、异步状态和并发请求。
>
> 范围：知识库管理、文档/摄取任务、合同审查、检索调试。本文区分“官方资料直接支持的事实”和“结合本仓库契约后的工程建议”，不把在线 `latest` 文档当成锁定版本 API。

## 结论先行

推荐采用以下边界：

```text
React local state       -> 输入、弹层、选中项、瞬时 UI 状态
URL / TanStack Router   -> 路由参数、可分享筛选和页面位置
TanStack Query          -> 所有 HTTP 服务端状态、缓存、失效和取消
SSE run controller      -> 当前对话流的临时状态，终态后以服务端记录校准
后端 PostgreSQL         -> 文档、任务、对话、消息、引用等业务事实
```

性能优化的优先级不是“减少 render 次数”，而是：

1. 减少首屏下载和不必要的网络请求。
2. 让输入、导航、停止按钮等紧急交互不被昂贵视图阻塞。
3. 让旧请求和旧流不能覆盖当前页面。
4. 只在真实长列表上虚拟化，并验证键盘、焦点和读屏行为。
5. 让每个异步流程都能被用户理解、恢复、取消或重试。
6. 用真实测量决定 `memo`、`useMemo`、`useCallback`、虚拟化和更复杂缓存是否值得。

当前仓库已经具备的正确基础包括：

- `frontend/package.json` 使用 React `19.3.0`、TanStack Query `5.104.0`、TanStack Router `1.170.41`、Node 24 和 pnpm 12。
- HTTP 查询函数已经接收并传递 TanStack Query 的 `AbortSignal`。
- Chat 使用 `POST` + `fetch` 流式读取，而不是直接用 `EventSource`。
- SSE 已有 schema version、固定事件名、终态检查和 `run_completed.answer` 校准。
- 摄取任务按页面可见性控制轮询。
- 知识库、文档、任务和检索调试已有 loading、empty、error 等基础页面状态。

优先修正的实现风险：

- SSE 解析应严格支持 `CRLF`、`TextDecoder` 尾部 flush、尾帧处理，并拒绝终态后的事件和第二个终态。
- `useAgentRun` 的旧流 `finally` 可能无条件把 `controllerRef.current` 清空，从而影响新 run 的停止按钮；应使用 generation/run identity 守卫。
- retrieval-debug 的异步结果应使用 generation 守卫，防止旧请求结果覆盖新查询。
- 摄取任务当前为每个文档版本建立一个 job query 和轮询器，文档数量增长后会形成 `O(document count)` 请求；应优先增加批量任务状态读取契约，再考虑虚拟化。
- 当前列表 API 没有分页、筛选或排序参数，不能在前端伪造服务端分页。规模增长前应先做 API 契约扩展。

## 1. 状态所有权与数据流

### 1.1 不要复制服务端状态

TanStack Query 的 query key 必须唯一描述 query function 所依赖的全部变量。官方文档说明，key 应包含影响 query 结果的变量；变量变化会触发新的缓存查找和获取。

来源：

- TanStack Query Query Keys：<https://tanstack.com/query/latest/docs/framework/react/guides/query-keys>
- 仓库前端契约：[`frontend-contract.md`](../architecture/frontend-contract.md)

推荐 key 形状：

```ts
["knowledge-bases"]
["knowledge-bases", knowledgeBaseId, "documents"]
["document-versions", versionId, "jobs"]
["conversations"]
["conversations", conversationId, "detail"]
```

如果以后增加分页、筛选、排序，必须把它们放进 key：

```ts
["documents", knowledgeBaseId, { page, pageSize, status, sort }]
```

不要把 cookie、密码、完整 prompt 或签名 URL 放进 query key。用户切换或登出时清理私有缓存，避免同一 QueryClient 生命周期内显示前一用户的数据。

### 1.2 资源 owner

| 数据 | 唯一 owner | React 中的表现 |
|---|---|---|
| 知识库、文档、版本、任务 | TanStack Query | query data、mutation、精确 invalidate |
| 当前筛选、知识库选择、展开行 | 组件 local state 或 URL | 不写入全局 store |
| 聊天历史 | conversation detail query | 不复制到另一份全局 server store |
| 当前 SSE 增量文本 | 当前 run controller/reducer | terminal 后替换或校准 |
| 业务状态和任务进度 | 后端 API | 不由前端计时器推断 |
| 检索调试结果 | 一次 mutation 的本地结果 | 不当作长期业务缓存 |

### 1.3 Router 与 Query 不要双重缓存

TanStack Router 可以在 route loader 中用 `ensureQueryData` 预加载关键数据，再由页面用同一个 Query key 读取。路由 loader 不应同时保存一份独立业务结果。

来源：

- TanStack Router 与 Query 集成：<https://tanstack.com/router/latest/docs/framework/react/guide/data-loading>
- TanStack Router Query integration：<https://tanstack.com/router/latest/docs/framework/react/guide/external-data-loading>
- TanStack Query Router integration：<https://tanstack.com/query/latest/docs/framework/react/guides/advanced-ssr>

工程规则：

- 进入页面必须有关键数据时：loader 使用 `ensureQueryData`，页面使用 query observer。
- 只是提前准备下一页时：使用不阻塞导航的 `prefetchQuery`，不要等待它完成。
- 选择一个缓存 owner。当前项目以 TanStack Query 为业务服务端状态 owner，Router 只负责导航、参数校验和必要的预加载。
- 预加载不是权限边界，服务端仍必须校验 cookie 和资源归属。

## 2. TanStack Query 请求策略

### 2.1 Query function 必须消费 signal

TanStack Query 会把 `AbortSignal` 传给 query function。官方文档指出，当 query 过时或不再活跃时，signal 可能被 abort；消费它可以中止底层 fetch。

来源：

- Query Cancellation：<https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation>
- MDN AbortController：<https://developer.mozilla.org/en-US/docs/Web/API/AbortController>
- MDN AbortSignal：<https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal>

统一模式：

```ts
export function documentsQueryOptions(knowledgeBaseId: string | null) {
  return {
    queryKey: ["knowledge-bases", knowledgeBaseId, "documents"] as const,
    enabled: knowledgeBaseId !== null,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      fetchDocuments(knowledgeBaseId!, signal),
  };
}

async function fetchDocuments(id: string, signal: AbortSignal) {
  const response = await fetch(`/api/v1/knowledge-bases/${id}/documents`, {
    credentials: "include",
    signal,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
```

取消应和失败分开：

- 用户点击停止、页面卸载、查询被淘汰：进入 cancelled/静默结束，不弹“系统失败”。
- 网络断开、超时、5xx：显示可理解错误和重试入口。
- 401：清理私有缓存并进入登录流程。
- 404：显示资源不存在，不推断或泄露其他用户资源。
- 422：映射字段或请求级错误，不自动重试。

### 2.2 不要照搬默认 freshness 和 retry

TanStack Query 的官方默认行为包括：query 默认立即 stale；失焦、重新连接和重新挂载可能触发后台 refetch；失败 query 默认会重试；非活跃缓存会在一段时间后 GC。具体默认值以当前锁定版本为准。

来源：

- Important Defaults：<https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults>
- Window Focus Refetching：<https://tanstack.com/query/latest/docs/framework/react/guides/window-focus-refetching>
- Query Retries：<https://tanstack.com/query/latest/docs/framework/react/guides/query-retries>

建议按变化速率配置，而不是全局一个值：

| 资源 | 建议策略 | 原因 |
|---|---|---|
| `knowledge-bases` | `staleTime` 数十秒到数分钟，mutation 后精确失效 | 元数据低频变化 |
| 文档列表 | 适中 `staleTime`，上传/删除后精确失效 | 不需要每次 focus 都全量重刷 |
| 单个 ingestion job | 页面可见时有界轮询，隐藏时暂停 | 需要新鲜，但不能打请求风暴 |
| conversation detail | 初次读取后按交互校准；run 结束主动 invalidate | SSE 是增量通道，detail 是持久事实 |
| retrieval-debug | mutation 结果不做长时间 query cache | 每次是一次 live report |
| `auth/me` | 较长 freshness，登出时清理 | 避免路由切换重复鉴权读取 |

retry 函数应按错误分类：

```ts
retry: (failureCount, error) => {
  if (error instanceof ApiError) {
    if (error.kind === "aborted" || error.status === 401 || error.status === 404 ||
        error.status === 422) return false;
    if (error.status !== undefined && error.status < 500) return false;
  }
  return failureCount < 2;
}
```

不要：

- 重试 4xx、用户取消或确定性 schema 错误。
- 对 job 页面开启无限轮询。
- 对每次窗口 focus 让全部页面同时发请求。
- 用 `staleTime: Infinity` 掩盖没有失效策略的问题。

### 2.3 Mutation 后精确更新

mutation 成功后的策略按语义选择：

- 新建知识库/对话：列表顺序由后端决定，精确 invalidate 或用响应写入后再 invalidate。
- 重命名：直接 patch 列表和详情缓存，避免不必要的空白和排序跳动。
- 删除：服务端成功后移除对应缓存；不要在失败不可恢复时永久乐观删除。
- 上传：更新文档列表，并读取 upload 返回的版本/job；不要只让页面等待一次固定时间。
- retry：失效对应 version、jobs 和文档摘要查询。

所有 mutation 都应有：pending 防重复、成功反馈、错误恢复、服务端响应校准。破坏性操作使用有名称、有键盘路径的确认对话框。

## 3. React 渲染成本控制

### 3.1 先保证纯渲染和 state locality

React 官方将组件 render 定义为纯计算，并建议保持组件和 hook 纯净。render 中不能启动请求、修改全局对象、追加流文本、读取随机值作为 key 或产生不可重复副作用。

来源：

- Render and Commit：<https://react.dev/learn/render-and-commit>
- Keeping Components Pure：<https://react.dev/learn/keeping-components-pure>
- Components and Hooks must be pure：<https://react.dev/reference/rules/components-and-hooks-must-be-pure>

针对本项目：

- SSE reader 放在 effect/专用 driver 中，reducer 只处理事件。
- chat composer 输入状态不要放在会随每个 delta 更新的消息树上层。
- 引用详情、历史消息、composer、流状态拆成独立子树。
- 表格行使用稳定业务 ID 作为 key，不能使用数组 index 作为身份。
- 不要在每次 render 对全部历史消息重复 Markdown 解析、引用解析和排序。

### 3.2 `memo`、`useMemo`、`useCallback` 的边界

React 官方说明：

- `memo` 只可能跳过父级触发的、且 props 浅比较相等的重渲染；组件自己的 state/context 变化仍会渲染。
- 新建 object/function props 会破坏浅比较收益。
- `useMemo` 和 `useCallback` 是性能优化工具，不是正确性保证。
- memoized value 不应承载 AbortController、run identity 或业务事实。

来源：

- `memo`：<https://react.dev/reference/react/memo>
- `useMemo`：<https://react.dev/reference/react/useMemo>
- `useCallback`：<https://react.dev/reference/react/useCallback>

使用顺序：

1. 先缩小 state 作用域和 context 订阅范围。
2. 再拆出稳定的行/消息/面板组件。
3. 用 React DevTools Profiler 和浏览器 Performance trace 找热点。
4. 只有昂贵纯计算或稳定 props 能让重组件跳过更新时才加 memoization。
5. 加入前后测量，防止缓存比较成本高于重算成本。

适合测量后使用的地方：

- retrieval-debug 的大候选表排序/派生视图。
- 文档、任务列表中昂贵的行内容。
- 已完成 chat message 的 Markdown/引用渲染。
- 复杂表格列定义和纯派生 Map/Set。

不适合：

- 每个小按钮、标签、简单文本都包 `memo`。
- 用 `useMemo` 保存必须稳定的业务状态。
- 用 `useCallback` 只是为了“代码看起来规范”。

React Compiler 的自动 memoization 不能作为本项目当前前提；仓库没有声明编译器配置，应以实际锁定工具链和构建产物为准。

### 3.3 把紧急输入和昂贵视图分开

`useDeferredValue` 可以让输入先更新、昂贵子树随后追赶；它不是网络 debounce，也不会让慢计算本身变快。`useTransition` 适合标记非紧急视图更新，不适合控制文本输入的 value。

来源：

- `useDeferredValue`：<https://react.dev/reference/react/useDeferredValue>
- `useTransition`：<https://react.dev/reference/react/useTransition>
- Suspense：<https://react.dev/reference/react/Suspense>

应用方式：

```tsx
const [filter, setFilter] = useState("");
const deferredFilter = useDeferredValue(filter);
const visibleCandidates = useMemo(
  () => filterCandidates(candidates, deferredFilter),
  [candidates, deferredFilter],
);

return (
  <>
    <input value={filter} onChange={(event) => setFilter(event.target.value)} />
    <CandidateTable rows={visibleCandidates} isStale={filter !== deferredFilter} />
  </>
);
```

网络搜索必须另行 debounce/显式提交，并使用 Query signal 取消旧请求。不能因为 deferred render 就向后端发送每个按键请求。

### 3.4 React 19.3 和 Suspense 的使用边界

Suspense 可以组织代码分割和异步渲染的 pending UI，但本项目已有 TanStack Query 的明确异步状态契约。不要为了追求“全 Suspense”而丢失 empty、retry、取消和字段错误语义。

建议：

- route chunk 可以使用 lazy/code splitting 和 route pending UI。
- 业务 query 是否使用 suspense，必须统一到项目约定；否则同一页面不要混用两套 loading/error 边界。
- 即使使用 Suspense，页面仍要在业务层表达空结果、可重试错误和 mutation pending。
- 不把异常边界当成普通可恢复业务错误的唯一 UI。

## 4. 列表、表格和虚拟化

### 4.1 虚拟化不是默认优化

TanStack Virtual 是 headless virtualizer，通过估算尺寸、滚动容器和 overscan 只渲染可视窗口附近项目；TanStack Table 本身不负责虚拟化，可以与 Virtual 组合。

来源：

- TanStack Virtual Introduction：<https://tanstack.com/virtual/latest/docs/introduction>
- TanStack Virtual React：<https://tanstack.com/virtual/latest/docs/framework/react/react-virtual>
- TanStack Table Virtualization：<https://tanstack.com/table/latest/docs/guide/virtualization>

当前项目建议：

- 知识库和文档列表短时使用普通 DOM 列表。
- retrieval-debug 候选表在数据量仍可控时优先保持原生 table、浏览器查找和屏幕阅读器顺序。
- chat 历史只有在消息数和 Markdown DOM 经实测造成滚动/输入延迟时才虚拟化。
- 摄取任务先解决每行 job query/轮询数量，再考虑行虚拟化；虚拟化不能减少网络请求。

虚拟化前置条件：

- 有稳定业务 ID key。
- 动态高度使用 `measureElement` 或可靠估算并测试滚动定位。
- 设置合理 overscan；overscan 越大，滚动空白越少，但渲染成本越高。
- 键盘焦点进入窗口外元素时行为明确。
- 读屏顺序、`aria-rowcount`、`aria-rowindex`、浏览器查找和窗口 resize 已通过真实浏览器验证。
- 如果无法完整保证无障碍，优先做后端分页而不是虚拟表格。

### 4.2 API 规模边界

当前 frozen API 的多数列表接口返回完整数组，没有分页、筛选和排序参数。前端不得把完整数组切片后声称实现了服务端分页，也不能把虚拟化当作数据规模治理。

建议触发 API 扩展的信号：

- 首屏 payload 明显影响 LCP 或内存。
- job query 数量与文档数线性增长并造成请求压力。
- table commit 或滚动任务影响 INP。
- 单个列表已经需要大量 DOM 才能浏览。

扩展后的优先顺序：

1. 后端提供分页、排序、筛选和总数/游标语义。
2. Query key 纳入 page/cursor/filter/sort。
3. 页面使用保留上一页数据的 pending 体验。
4. 只有单页仍有大量行时再加 Virtual。

## 5. 路由、拆包和预加载

TanStack Router 官方文档将 route code splitting 和 lazy loading 作为减少初始 bundle 的方式；数据加载阶段可以协调 route component 与 loader，预加载结果可与后续导航共享。

来源：

- TanStack Router Code Splitting：<https://tanstack.com/router/latest/docs/framework/react/guide/code-splitting>
- TanStack Router Data Loading：<https://tanstack.com/router/latest/docs/framework/react/guide/data-loading>
- TanStack Router File-based routing：<https://tanstack.com/router/latest/docs/framework/react/routing/file-based-routing>

推荐拆包：

- 登录/应用壳与知识库首页：首屏必要。
- 知识资产管理：独立 route chunk。
- Chat：独立 route chunk；Markdown/highlight 等大依赖再拆次级 chunk。
- retrieval-debug：独立 route chunk，避免进入普通首页首屏。
- graph/可视化：独立 route chunk，按真正导航或显式打开时加载。

推荐有限预加载：

- 侧栏高频且明确的下一站，在 hover/focus/intent 时预加载 route component 或关键 query。
- 不对所有页面和所有 query 全量预取。
- 低带宽、低端设备或用户未登录时减少无意义 preload。
- 预加载失败不能破坏当前页面，导航时仍应有 pending/error/retry。

使用 Vite+ 的 `vp` 脚本和仓库现有配置，不直接假设裸 Vite CLI 配置与当前版本完全相同。验收时检查：

- 生产构建产物有合理 route chunk。
- 首屏不下载 retrieval-debug 大依赖。
- 预加载和正式导航不产生重复 query。
- 慢网下主标题、导航和错误恢复仍可用。

## 6. Chat POST SSE：状态机、取消和竞态

### 6.1 为什么使用 fetch 而不是 EventSource

原生 `EventSource` 面向 URL 建立 SSE 连接，并提供浏览器自动重连语义；本仓库的消息接口是 `POST /conversations/{id}/messages`，需要 JSON body，且自动重放会重复提交一次业务 turn。因此应使用 `fetch`，消费 `Response.body` 的 `ReadableStream`，并由 `AbortController` 取消。

来源：

- MDN EventSource：<https://developer.mozilla.org/en-US/docs/Web/API/EventSource>
- MDN EventSource constructor：<https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource>
- MDN Using server-sent events：<https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events>
- MDN Using readable streams：<https://developer.mozilla.org/en-US/docs/Web/API/Streams_API/Using_readable_streams>
- WHATWG Server-sent events：<https://html.spec.whatwg.org/multipage/server-sent-events.html>
- 仓库 SSE 合同：[`frontend-contract.md`](../architecture/frontend-contract.md)

### 6.2 推荐状态机

```text
idle
  -> submitting
  -> streaming
  -> completed
  -> failed
  -> cancelled

submitting -> failed       HTTP 401/404/422、网络或开流失败
submitting -> streaming    run_started
streaming  -> completed    run_completed
streaming  -> failed       run_failed、格式错误、无终态 EOF
streaming  -> cancelled    用户 Abort 或 run_cancelled
```

约束：

- 一个 stream 只接受一个终态。
- `run_started` 建立服务端 run/message identity。
- 只处理当前 generation 的事件。
- delta 只用于实时显示。
- `run_completed.answer` 是权威最终文本，必须替换拼接文本。
- citation frame 先暂存，completed payload 再校准 citation IDs。
- EOF 无终态是断流/待同步，不是假装成功。
- HTTP 开流前错误不能伪装成 `run_failed` event。
- AbortError 不作为普通失败 toast。
- 取消后重新读取 conversation detail，确认后端持久化的 partial/cancelled message。
- 当前合同没有 event ID/resume protocol，不要自行实现 Last-Event-ID 重放。

### 6.3 SSE parser 必须覆盖的边界

实现层应：

- 使用 `TextDecoder.decode(value, { stream: true })`，读完后执行一次 `decode()` flush。
- 同时处理 `\\n\\n` 和 `\\r\\n\\r\\n` 的帧边界，或先按规范归一化行尾。
- 支持一个 event 的多个 `data:` 行，并按 SSE 规则拼接。
- 忽略注释/keepalive，但不静默忽略未知 event。
- 处理 chunk 恰好切断 UTF-8 多字节字符、`event:` 行或 JSON 行的情况。
- 对尾部不完整 frame 报 malformed，而不是丢失或伪造完成。
- 终态后遇到任何事件都报协议错误或忽略整个后续流，不能再次结算。
- `schema_version`、event payload 和 citation 字段全部做运行时校验。

伪代码：

```ts
let terminal = false;
let frameCount = 0;

for await (const frame of parseSse(response.body)) {
  if (terminal) throw malformed("event after terminal event");
  const event = parseVersionedEvent(frame);
  if (isTerminal(event)) {
    terminal = true;
    frameCount += 1;
    yield event;
    continue;
  }
  yield event;
}

if (!terminal || frameCount !== 1) {
  throw malformed("stream ended without exactly one terminal event");
}
```

### 6.4 generation guard

每次 run 分配递增 generation。异步 reader、catch、finally 和 query invalidate 都只能影响仍然是当前 generation 的状态。

```ts
const generation = ++generationRef.current;
const controller = new AbortController();
controllerRef.current = { generation, controller };

try {
  for await (const event of streamAgentRun({ signal: controller.signal, ...request })) {
    if (generation !== generationRef.current) continue;
    setRun((current) => applyRunEvent(current, event));
  }
} catch (error) {
  if (generation !== generationRef.current) return;
  // classify abort vs network/http/protocol failure
} finally {
  if (generation !== generationRef.current) return;
  if (controllerRef.current?.generation === generation) {
    controllerRef.current = null;
  }
  await queryClient.invalidateQueries({ queryKey: conversationDetailKey });
}
```

这解决两个实际风险：旧流的 finally 不会清掉新流的 controller；切换会话或 replay 后旧 delta 不会写入当前消息。

### 6.5 Chat UX

| 时机 | UI 行为 |
|---|---|
| 提交后 | 立即显示 user message 和 assistant pending；停止按钮可用 |
| `run_started` | 显示“正在生成”，记录 run/message ID |
| 首个 delta | 显示流式内容，不移动焦点 |
| `citation` | 增量准备引用，但不自行判断 marker 是否有效 |
| `run_completed` | 用 authoritative answer 替换 delta，显示完成/引用 |
| `run_failed` | 保留用户问题，显示错误分类和新请求重试入口 |
| Abort | 显示已取消，保留已生成 partial 内容；detail 校准后端状态 |
| 无终态 EOF | 显示“连接中断，正在同步结果”或“重试读取”，绝不显示成功 |

可访问播报只播报简短状态摘要，如“正在生成”“回答完成”“回答失败”；不要逐 token 使用 assertive live region。

## 7. 异步状态完整性

仓库前端契约明确要求每个异步视图覆盖 loading、empty、error、retry、cancellation 和 success。建议再区分初次加载与后台刷新：

```text
initial loading   -> skeleton/页面占位
background fetch  -> 保留旧内容 + 小型刷新标记
empty success    -> 解释为什么为空 + 当前下一步
error            -> 具体原因 + 可执行 retry
cancelled        -> 用户动作的结果，不当系统失败
mutation pending  -> 禁止重复提交/显示进行中
success           -> 服务端响应校准 + 不抢焦点反馈
```

### 页面矩阵

| 页面 | 必须实现 | 性能重点 | 不要做 |
|---|---|---|---|
| 知识库管理 | 列表 loading/empty/error/retry；创建编辑删除 pending/成功/失败；字段错误 | route chunk、精确 invalidate、避免全局重复状态 | 不在客户端伪造分页；不默认虚拟化短列表 |
| 文档管理 | 上传进度/取消/413/415/502；列表空状态；版本详情 | 大文件不能读入多份内存；上传请求有 timeout/signal | 不因固定延时猜测解析完成 |
| ingestion jobs | job 状态和网络 loading 分开；可见时有界 polling；失败/人工重试状态 | 解决每文档一个 query 的规模问题；隐藏页面暂停 | 不把 RabbitMQ 或前端计时器当业务真相；不显示合同不存在的 cancel |
| chat | SSE 状态机、停止、断流恢复、终态校准、引用 | 隔离 delta 更新；历史消息按实测虚拟化 | 不用 EventSource 自动重连；不自动重放 POST |
| retrieval-debug | query pending/取消/失败/空报告；区分 channel 状态；展示 rerank degraded | 结果很大时分页/虚拟化；派生排序只按 profile memo/defer | 不缓存成业务事实；不把 null score 当 0 |
| graph/调试 | 懒加载、加载占位、无数据和错误恢复 | 图组件独立 chunk | 不让图组件进入普通首屏 |

### 错误映射

后端契约：处理错误是 `{"detail": "..."}`，422 是 FastAPI validation detail 数组，资源不存在和无权限都为 404。前端应：

- 读取 `detail` 文本而不是只显示状态码。
- 422 把 `loc` 映射到字段，保留用户输入，必要时聚焦第一个错误。
- 401 进入统一登录恢复，并清理私有 Query cache。
- 404 使用资源不存在语义，不能暴露是否属于其他用户。
- 413、415、502 分别给上传大小、格式、存储故障的可行动建议。

## 8. 可访问性和反馈

### 8.1 语义优先

优先使用 Base UI 已提供的 dialog、select、tabs、switch 等无障碍行为，并通过真实浏览器验证，而不是手写不完整的 ARIA 状态机。

来源：

- WAI-ARIA APG Alert：<https://www.w3.org/WAI/ARIA/apg/patterns/alert/>
- WAI-ARIA APG Alertdialog：<https://www.w3.org/WAI/ARIA/apg/patterns/alertdialog/>
- WAI-ARIA APG Combobox：<https://www.w3.org/WAI/ARIA/apg/patterns/combobox/>
- WAI Dialog Modal Pattern：<https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/>

必查项：

- 每个 input 有可关联的 label；placeholder 不是 label。
- 字段错误通过 `aria-describedby` 关联；`aria-invalid` 只在真实错误时设置。
- 动态错误/状态 live region 在 DOM 中预先存在，避免只在出错时才插入而不被读屏器捕获。
- `role="alert"` 只用于需要立即知道的错误，不用于每 token、每次 polling 或普通成功 toast。
- alert 不抢焦点；需要用户确认/响应的阻断操作才用 alertdialog/dialog。
- 模态打开时焦点进入合理控件，Escape 可关闭，关闭后回到触发控件。
- 路由切换后有清晰的主标题和主区域，不要无条件抢走 composer 输入焦点。
- 所有功能可仅用键盘完成，焦点可见，Tab 顺序稳定。
- 状态不能只靠颜色表达，任务状态同时提供文字。
- loading skeleton 不造成页面布局跳动；按钮在 pending 时仍有可理解的禁用/进行中状态。

### 8.2 live region 策略

| 信息 | 建议 |
|---|---|
| 表单字段错误 | 字段关联文本，必要时页面错误摘要 `role=alert` |
| 删除确认 | modal/alertdialog，要求明确响应 |
| 保存成功 | `aria-live="polite"` 的简短反馈，不抢焦点 |
| job 后台刷新 | 页面可见状态文字，不逐行播报 |
| chat streaming | 只播报“正在生成/完成/失败”，不逐 token 播报 |
| 网络重试 | polite 状态 + 可聚焦 retry button |

来源：

- WAI ARIA19：<https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA19>
- WAI Error Identification：<https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html>
- WAI Labels or Instructions：<https://www.w3.org/WAI/WCAG22/Understanding/labels-or-instructions.html>

## 9. 性能测量与验收门槛

### 9.1 Web Vitals

web.dev 建议以真实用户数据的第 75 百分位评估 Core Web Vitals：

- LCP：不超过 2.5 秒为 good。
- INP：不超过 200 毫秒为 good。
- CLS：不超过 0.1 为 good。

来源：

- Web Vitals：<https://web.dev/articles/vitals>
- Optimize INP：<https://web.dev/articles/optimize-inp>

应按知识资产、chat、retrieval-debug 路由分别观察移动端和桌面端。仓库尚未定义前端 RUM endpoint 和隐私协议，因此不要擅自上传 prompt、文档名、引用 quote 或敏感内容。未有足够真实流量时，使用固定设备/网络的 lab trace，并明确标记为 provisional。

### 9.2 本项目关键指标

记录不包含 prompt、文档正文或引用敏感内容的计时：

```text
route navigation -> first meaningful heading/actionable UI
input event -> next paint / INP
SSE submit -> run_started
SSE submit -> first answer_delta
last event -> terminal event
abort click -> cancelled UI
EOF without terminal ratio
job polling request count per visible document
same query key duplicate in-flight request count
```

SSE 的绝对时限由后端/运营 SLO 定义，不在没有数据时编造“必须几秒完成”。

### 9.3 功能与竞态验收

Playwright 和真实浏览器至少覆盖：

- 每个 async view：loading、background refresh、empty、error、retry、cancel、success。
- 401、404、409、413、415、422、502 的正确提示和恢复路径。
- 切换会话/重试时旧 SSE delta 不覆盖新消息。
- stop 后新 run 的 stop controller 仍然有效。
- UTF-8 chunk 切分、CRLF、多个 data 行、尾帧、未知 event、无终态 EOF、重复终态。
- chat 成功后最终文本来自 `run_completed.answer`。
- 失焦暂停 job polling，回焦不会造成重复风暴。
- 同 query key 的在途请求复用，过时 query 能取消。
- 键盘-only：导航、select/combobox、tabs、dialog、retry、stop、表单错误恢复。
- 屏幕阅读器能获得错误、完成和取消摘要，但不会被 token 流刷屏。
- 构建产物中 retrieval-debug 不进入不必要的首屏 chunk。

## 10. 推荐实施顺序

### P0：先修正确性和竞态

1. 将 `useAgentRun` 的 controller 和 `finally` 改为 generation-scoped；旧 run 不得清理新 run 的 controller。
2. SSE parser 加入 CRLF、decoder flush、尾帧和严格单终态检查。
3. retrieval-debug 提交/停止流程加入 generation guard，旧结果不能写当前页面。
4. 统一 `ApiError` 分类，取消不进入普通失败 toast 和 retry。
5. 对 run 结束、取消、断流统一 invalidate conversation detail，让持久记录校准 UI。

### P1：稳定异步体验和请求成本

1. 建立集中 `queryOptions` 与错误 retry policy，避免每个 feature 私自重复规则。
2. 给 jobs polling 增加请求计数和可见性保护；确认文档规模后设计批量 job read API。
3. route 级 code splitting；对高概率目标做有限 intent preload。
4. 表单错误按 422 `loc` 映射，补齐 focus、`aria-describedby`、错误摘要。
5. 所有页面统一初次 loading 与后台刷新 UI，避免刷新时把已知内容换成空白。

### P2：按测量做结构优化

1. 用 Profiler 找出 chat message、retrieval table、job row 的实际热点。
2. 只给重组件加入 `memo` 和稳定 props；只缓存昂贵纯派生计算。
3. 先扩展后端分页/筛选，再评估 TanStack Virtual。
4. 长 chat 历史实测超过 DOM/滚动预算后再做动态高度虚拟化。
5. 在 route chunk、LCP、INP、CLS、SSE 首字和 job 请求数上建立回归门槛。

## 不建议事项清单

- 不机械添加 `memo/useMemo/useCallback`。
- 不用 `useDeferredValue` 代替网络 debounce、取消或分页。
- 不让 Router loader 与 Query 各自保存同一业务数据。
- 不为所有 query 使用无限 staleTime 或无限 retry。
- 不把前端 polling、RabbitMQ 消息或倒计时当业务事实。
- 不对短列表默认虚拟化。
- 不用原生 EventSource 自动重连本仓库的 POST SSE。
- 不自动重放用户消息，不假设当前合同支持 Last-Event-ID 恢复。
- 不把 citation marker 的有效性、任务取消或后端状态交给前端猜测。
- 不用 assertive live region 逐 token 播报。
- 不在没有真实测量和数据隐私契约时擅自增加 RUM 上报。

## 官方来源索引

- React Render and Commit：<https://react.dev/learn/render-and-commit>
- React Keeping Components Pure：<https://react.dev/learn/keeping-components-pure>
- React memo：<https://react.dev/reference/react/memo>
- React useMemo：<https://react.dev/reference/react/useMemo>
- React useCallback：<https://react.dev/reference/react/useCallback>
- React useDeferredValue：<https://react.dev/reference/react/useDeferredValue>
- React useTransition：<https://react.dev/reference/react/useTransition>
- React Suspense：<https://react.dev/reference/react/Suspense>
- TanStack Query Query Keys：<https://tanstack.com/query/latest/docs/framework/react/guides/query-keys>
- TanStack Query Important Defaults：<https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults>
- TanStack Query Query Cancellation：<https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation>
- TanStack Query Window Focus Refetching：<https://tanstack.com/query/latest/docs/framework/react/guides/window-focus-refetching>
- TanStack Query Query Retries：<https://tanstack.com/query/latest/docs/framework/react/guides/query-retries>
- TanStack Router Code Splitting：<https://tanstack.com/router/latest/docs/framework/react/guide/code-splitting>
- TanStack Router Data Loading：<https://tanstack.com/router/latest/docs/framework/react/guide/data-loading>
- TanStack Router File-based Routing：<https://tanstack.com/router/latest/docs/framework/react/routing/file-based-routing>
- TanStack Virtual Introduction：<https://tanstack.com/virtual/latest/docs/introduction>
- TanStack Virtual React：<https://tanstack.com/virtual/latest/docs/framework/react/react-virtual>
- TanStack Table Virtualization：<https://tanstack.com/table/latest/docs/guide/virtualization>
- MDN EventSource：<https://developer.mozilla.org/en-US/docs/Web/API/EventSource>
- MDN Server-sent events：<https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events>
- MDN Readable streams：<https://developer.mozilla.org/en-US/docs/Web/API/Streams_API/Using_readable_streams>
- MDN AbortController：<https://developer.mozilla.org/en-US/docs/Web/API/AbortController>
- MDN AbortSignal：<https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal>
- WAI-ARIA APG Alert：<https://www.w3.org/WAI/ARIA/apg/patterns/alert/>
- WAI-ARIA APG Alertdialog：<https://www.w3.org/WAI/ARIA/apg/patterns/alertdialog/>
- WAI-ARIA APG Combobox：<https://www.w3.org/WAI/ARIA/apg/patterns/combobox/>
- WAI Dialog Modal Pattern：<https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/>
- WAI ARIA19：<https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA19>
- WAI Error Identification：<https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html>
- Web Vitals：<https://web.dev/articles/vitals>
- Optimize INP：<https://web.dev/articles/optimize-inp>

## 仓库依据

- [`docs/architecture/frontend-contract.md`](../architecture/frontend-contract.md)
- [`docs/architecture/system-overview.md`](../architecture/system-overview.md)
- [`frontend/package.json`](../../frontend/package.json)
- [`frontend/src/lib/sse.ts`](../../frontend/src/lib/sse.ts)
- [`frontend/src/features/chat/run.ts`](../../frontend/src/features/chat/run.ts)
- [`frontend/src/features/ingestion-jobs/JobsPage.tsx`](../../frontend/src/features/ingestion-jobs/JobsPage.tsx)
- [`frontend/src/features/retrieval-debug/RetrievalDebugPage.tsx`](../../frontend/src/features/retrieval-debug/RetrievalDebugPage.tsx)
