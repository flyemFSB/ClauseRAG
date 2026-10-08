# 官方文档核对：HTTPX（Clients / Limits / 超时）

日期：2026-10-05 · 版本依据：`uv.lock` 锁定的 `httpx 0.28.1`（`uv run python -c "import httpx; …"` 读取的
docstring 与 `httpx._config` 默认值）。
抓取页面：

- Clients：<https://www.python-httpx.org/advanced/clients/>
- API reference（`Limits` / `AsyncClient`）：<https://www.python-httpx.org/api/>

本文件服务于 ADR-0025（HTTPX、SiliconFlow、OCR 与外部 provider 的连接与超时契约），只记录官方声明、
锁定版本的实际行为，以及本项目的取舍；官方没写的写明“文档未给”。

---

## 1. Client 复用连接：官方把“每次新建连接”明确列为低效

> “When you make requests using the top-level API … HTTPX has to establish a new connection **for every
> single request** (connections are not reused). As the number of requests to a host increases, this
> quickly becomes inefficient. On the other hand, a `Client` instance uses HTTP connection pooling.
> This means that when you make several requests to the same host, the `Client` will reuse the
> underlying TCP connection, instead of recreating one for every single request. This can bring
> **significant performance improvements** compared to using the top-level API, including:
> * Reduced latency across requests (**no handshaking**).”

—— <https://www.python-httpx.org/advanced/clients/>

这里的“top-level API”指 `httpx.get/post`；官方在 API reference 的 Helper Functions 一节再次强调：

> “Only use these functions if you're testing HTTPX in a console or making a small number of requests.
> Using a `Client` will enable HTTP/2 and connection pooling for more efficient and long-lived
> connections.”

—— <https://www.python-httpx.org/api/>

**对项目的含义**：provider 调用全部是 HTTPS，直达 `api.siliconflow.cn`。本仓库原来的写法是
`async with httpx.AsyncClient(...)` **每次调用新建并关闭一个 client**（embeddings / rerank / chat
三个 adapter 都是），即官方点名的“每次请求新建连接”模式：每个 embedding batch、每次 rerank、每个回答
（分类一次 + 流式回答一次）都要重做 DNS/TCP/TLS 握手。这一项不是“更优雅”，而是**请求路径上可直接测量的
固定成本**，因此是本次唯一按官方建议改写的 provider 行为。

**判定**：每个 provider adapter 每进程持有 **一个** client，首次使用时在事件循环内创建，由拥有它的
进程 runtime 的 `close()` 关闭（ADR-0025）。检索/摄取路径不放宽任何 timeout 或 retry 语义。

## 2. `Limits`：官方给的是语义，不是推荐数值

锁定版本 `httpx.Limits` 的 docstring（与 API reference 同源）：

> “Configuration for limits to various client behaviors.
> * **max_connections** - The maximum number of concurrent connections that may be established.
> * **max_keepalive_connections** - Allow the connection pool to maintain keep-alive connections below
>   this point. Should be less than or equal to `max_connections`.
> * **keepalive_expiry** - Time limit on idle keep-alive connections in seconds.”

默认值（本机读取，`httpx 0.28.1`）：
`Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=5.0)`。

**文档缺口（如实记录）**：官方**没有**给出“一个进程应该开多少连接”的建议值，也没有把它与 provider 配额或
worker 并发建立公式。可查到的量化约束只有默认值本身（单 client 100 条并发连接）。

**判定**：保留官方默认的 `keepalive_expiry`（5 s）——它是官方对“空闲连接值不值得留”的回答，本项目没有
调用间隔的实测数据去反驳它；只把 `max_connections` 显式配置为 `RAG_PROVIDER_MAX_CONNECTIONS`（默认 16），
因为 100 条并发连接既超过 provider 配额，也超过本部署实际会同时发出的请求数。

**本机实测**（`scripts/probes/http_client.py`，本地计数 HTTP server，无容器、无 provider 凭据）：

```text
sequential calls: connections=1 (reused)
five concurrent calls, max_connections=2: connections=2 peak_in_flight=2
a cancelled call left the client usable
http client probe passed
```

