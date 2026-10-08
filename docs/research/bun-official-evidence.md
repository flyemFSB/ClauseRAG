# Research: Bun 官方文档证据（迁移审查）

> 范围：仅使用 Bun 官方文档（`bun.sh/docs`）、Bun 官方发布说明（`bun.com/blog`）以及 `oven-sh/bun` 官方 GitHub Releases。本文把“官方明确写出”的内容与研究者据此提出的迁移推论分开。页面内容会随 Bun 发布更新；版本、兼容矩阵和实验性标记应在每次升级前重新核对。

## Summary

当前官方 GitHub Releases 页面顶部显示 **Bun v1.4.2**；其官方发布说明标题为“Bun v1.4.2”，内容记录了 `bun build`、`AsyncLocalStorage`、`worker_threads`、JSC、musl/GC 和 `bun install` 等修复。官方文档已把 Bun 定位为可运行现有 Node.js 项目的 runtime/package manager/bundler/test runner，但同时明确说 Node.js 兼容性尚未 100%，并逐模块记录差异。因此从 Node.js 迁移的低风险路径是先固定 Bun 版本、保留现有 Node/pnpm 可回退路径，在真实依赖和真实基础设施上做对照验证；不要把“多数 npm 包可运行”理解成行为或 ABI 等价。

Bun 对本任务相关能力的官方承诺较强：TypeScript/JS 直接运行，`node:*` 常用模块、Web APIs、内置测试、bundler、`Bun.file`、SQLite、Redis、S3 和 `Bun.serve` 均有官方实现。风险集中在部分 Node 模块的语义边界（例如 `node:test`、`async_hooks`、`v8`、TLS/HTTP2、N-API/原生扩展）、Bun 专属 API 的可移植性、bun.lock 与 pnpm-lock 的迁移副作用、以及平台/容器/CPU 差异。

## Findings

### 1. 最新稳定发布与安装/支持平台

**Claim.** 官方 Releases 页当前顶部为 `Bun v1.4.2`；官方发布页记录该版本修复 `bun build` 变量名冲突、`AsyncLocalStorage` 内存泄漏、`worker_threads` 的 `online` 事件顺序、musl GC 崩溃，以及 `bun install` 的 lockfile/hash panic 等问题。