即：连续两次调用确实复用同一条 TCP 连接；`max_connections=2` 时 5 个并发请求只建立 2 条连接、服务端观测
到的并发峰值也是 2——这个参数是**硬上限**而不是提示。

## 3. 生命周期：`aclose()`，且不能把共享 client 当上下文管理器

> “The recommended way to use a `Client` is as a context manager. This will ensure that connections
> are properly cleaned up when leaving the `with` block … Alternatively, you can explicitly close the
> connection pool without block-usage using `.close()`”

—— <https://www.python-httpx.org/advanced/clients/>

异步侧：`AsyncClient.aclose()`，锁定版本 docstring 为 “Close transport and proxies.”

**锁定版本的实际行为（阅读 `.venv/Lib/site-packages/httpx/_client.py`，比文档更严格）**：

- `AsyncClient.__aenter__` 在 client 已经 `OPENED` 时抛
  `RuntimeError("Cannot open a client instance more than once.")`，在 `CLOSED` 时抛
  `RuntimeError("Cannot reopen a client instance, once it has been closed.")`；
- `aclose()` 用 `_state` 判重，重复调用是无害的 no-op。

**对项目的含义**：共享 client **不能**再写 `async with client:`（第二次进入会直接抛错，或把整个连接池关掉）。
需要的“块级作用域”下移到**响应**：`async with client.stream(...)`。这正好保留了取消语义——消费者被取消时
展开生成器，块退出关闭 response 并释放它占用的连接，而 client 本身留给下一个请求继续用。

## 4. 事件循环归属：文档未给，按本仓库既有约定处理

官方文档没有说明“`AsyncClient` 是否必须在其所属事件循环内创建”。锁定版本里 `AsyncClient.__init__`
只构造 transport / pool 对象，真正的连接在首次请求时建立。

**判定**：不依赖该未声明行为，沿用本仓库已经在 `QdrantChildChunkIndex` 与 `IngestionJobQueue` 里使用的
形状——`asyncio.Lock` + 惰性创建 + `close()`：client 在**第一次使用时**创建，因此必然落在将使用它的那个
事件循环里；一个从不调用该 provider 的进程（例如只跑 parse 的 CLI 命令）不会打开任何连接。CLI 的
`run_once_async`/`reindex_async` 已经把“同一 runtime 的所有调用和 `close()` 放在同一个 `asyncio.run` 里”
写成约定，本改动与该约定一致。

## 5. 本次未采纳的官方能力

- **HTTP/2**（`http2=True`）：官方说明需要额外依赖 `h2`，且收益取决于服务端支持。文档未证明
  SiliconFlow 支持，故不开启。
- **`keepalive_expiry` 调参**：见 §2，没有实测调用间隔支撑，保留默认。
- **`proxy` / `mounts` / event hooks / 自定义 transport**：本项目没有对应需求，不加。
- **重试**：官方客户端默认**不重试**（`retries` 是 transport 层参数）。本项目的重试预算属于队列中间件
  （ADR-0017），adapter 仍然“一次调用一次请求、从不重试”，本次不改变。

---

## 6. 与其他 provider 的对照

| 适配器 | 本次改动 | 理由 |
|---|---|---|
| embeddings / chat / rerank | 每进程一个 pooled client，`close()` 由 runtime 调用 | 官方“no handshaking”，见 §1；一次回答/一次摄取 = 多次调用 |
| PaddleOCR-VL | **不改** | 它已经在一次 `parse()` 内复用一个 client（提交 + 轮询 + 取结果）；跨文档复用收益远小于其自身的轮询间隔，且 `DocumentParser` 端口没有 `close()`，为它加一个只为 OCR 存在的生命周期会污染另外三个纯本地 parser |
| Qdrant | **不改** | 已经是官方推荐的 `AsyncQdrantClient` + 惰性连接 + `close()` |
| RustFS/S3 (boto3) | **不改** | boto3 client 自带连接池与 multipart 线程池，已经是长生命周期对象 |