**Sources.**
- [Releases · oven-sh/bun](https://github.com/oven-sh/bun/releases) — 页面顶部显示 Bun v1.4.2，并列出其 assets；标题与版本顺序是确认当前发布线的直接证据。
- [Bun v1.4.2](https://bun.com/blog/bun-v1.4.2) — “Fixed: `bun build` variable name collision”、“Fixed: `AsyncLocalStorage` memory leak”、“Fixed: `worker_threads` 'online' event order”、“Bugfixes”章节。

**Support.** 直接证据：官方 Releases 页和发布说明。版本结论是对当前官方页面顶部排序的解释；Bun 发布会改变，因此应在 CI 中固定精确版本/镜像 tag 并记录 `bun --version`、`bun --revision`。

**Confidence.** high

**Claim.** Bun 是单一、无依赖可执行文件，可用安装脚本、包管理器或 Docker 在 macOS、Linux、Windows 安装。Linux 安装需要 `unzip`；glibc 二进制要求 glibc 2.17+，无 glibc 的系统可用 musl 版本；x64 要求 SSE4.2，macOS 要求 13.0+。官方安装页建议安装后运行 `bun --version` 与 `bun --revision`。

**Sources.**
- [Installation — Bun Docs](https://bun.sh/docs/installation) — “Overview”、“Installation”、“Direct Downloads”、“Musl Binaries”、“CPU Requirements”章节。

**Support.** 直接证据：安装页明确列出平台、glibc/musl、CPU 和 macOS 约束。研究者推论：生产镜像、CI runner、旧 VM 和 Windows ARM/x64 需在上线前逐平台探测，不应只在开发机验证。

**Confidence.** high

### 2. `bun install`、lockfile 与 pnpm/package-manager 行为

**Claim.** `bun install` 读取 `package.json`，安装 `dependencies`、`devDependencies`、`optionalDependencies`，默认安装 peer dependencies，执行项目自身生命周期脚本，并写项目根目录的 `bun.lock`。已安装依赖的生命周期脚本默认不执行，必须放入 `trustedDependencies`；这是 Bun 的供应链安全默认值。

**Sources.**
- [bun install — Bun Docs](https://bun.sh/docs/pm/cli/install) — “Basic Usage”、“Lifecycle scripts”章节。

**Support.** 直接证据：上述章节逐项列出安装范围、peer 默认行为、锁文件和 trusted dependency 规则。迁移含义：pnpm/npm 中依赖的 `postinstall` 若未加入信任名单，安装后行为可能缺失；需要把原生模块、代码生成和 ORM 生成步骤列为审查项。

**Confidence.** high

**Claim.** `bun.lock` 是当前文本锁文件格式；Bun 1.2 前的二进制 `bun.lockb` 可按官方命令转换。`bun install` 在没有 `bun.lock` 时可自动迁移 Yarn v1、npm lockfile v2/3/4 和 pnpm lockfile；npm 6 及更旧的 lockfile v1 不迁移，而是告警并从 `package.json` 重新解析。原锁文件会保留，验证后才应删除。

**Sources.**
- [Lockfile — Bun Docs](https://bun.sh/docs/pm/lockfile) — “Text-based lockfile”、“Automatic lockfile migration”章节。
- [bun install — Bun Docs](https://bun.sh/docs/pm/cli/install) — “Lockfile”、“pnpm migration”章节。

**Support.** 直接证据：文档明确列出迁移的 lockfile 版本、保留原文件以及 `bun.lockb` 转换命令。推论：迁移分支应先在干净工作树生成并审阅 `bun.lock`，比较解析版本、integrity、peer/platform 选择和脚本结果，而不是把一次成功安装当作等价证明。

**Confidence.** high

**Claim.** 可复现 CI 安装使用 `bun ci` 或 `bun install --frozen-lockfile`；两者要求提交 `bun.lock`，package.json 与锁文件不一致会失败。`--production` 隐含 frozen lockfile，但只阻止新装 devDependencies，不会删除 node_modules 中已有的 devDependencies；清理应使用 `bun prune --production`。Bun 不会在 CI 自动打开 frozen lockfile。

**Sources.**
- [bun install — Bun Docs](https://bun.sh/docs/pm/cli/install) — “Production mode”、“CI/CD”、“Offline installs”章节。

**Support.** 直接证据：文档明确写出 CI 不会自动启用 frozen、`bun ci` 等价关系、生产安装的边界和 `--dry-run` 校验方式。研究者推论：Docker/CI 应使用 `bun ci`，并将 lockfile 及 Bun 精确版本作为构建输入。

**Confidence.** high

**Claim.** Bun 支持 hoisted 和 isolated 两种安装策略；新 workspace/monorepo 默认 isolated，新单包项目默认 hoisted，旧项目为了兼容保留 hoisted，lockfile 的 `configVersion` 控制默认值。isolated 会在 `node_modules/.bun` 建中心 store 并用 symlink，能暴露未声明的 phantom dependencies。

**Sources.**
- [bun install — Bun Docs](https://bun.sh/docs/pm/cli/install) — “Installation strategies”、“Default strategy”章节。
- [Isolated installs — Bun Docs](https://bun.sh/docs/pm/isolated-installs) — isolated linker 和 phantom dependency 说明。

**Support.** 直接证据：官方列出各项目类型的默认 linker 和 isolated 的目录/声明隔离。推论：pnpm 项目迁移尤其要检查隐式依赖；新 isolated 结果可能揭露过去依赖 hoisting 的代码。

**Claim.** Bun 自动迁移 pnpm 7–9 lockfile（包括 pnpm 11 的多文档文件），保存解析版本和 integrity，迁移 workspace、catalog、overrides、patches 及多种依赖协议；pnpm 原文件保留。限制包括 workspace package 必须有 `name`、迁移时所有 workspace package.json 必须在磁盘上、相对 `link:` 和带子目录的 git `resolution.path` 不支持；失败时会说明原因并从头解析。迁移完成后可删除 pnpm 文件。

**Sources.**
- [bun install — Bun Docs](https://bun.sh/docs/pm/cli/install) — “pnpm migration”、“Lockfile Migration”、“Requirements and limitations”章节。

**Support.** 直接证据：官方逐项列出保留内容、版本和限制。推论：对于 pnpm monorepo，迁移命令必须在完整 workspace checkout 执行；Docker 若只 COPY 部分 workspace manifests，可能导致迁移失败或重新解析。

**Confidence.** high

### 3. 运行 TypeScript/JavaScript、Node built-ins 与 Web APIs

**Claim.** Bun 可直接运行 JavaScript/TypeScript，支持 top-level await、JSX 和 `.ts` 扩展导入；官方建议安装 `@types/bun`，并给出 tsconfig compilerOptions。Bun 的运行时转译不是类型检查器；bundler 文档明确说 bundler 不替代 `tsc` 的 typecheck 或 declaration generation。

**Sources.**
- [TypeScript — Bun Docs](https://bun.sh/docs/runtime/typescript) — “Suggested compilerOptions”章节。
- [Bundler — Bun Docs](https://bun.sh/docs/bundler) — “The Bun bundler is not intended to replace `tsc`...”段落。

**Support.** 直接证据：官方明确支持语法和 `@types/bun`，并明确 bundler 与类型检查职责不同。推论：React/Vite 的类型检查、声明生成和 lint 仍应保留现有工具链，不应因 `bun run` 能执行 TS 就删掉 `tsc --noEmit`。

**Confidence.** high

**Claim.** Node compatibility 页面宣称：如果一个在 Node.js 工作的 package 在 Bun 不工作，Bun 将其视为 bug；同时页面明确该兼容性“不是 100%”。当前页面按 Node.js v26 更新，并按模块标出 fully/partially/not implemented 及具体差异。

**Sources.**
- [Node.js Compatibility — Bun Docs](https://bun.sh/docs/runtime/nodejs-compat) — 开头的兼容性声明；“Built-in Node.js modules”、“Node.js globals”章节。

**Support.** 直接证据：开头承诺和“不为 100%”的限定同时存在；模块表是当前边界的规范性证据。研究者推论：该页面应成为依赖审核的第一索引，但不能替代应用级测试。

**Confidence.** high

**关键已实现/边界（以当前 compatibility 页面为准）：**

- `node:fs`：标为 fully implemented，Node 测试通过率页面给出 98%，但 `Stats` 缺少 Temporal.Instant getters。
- `node:http`：标为 fully implemented，但 `http.Server` 不继承 `net.Server`，`listen(handle)` 及 `fd`、`ipv6Only`、`signal` 选项被忽略；server 的 `keepAlive`/`keepAliveInitialDelay` 是 no-op。
- `node:https`：标为 partially implemented；server 请求 socket 不是 `tls.TLSSocket`，缺少 `getPeerCertificate`、`getCipher`、`setSecureContext`、`addContext`、`SNICallback`、`handshakeTimeout`。
- `node:async_hooks`：`AsyncLocalStorage`/`AsyncResource` 实现，但 `createHook` 和 async-id APIs 是 stub；AsyncLocalStorage context 不传播到 MessagePort/BroadcastChannel/Worker events。
- `node:child_process`：支持部分 handle IPC，但 HTTP server sockets 不可传递，advanced serialization 只适用于 Bun↔Bun，且有 stdio/channel 差异。
- `node:cluster`：net/dgram worker 共享行为已实现；HTTP/HTTPS worker 每个绑定自己的 socket，跨进程负载均衡只在 Linux 通过 `SO_REUSEPORT` 支持，官方称“not battle-tested”。
- `node:crypto`：BoringSSL 后端带来算法/曲线边界，包括缺少 `ed448`、`x448`、`secp256k1` 以及若干 cipher；`setFips()` 是 no-op。
- `node:http2`：client/server 标为 implemented，页面给出约 94% Node test suite 通过，但部分选项被忽略。
- `node:module`：缺少多个现代 loader/source-map API；`syncBuiltinESMExports`、`module._load`、`module.register` 等为 no-op，官方建议用 `Bun.plugin`。
- `node:v8`：部分实现，序列化使用 JavaScriptCore wire format 而非 V8，多个 profiling/coverage API 缺失。
- `node:worker_threads`：部分实现；`resourceLimits`、`trackUnmanagedFds` 被忽略，缺少 `moveMessagePortToContext` 和 `locks`。
- `node:sqlite`：标为 fully implemented，但 `backup()` 同步阻塞 event loop；macOS 使用系统 SQLite，扩展/session 能力可能需 `Database.setCustomSQLite`。
- `node:test`：标为 partially implemented；在 `bun test` 下 API 可用，但 Node CLI runner、reporters、coverage、snapshot、`mock.module()`、`--test-only` 等缺失或不完整；官方建议使用 `bun:test`。
- `node:sea`：not implemented；官方建议用 `bun build --compile`。

**Sources.**
- [Node.js Compatibility — Bun Docs](https://bun.sh/docs/runtime/nodejs-compat) — 每个 `node:*` 小节（特别是 `node:async_hooks`、`node:https`、`node:test`、`node:v8`、`node:worker_threads`、`node:sea`）。

**Support.** 直接证据：以上为兼容性页面中的逐模块状态/限制摘要。推论：依赖 observability、worker、TLS、HTTP2、native addon、test runner 或 V8 internals 的项目应列为高风险，不能只做 import smoke test。

**Confidence.** high

**Claim.** Web APIs 方面，Bun 文档列出 fetch/Request/Response/Headers、URL、Workers/message channels、streams、Blob、WebSocket、encoding、crypto、performance、events 等；但“部分或完全支持”并非浏览器全量兼容。当前兼容矩阵例如：Request 缺少 `keepalive`/`duplex`，Readable/Transform streams 不能 transfer，`Storage`/localStorage/sessionStorage 不实现，WebSocket 的 binaryType 默认是 `nodebuffer` 而 Node 默认 blob。

**Sources.**
- [Web APIs — Bun Docs](https://bun.sh/docs/runtime/web-apis) — API 分类表。
- [Node.js Compatibility — Bun Docs](https://bun.sh/docs/runtime/nodejs-compat) — “Node.js globals”中 Request、ReadableStream、Storage、WebSocket 等小节。

**Support.** 直接证据：官方 API 表和逐 API 限制。推论：React/Vite 浏览器代码仍由浏览器执行；只有 SSR、测试、构建脚本运行在 Bun 时，才应针对这些差异做 runtime-specific 测试。

**Confidence.** high

### 4. 测试与 bundler

**Claim.** `bun test` 是内置、Jest-compatible runner，支持 TS/JSX、hooks、snapshot、UI/DOM、watch 和 preload；默认一个进程共享 global，可用 `--parallel` 按文件跨 CPU 并行；单测默认 timeout 5000ms。它支持 GitHub Actions annotations 与 JUnit XML。官方同时说明 Jest 并非全部实现。

**Sources.**
- [Test runner — Bun Docs](https://bun.sh/docs/test) — 开头能力列表、“Run tests”、“CI/CD integration”、“Timeouts”、“Concurrent test execution”章节。

**Support.** 直接证据：官方功能和限制。推论：从 Vitest/Jest 迁移不能只替换脚本；必须核对 module mocking、coverage、snapshot、fake timers、worker isolation、test ordering 和 reporter 输出。

**Confidence.** high

**Claim.** `bun build` CLI/API 支持 watch、browser/bun/node targets，默认 ESM，CJS/IIFE 是 experimental；支持 TS/JSX/CSS/JSON/HTML 等 loaders、tree-shaking、splitting、plugins、sourcemap。官方明确 Bun bundler 不用于 typecheck/declaration。`target: "bun"` 输出带 `// @bun` pragma；`target: "node"` 不 polyfill Bun global/bun:* modules；browser target 可解析 Node built-ins 但 fs 等函数不能在 browser 调用。

**Sources.**
- [Bundler — Bun Docs](https://bun.sh/docs/bundler) — “At a Glance”、“Content types”、“target”、“format”、“The Bun bundler is not intended to replace `tsc`”。
- [esbuild — Bun Docs](https://bun.sh/docs/bundler/esbuild) — Bun 与 esbuild API 差异，包括 Bun 默认 bundle、插件 API 是子集。

**Support.** 直接证据：官方标示 target、实验性 format 和职责边界。推论：对 React/Vite 项目，Bun 可作为运行器或包管理器而不必替代 Vite；若替换 Vite bundling，应单独比较 alias、plugin、HTML、CSS、SSR、asset、env、sourcemap 和 output contract。

**Confidence.** high

### 5. 内置 SQLite、Redis、S3、HTTP、WebSocket、文件 API

**Claim.** `bun:sqlite` 是同步、高性能内置 SQLite3 driver，支持事务、参数、prepared statements、BLOB→Uint8Array、bigint、multi-query、迭代和 WAL；官方建议多数应用启用 WAL。同步 API 意味着长查询/备份会阻塞 event loop；macOS 系统 SQLite 与 Linux/Windows 自带 SQLite 的 WAL sidecar/扩展行为可能不同。

**Sources.**
- [SQLite — Bun Docs](https://bun.sh/docs/api/sqlite) — 开头能力列表、“WAL mode”、“Transactions”、“loadExtension”、“safeIntegers”章节。
- [Node.js Compatibility — Bun Docs](https://bun.sh/docs/runtime/nodejs-compat) — `node:sqlite` 小节。

**Support.** 直接证据：SQLite API、同步性质、WAL 和 macOS caveat。研究者推论：Python FastAPI 侧的 PostgreSQL/SQLAlchemy 事务和并发语义不能直接类比到 Bun SQLite；若迁移只涉及前端工具链，应不引入 `bun:sqlite` 作为无必要的架构变化。

**Confidence.** high

**Claim.** 内置 Redis client 支持 Redis 7.2+，Promise API、自动连接管理、typed responses、TLS、自动 pipeline 和指数退避重连；Pub/Sub 文档明确标为 experimental；不支持 Redis Sentinel/Cluster，MULTI/EXEC 要用 raw commands。

**Sources.**
- [Redis — Bun Docs](https://bun.sh/docs/api/redis) — 开头版本要求、“Pub/Sub”、“Reconnection Behavior”、“Limitations and Future Plans”。

**Support.** 直接证据：官方版本支持、experimental 标志、重连参数和限制。推论：生产使用前应验证 Redis 版本、Sentinel/Cluster 拓扑、事务、故障切换、命令返回类型与离线队列策略；不要把自动重连等同于业务幂等。

**Confidence.** high

**Claim.** Bun S3 API 是 native、lazy、兼容 Blob/Response 的 S3-compatible client，支持 AWS S3、R2、DigitalOcean Spaces、MinIO、Backblaze B2 等，支持流式/大文件 multipart、range reads、presigned URL 和 `s3://`；凭据从 `S3_*` 或 `AWS_*` 环境变量读取。它不是 Node AWS SDK 的 API 等价替换。

**Sources.**
- [S3 — Bun Docs](https://bun.sh/docs/api/s3) — “Bun's S3 API is fast”、“Working with S3 Files”、“Working with large files”、“Presigning URLs”、“Credentials”章节。

**Support.** 直接证据：官方 API 形态、服务范围、lazy/stream/presign 和环境变量。研究者推论：若后端已有 boto3/aiobotocore 或 `@aws-sdk/client-s3`，应先保留现有 SDK 做行为对照；只有确认签名、重试、代理、SSE、ACL、错误和 streaming 语义后才考虑替换。

**Confidence.** high

**Claim.** `Bun.file()` 是 lazy `BunFile`，符合 Blob，可读 text/json/bytes/arrayBuffer/stream；`Bun.write()` 支持 path、URL、BunFile、Blob、ArrayBuffer、TypedArray、Response；目录操作仍建议 `node:fs`。Bun 文档称这些是推荐的高性能文件 API，并列出 `FileSink` 的增量写入、flush/high-water-mark/end/unref 行为。

**Sources.**
- [File I/O — Bun Docs](https://bun.sh/docs/api/file-io) — “Reading files (`Bun.file`)”、“Writing files (`Bun.write`)”、“Incremental writing with `FileSink`”、“Directories”。

**Support.** 直接证据：API 输入输出和 lazy/streaming/生命周期说明。推论：生产迁移必须检查路径编码、权限、原子性、文件 descriptor 生命周期、Windows path、容器只读文件系统以及大文件 backpressure。

**Confidence.** high

**Claim.** `Bun.serve` 提供 Request/Response 风格 HTTP server，支持 port/hostname、Unix sockets、routes、streaming、SSE timeout 控制和 WebSocket upgrade。HTTP/2 与 HTTP/3 在 HTTP 文档中明确标为 experimental；HTTP/2 不支持 WebSocket over HTTP/2、server push 和 response trailers（gRPC 所需），`server.upgrade()` 只适用于 HTTP/1.1。

**Sources.**
- [HTTP — Bun Docs](https://bun.sh/docs/api/http) — “HTTP/2”、“HTTP/3 (QUIC)”、“idleTimeout”、“Per-Request Controls”。
- [WebSockets — Bun Docs](https://bun.sh/docs/api/websockets) — “Start a WebSocket server”、“Backpressure”、“Timeouts and limits”。

**Support.** 直接证据：官方 experimental 标志、协议限制、默认 HTTP idle timeout 10 秒、WebSocket 默认 idle 120 秒/max payload 16MB、backpressure 返回值。推论：FastAPI/Uvicorn 的 HTTP/2/WebSocket/SSE 行为不能由“都有 HTTP API”推断为相同；应做协议级和长连接 soak test。

**Confidence.** high

### 6. Windows、Docker、CI 与生产部署

**Claim.** 官方安装页支持 Windows 安装脚本和 releases 直接下载；Bun 在 Windows 具有专门 binary/shim 行为。官方环境变量文档说明 Windows 下 `bun run` scripts 自动使用 Bun Shell，可跨平台处理 shell 语法；Bun 还自动读取 `.env` 家族文件，但以 `node`/`bun --bun` 方式调用时会关闭自动 `.env` 加载以匹配 Node 行为。

**Sources.**
- [Installation — Bun Docs](https://bun.sh/docs/installation) — Windows/直接下载及平台要求。
- [Environment Variables — Bun Docs](https://bun.sh/docs/runtime/environment-variables) — “Cross-platform solution with Windows”、“When invoked as node”、“Disabling automatic .env loading”。

**Support.** 直接证据：官方 Windows 与 env 行为。推论：React/Vite 的 `.env` mode resolution 可能受启动方式影响；CI/生产应明确使用 `--env-file` 或禁用自动加载，并验证 `VITE_*`/server-only secrets 不被打包泄漏。

**Confidence.** high

**Claim.** 官方 package-manager 文档推荐 GitHub Actions 使用 `oven-sh/setup-bun`，并要求 CI 运行 `bun ci`/`--frozen-lockfile`；平台依赖被规范化写入 lockfile，当前平台不适用的包会跳过下载/安装，lockfile 可跨平台不变。`--cpu`/`--os` 可为交叉构建指定目标。

**Sources.**
- [bun install — Bun Docs](https://bun.sh/docs/pm/cli/install) — “CI/CD”、“Platform-specific dependencies”、“--cpu and --os flags”。

**Support.** 直接证据：官方 CI action、lockfile 和目标平台选择说明。推论：至少在 Linux x64、Linux arm64/musl、Windows runner 上运行依赖安装和 smoke tests；含 native addon 的包即使 lockfile 相同，实际 node_modules 也可能不同。

**Claim.** 官方发布说明给出 `oven/bun` Docker image 的 pull/run 入口；安装页说明 musl binaries。运行时转译缓存默认全局共享，Bun 的 Docker images 会自动禁用该缓存。Bun 的生产 bundler 文档支持 `bun build --production`；single-file executable 可用 `bun build --compile`，但这是 Bun 运行时形态，不能直接假定兼容 Node SEA。

**Sources.**
- [Installation — Bun Docs](https://bun.sh/docs/installation) — Docker、musl、glibc 章节。
- [Environment Variables — Bun Docs](https://bun.sh/docs/runtime/environment-variables) — “Runtime transpiler caching”章节，明确 Docker images 自动禁用缓存。
- [Bun 1.3](https://bun.com/blog/bun-v1.3) — “Production Builds”章节的 `bun build ./index.html --production --outdir=dist`。
- [Bundler — Bun Docs](https://bun.sh/docs/bundler) — target/compile 相关章节。
- [Node.js Compatibility — Bun Docs](https://bun.sh/docs/runtime/nodejs-compat) — `node:sea` not implemented。

**Support.** 直接证据：官方镜像/缓存/production build/SEA 边界。推论：多阶段 Docker 应分离 dependency install、build 和 runtime，生产镜像应固定 `oven/bun:<exact-version>` 或 digest，并在容器内执行 `bun ci`、构建后文件存在性检查和 runtime health probe。

**Confidence.** high

**Claim.** 对框架命令，官方 Next.js guide 建议在 package.json 的 `dev`、`build`、`start` 前加 `bun --bun`，确保框架实际在 Bun runtime 执行。官方 Vercel 说明强调 Next.js 仍使用自己的 Turbopack/Webpack，`bun --bun` 只改变执行 runtime；Vercel Bun runtime 仍标 public beta。该部署方式的 beta 结论仅适用于 Vercel，不应推广为 Bun 本身的稳定性承诺。

**Sources.**
- [Next.js — Bun Docs](https://bun.sh/docs/guides/ecosystem/nextjs) — “Update scripts in package.json”、“Hosting”。
- [Vercel now supports the Bun Runtime](https://bun.com/blog/vercel-adds-native-bun-support) — `bunVersion`、`bun run --bun`、build/runtime 区分和 public beta 章节。

**Support.** 直接证据：官方指南和官方发布文章。推论：在 Vite/React 项目中，`bun run vite` 只保证 Bun 启动 CLI，不保证 Vite 的 dev server/bundler 被 Bun 替换；要替换构建器需单独设计和验证。

**Confidence.** high

### 7. 从 Node.js 迁移的官方建议、风险与验证方法

**Claim.** 官方迁移信号是“先运行现有 Node.js project”：package-manager 文档说有 package.json 的 Node 项目可直接 `bun install`，兼容性文档说常见框架和 npm 包可运行，并持续运行 Node test suite。官方没有给出一个保证全自动的“Node→Bun 一键迁移”承诺，而是用兼容矩阵、issue 反馈和发布修复持续推进。

**Sources.**
- [bun install — Bun Docs](https://bun.sh/docs/pm/cli/install) — “Basic Usage”第一段。
- [Node.js Compatibility — Bun Docs](https://bun.sh/docs/runtime/nodejs-compat) — 开头兼容性声明和逐模块矩阵。
- [Bun 1.4](https://bun.com/blog/bun-v1.4) — “Node.js compatibility”及 Node test suite 统计。

**Support.** 直接证据：官方支持“existing Node.js projects”和兼容性测试，但也明确不完全兼容。推论：建议采用增量迁移：先 `bun install`/`bun run`，再选 test/build/runtime；每一步保留 Node/pnpm 对照。

**Confidence.** high

**迁移风险分级（研究者基于官方边界的 inference）：**

1. **低到中风险：**纯 JS/TS、fetch/Web APIs、常见 `node:fs/path/url/util/events`、无 native addon 的 CLI/测试工具；仍需对照测试。
2. **中到高风险：**依赖 `node:test` 的 Node CLI runner/reporters/coverage，V8 inspector/serialization，`async_hooks` hook/async IDs，`cluster` HTTP worker，多进程 IPC，TLS renegotiation/OCSP/session resumption，HTTP/2 trailers/gRPC，`require.cache`/loader hook，N-API/native addon。
3. **高风险：**依赖 Node-specific ABI、V8 internals、原生数据库驱动、平台特定 syscall/文件 watcher、Redis Cluster/Sentinel，或要求 strict WebSocket/HTTP2/S3 行为的服务。
4. **Bun 专属 API 风险：**`Bun.*`、`bun:*`、Bun bundler output、Bun Shell 和内置 clients 会产生 runtime/vendor lock-in；`target: "node"` 不提供 Bun global/bun:* polyfill。

**官方验证证据与建议：**

- 在 CI 固定 Bun 精确版本，执行 `bun --version`/`bun --revision`；不要使用未测试的 canary 作为生产版本。[Installation](https://bun.sh/docs/installation) 的 “Canary Builds” 明确 canary 是 untested。
- 先运行现有 test suite，再用 `bun test`；对 Node runner 项目保留 Node `node --test`，并按 compatibility 页面检查缺失能力。[Test runner](https://bun.sh/docs/test)、[Node.js Compatibility](https://bun.sh/docs/runtime/nodejs-compat)。
- 对 package manager 在干净工作树执行 `bun install --frozen-lockfile --dry-run`，审阅 lockfile/peer/native/platform 变化；pnpm 迁移前保留 `pnpm-lock.yaml`，比较 `pnpm install` 与 `bun ci` 的包树和脚本输出。[bun install](https://bun.sh/docs/pm/cli/install)、[Lockfile](https://bun.sh/docs/pm/lockfile)。
- 对构建产物同时跑原 Vite/Node 与候选 Bun command，比较 asset names、HTML/CSS、source maps、SSR、dynamic import、env 注入、external dependencies；不要把 Bun bundler 当 `tsc`。[Bundler](https://bun.sh/docs/bundler)。
- 对 API 做真实 HTTP/WebSocket/SSE/streaming/timeout/backpressure/large-file tests；HTTP2/HTTP3、gRPC、WebSocket over HTTP2 属于明确边界或 experimental，必须做协议级验证。[HTTP](https://bun.sh/docs/api/http)、[WebSockets](https://bun.sh/docs/api/websockets)。
- 对数据库、Redis、S3 保留真实服务容器/测试账户，验证事务、并发、重连、错误、签名、range/stream、权限和数据一致性；不要以 API 名称相似推断兼容。[SQLite](https://bun.sh/docs/api/sqlite)、[Redis](https://bun.sh/docs/api/redis)、[S3](https://bun.sh/docs/api/s3)。
- 在 Linux glibc/musl、Linux arm64、Windows 和 Docker/CI runner 上分别执行 install/build/test/health/termination probes；依据官方安装页的 glibc、SSE4.2、macOS、musl 约束做平台矩阵。[Installation](https://bun.sh/docs/installation)。
- 对生产运行做 canary/rollback：保留 Node 入口和 Docker image，记录 latency、memory、CPU、event-loop stalls、crash/exit signals、native module load、HTTP errors 和 graceful shutdown；只有真实流量/故障演练通过才扩大比例。这是研究者基于官方“非 100% 兼容”和实验性标记提出的运营建议，不是 Bun 官方 SLA。

## Contradictions

1. **“Drop-in replacement”与“不是 100% 兼容”并存。** 官方兼容页的直接表述是：Node.js 可工作的 package 在 Bun 不能工作会被视为 Bun bug；同页/矩阵又明确多个模块 partial、缺失或语义不同。应解释为兼容目标/生态策略，而非行为等价保证。
2. **“Fully implemented”不等于完全同构。** 例如 `node:http` 标为 fully implemented，但文档仍列出 `http.Server` 继承关系和 `listen()` 选项差异；`node:sqlite` 标为 fully implemented，但 backup 阻塞和 macOS SQLite 差异仍存在。迁移审查必须同时读取 status 和 caveat。
3. **Bundler 与 Vite 的职责不可直接互换。** Bun 官方 bundler 是可用能力，但官方也明确 target/format/plugin 限制、CJS/IIFE experimental、不能替代 tsc；官方 Vercel 文档则说明 Next.js 仍用自己的 bundler。没有官方证据支持“使用 Bun runtime 即自动替换 Vite/框架 bundler”。
4. **Redis client 稳定 API 与 Pub/Sub experimental 并存。** Redis 文档明确 client 基础 API 和 Pub/Sub 的 experimental 标记；不能用基础 client 的稳定性推断 Pub/Sub 可作无风险生产依赖。

## Missing evidence

- 官方文档没有针对“Python FastAPI + React/Vite + pnpm”给出一份端到端迁移方案，也没有声明 Bun 可以运行 Python/FastAPI；本文件的项目清单只覆盖 JavaScript/TypeScript/Vite 侧和跨语言部署边界。
- 官方 compatibility 页面未提供一个可导出的、针对某个项目依赖闭包的 pass/fail 报告；实际 npm 包、native addon、postinstall 与 framework plugin 仍需项目级运行验证。
- 官方 Docker 入口和发布说明证明存在 `oven/bun` 镜像，但不等于每个应用都应使用 latest tag；镜像 digest、非 root 用户、信号转发、只读文件系统、OS packages 和 SBOM 需由项目自行审计。
- 发行页当前顶部版本会继续变化；本报告没有把未来 release/canary 作为稳定版本证据。升级时应重新抓取 Releases、Installation 和 compatibility 页面。
- 性能数字（例如 `Bun.serve`、内存/启动速度）是官方基准结果，不是本项目 FastAPI/Vite 工作负载的预测；未做项目实测，不能把它们当作容量承诺。

## 面向 Python FastAPI + React/Vite + pnpm 项目的迁移审查清单

### 版本与供应链

- [ ] 记录当前 Node、pnpm、Vite、React、测试框架、bundler plugins、native addons、lockfile 版本。
- [ ] 从官方 Releases 选择并固定 Bun 精确版本和 Docker digest；CI 输出 `bun --version`、`bun --revision`。
- [ ] 在副本分支执行 `bun install`，保留 `pnpm-lock.yaml`；审阅生成 `bun.lock`、resolved versions、integrity、peer/optional/platform packages。
- [ ] 验证所有 workspace package 有 `name`，迁移时所有 package.json 在 checkout/Docker context；检查 catalog、patch、overrides、`link:`、git subdirectory 限制。
- [ ] 对比 `pnpm install --frozen-lockfile` 与 `bun ci` 的 node_modules、脚本日志和生成文件；确认 trustedDependencies 与原生模块 install/build 步骤。
- [ ] 确认 isolated/hoisted linker 选择；清理未声明的 phantom dependencies，并把每个运行时依赖显式写入 package.json。

### React/Vite 与 TypeScript

- [ ] 保留 `tsc --noEmit`/声明生成、ESLint 和现有 Vite build；不要以 Bun bundler 代替类型检查。
- [ ] 对比 dev server HMR、React refresh、Vite plugins、alias、CSS/PostCSS/Tailwind、HTML entry、asset URL、dynamic import、SSR 和 source maps。
- [ ] 检查 `.env` 加载顺序、`NODE_ENV`、Vite mode、`VITE_*` 暴露规则；明确 `bun --bun`、`--env-file`、`--no-env-file` 的使用方式。
- [ ] 若采用 `bun build`，单独验证 browser/node/bun target、ESM/CJS、code splitting、external、minify、sourcemap、publicPath 和产物可被既有部署服务正确托管。
- [ ] 运行浏览器 E2E，不把 Bun 的 server-side Web APIs 当成浏览器 API；检查 `Storage`、WebSocket binaryType、stream transfer 等差异。

### Python FastAPI 交界

- [ ] 明确 Bun 只替换 JavaScript/TypeScript runtime/tooling；FastAPI/Uvicorn、Python dependencies、ASGI lifecycle、OpenAPI 和 Python worker 仍由 Python 工具链负责。
- [ ] 选择进程拓扑：Python API、Bun/Vite dev server、静态资产 server、reverse proxy 的端口/health/readiness/shutdown contract。
- [ ] 验证 CORS、cookie、CSRF、auth headers、upload/download streaming、SSE、WebSocket、timeouts 和 proxy headers 的跨进程行为。
- [ ] 对 Node/Bun 与 Python 共享的 Redis、S3、数据库连接，做真实数据类型、编码、TTL、事务、重试、并发、签名和错误映射对照。
- [ ] 不因 Bun 有 `bun:sqlite`/Redis/S3 而替换既有 Python 数据访问层，除非完成数据一致性、迁移、故障切换和回滚评审。

### CI、Docker 与生产

- [ ] GitHub Actions 使用官方 `oven-sh/setup-bun`，安装用 `bun ci`；Linux glibc/musl、arm64、Windows runner 至少覆盖 install/build/test smoke。
- [ ] 多阶段 Docker 中分离 lockfile/install、build、runtime；生产层只复制需要的产物和 production dependencies；验证非 root、PID 1、SIGTERM、graceful shutdown 和只读文件系统。
- [ ] 不在生产使用 canary；对 `bun install`、构建、启动、healthcheck、migration/rollback 编写可重复命令，并保存构建产物清单。
- [ ] 对 HTTP/1.1、HTTP/2/3、WebSocket、SSE、large uploads/downloads、idle timeout/backpressure 做协议级 smoke/soak tests；HTTP2/HTTP3 experimental 的场景必须有 Node/Python 回退。
- [ ] 记录 CPU、RSS、event-loop latency、启动时间、5xx、连接重置、OOM、native addon 错误、文件句柄和数据库/Redis/S3 重试；用小流量 canary 后再扩大。
- [ ] 保留原 pnpm/Node/Python 路径和可回滚镜像，明确触发条件；迁移完成前不要删除原 lockfile 或移除 Node 兼容验证。

## Sources

### Kept

- [Bun v1.4.2](https://bun.com/blog/bun-v1.4.2) — 当前发布线的 patch 修复与稳定发布说明。
- [Releases · oven-sh/bun](https://github.com/oven-sh/bun/releases) — 官方发布排序、版本和 assets。
- [Installation](https://bun.sh/docs/installation) — 平台、CPU、glibc/musl、Docker、验证和 canary。
- [bun install](https://bun.sh/docs/pm/cli/install) — 安装、生命周期、CI、linker、pnpm migration、platform dependencies。
- [Lockfile](https://bun.sh/docs/pm/lockfile) — bun.lock 格式和自动迁移。
- [Node.js Compatibility](https://bun.sh/docs/runtime/nodejs-compat) — 当前 Node.js built-ins/globals 兼容矩阵和差异。
- [TypeScript](https://bun.sh/docs/runtime/typescript) — TS 运行与类型声明配置。
- [Web APIs](https://bun.sh/docs/runtime/web-apis) — Bun 的 Web-standard API 范围。
- [Test runner](https://bun.sh/docs/test) — `bun test` 能力、CI、并行和已知 Jest 兼容边界。
- [Bundler](https://bun.sh/docs/bundler) — build targets、formats、loaders、plugins、产物和职责边界。
- [esbuild](https://bun.sh/docs/bundler/esbuild) — Bun bundler 与 esbuild/plugin 的差异。
- [SQLite](https://bun.sh/docs/api/sqlite) — `bun:sqlite`、同步事务、WAL、平台差异。
- [Redis](https://bun.sh/docs/api/redis) — Redis 7.2+、重连、pipeline、Pub/Sub experimental 和限制。
- [S3](https://bun.sh/docs/api/s3) — S3-compatible files、streaming、presign、credentials。
- [File I/O](https://bun.sh/docs/api/file-io) — Bun.file/Bun.write/FileSink。
- [HTTP](https://bun.sh/docs/api/http) — Bun.serve、timeouts、HTTP2/3 experimental 边界。
- [WebSockets](https://bun.sh/docs/api/websockets) — upgrade、backpressure、payload/idle limits。
- [Environment Variables](https://bun.sh/docs/runtime/environment-variables) — `.env` precedence、Windows Shell、Docker cache。
- [Next.js](https://bun.sh/docs/guides/ecosystem/nextjs) — 官方 `bun --bun` framework invocation guidance。
- [Vercel now supports the Bun Runtime](https://bun.com/blog/vercel-adds-native-bun-support) — 官方部署说明，明确 runtime 与 framework bundler 区分，并标 public beta。
- [Bun 1.4](https://bun.com/blog/bun-v1.4) — 官方 Node test suite 统计、生产 benchmark、兼容改进补充。

### Rejected/deprioritized

- 非官方博客、教程、benchmark 汇总、Stack Overflow、论坛和二手迁移指南 — 用户要求只使用 Bun 官方一方资料。
- `oven-sh/bun` GitHub issues/PRs — 未作为本报告的核心证据，因为 issue 内容可能是未发布修复、用户报告或讨论；仅官方 docs/release 页面已足够覆盖风险。若后续遇到项目特定崩溃，应针对该版本再查官方 issue/release。
- Node.js、MDN、Redis、SQLite、AWS、Vite 等上游资料 — 本报告只用 Bun 官方页面来描述 Bun 行为；这些资料可用于协议/生态对照，但不作为本报告的 Bun 证据。
