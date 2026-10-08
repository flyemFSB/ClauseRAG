# Bun 包管理器与 Vite+ 覆盖评估

> 调研日期：2026-10-05。范围限定为 `frontend/`：评估 `pnpm -> bun install/bun ci`，以及 Bun 内置工具对 Vite+ `vp` 的覆盖关系。后端不在范围内。官方证据见 [bun-official-evidence.md](./bun-official-evidence.md)。

## 直接答案

### 将 pnpm 换成 Bun 包管理器会存在问题吗？

**会有迁移问题，但不是当前依赖无法安装的问题。**

当前项目已在隔离副本中证明 Bun 可以安装并运行前端：

- `bun install` 成功安装 589 个包。
- `bun run build` 成功执行 `vp build`。
- 4 个测试文件、27 个测试全部通过。

但当前项目直接执行：

```powershell
bun install --frozen-lockfile --dry-run
```

失败。原因是 Bun 发现 `pnpm-lock.yaml` 后会启动 pnpm lockfile 迁移，并将 `pnpm-workspace.yaml` 中的部分配置转移到 `package.json`。迁移结果与冻结安装状态不一致，因此 frozen install 失败。

这说明：

- **依赖解析和 Vite+ 执行层面可行。**
- **不能把 `pnpm install --frozen-lockfile` 直接替换成 `bun install --frozen-lockfile`。**
- 迁移必须生成并提交独立的 `bun.lock`，同时确认 workspace/catalog/override/peer 配置的最终位置。

### Bun 内置功能是否完整覆盖 Vite+？

**不完整覆盖。Bun 和 Vite+ 是不同层级的工具。**

Bun 内置的是：

```text
JavaScript/TypeScript runtime
package manager
script runner
bundler
test runner
```

Vite+ 提供的是：

```text
项目工具链 CLI
Vite/Rolldown 构建集成
React/Vite/Tailwind 插件管理
type-aware check 编排
Vitest 集成
format/lint/check/test/build/dev/preview 等统一命令面
```

Bun 可以替代 Vite+ 的底层运行环境和部分独立能力，但不能声明为 Vite+ 的完整替代品。对本项目来说，正确方案是：

```text
Bun package manager/runtime
  -> Vite+ vp
      -> Vite+ bundled Vite/Rolldown
      -> React plugin
      -> Tailwind Vite plugin
      -> Vitest
```

## 项目配置为什么需要谨慎迁移

当前项目的 `frontend/pnpm-workspace.yaml` 包含 Vite+ 手工安装所需的配置：

```yaml
catalog:
  vite: npm:@voidzero-dev/vite-plus-core@1.0.0
  vite-plus: 1.0.0

overrides:
  vite@*: "catalog:"
  vitest@*: 5.0.1

peerDependencyRules:
  allowAny:
    - vite
  allowedVersions:
    vite: "*"
```

其目的不是普通 workspace 声明，而是保证：

1. 项目使用 Vite+ bundled core，而不是第二份独立 Vite。
2. Vitest 使用 Vite+ 兼容的固定版本。
3. Vite+ core 的特殊版本号不会被 peer dependency 检查误判。

Bun 的 workspace 语法和配置位置不同。Bun catalogs 需要 workspace 根 `package.json` 中存在非空 `workspaces`；Bun 迁移 pnpm lockfile 时会把相关配置转换到 `package.json`。当前仓库在 Bun 探针后出现了：

```json
"workspaces": {
  "catalog": {
    "vite": "npm:@voidzero-dev/vite-plus-core@1.0.0",
    "vite-plus": "1.0.0"
  }
},
"overrides": {
  "vite@*": "catalog:",
  "vitest@*": "5.0.1"
}
```

这部分转换方向是合理的，但不能只看 JSON 是否生成，还要确认 Bun 的 peer resolver 最终安装的是同一份 Vite+ core，以及 `vp` 的命令和 Vitest 运行时没有第二份 Vite/Vitest。

## Bun 与当前 Vite+ 命令面的覆盖矩阵

| 当前命令/能力 | Bun 是否能直接覆盖 | 正确判断 |
| --- | --- | --- |
| `vp dev` | Bun 可启动 `vp` | **可覆盖执行 runtime，不替换 `vp dev`** |
| `vp build` | Bun 可启动 `vp` | **已实测通过，不等于使用 `bun build`** |
| `vp preview` | Bun 可启动 `vp` | 高概率可用，需启动后验证端口和静态资源 |
| `vp test` | Bun 可启动 Vite+ bundled Vitest | **已实测通过**，保留 `vite-plus/test` |
| `vp check` | Bun 可启动 `vp` | 需要专门跑一次，作为迁移门槛 |
| `vp lint` | Bun 可启动 `vp` | 可保留 Vite+ 的 lint 编排，不等于 Bun lint |
| `vp fmt` | Bun 可启动 `vp` | 可保留 Vite+ 的 formatter，不等于 Bun formatter |
| `vp install` | Bun 有 `bun install` | **命令语义和 lockfile 不同，不是无缝替换** |
| `vp exec` / `vp run` | `bunx` / `bun run` 有相近能力 | 参数、环境变量和命令解析仍需逐项替换验证 |
| `vp toolchain` | Bun 没有等价的 Vite+ toolchain 管理 | **不能完整覆盖** |
| `vp migrate` | Bun 没有 Vite+ 项目迁移规则 | **不能完整覆盖** |
| `vp create` | `bun create` 有项目生成能力 | 模板、配置和 Vite+ 集成不等价 |
| `vp cache` | Bun 有缓存相关能力 | 缓存目录、清理语义和 Vite+ 缓存不等价 |
| `vp hooks` / `vp staged` | Bun 无完整等价命令面 | 仍需 Vite+ 或 Git hook 工具 |
| `vp pack` | Bun 有 `bun pm pack` | package 打包细节和 workspace 替换需验证 |
| `vp check` 的 type-aware 检查 | Bun bundler 不提供 | 仍由 TypeScript/Vite+ 工具链负责 |
| Vite config/plugins | Bun 可作为 host | Vite+ / Vite plugin 仍然负责 |
| Vite+ bundled Vitest | Bun 可作为 host | Bun `bun:test` 不能直接替换它 |
| Bun bundler | 有 | **不是 Vite+ bundler 的完整替代品** |

## 具体会遇到的问题

### 1. `pnpm-lock.yaml -> bun.lock` 会产生新的事实源

迁移后不能继续依赖 pnpm 的 frozen install 语义。正式 Bun 路径需要：

```powershell
bun install
bun ci
```

并提交 `bun.lock`。`bun ci` 要求 `package.json` 与 `bun.lock` 一致；它不会把 `pnpm-lock.yaml` 当作正式锁文件继续使用。

建议：

- 在独立分支生成 `bun.lock`。
- 保留 `pnpm-lock.yaml` 直到 Bun CI 连续稳定通过。
- 迁移完成后不要长期维护两个正式 lockfile。
- 对比两边的 resolved version、integrity、peer、optional/native package 和安装脚本。

### 2. workspace/catalog/override/peer 规则需要重新确认

当前 Vite+ 配置依赖 pnpm 的 `peerDependencyRules`。Bun 有 `overrides` 和 workspace catalogs，但不应假设所有 pnpm peer 规则有逐字段等价物。

重点检查：

- `vite` 是否最终只解析到 `@voidzero-dev/vite-plus-core`。
- `vitest` 是否固定为 Vite+ 需要的 `5.0.1`。
- `@vitejs/plugin-react`、`@tailwindcss/vite`、`vite-plus` 的 peer warning 是否消失。
- `bun install` 是否产生第二份独立 Vite。
- `bun pm ls` 或等价依赖树输出是否符合当前 pnpm 结果。
- `bun update` 对 catalog 的更新行为是否符合预期。

### 3. Bun 安装脚本更严格

Bun 对已安装依赖的生命周期脚本默认可能需要 `trustedDependencies` 才会执行。当前依赖树中有大量平台相关包和原生 binding，必须检查：

- `@tailwindcss/oxide` 平台包。
- Vite+/Rolldown/OXC 的平台 binding。
- `lightningcss` 平台包。
- 其他 optional dependency 是否被正确安装。
- 安装后是否生成 Vite+ 需要的 CLI 或运行时文件。

“`bun install` 成功”不能单独证明依赖行为等价。

### 4. 安装布局可能变化

Bun 支持 hoisted 和 isolated 安装策略。pnpm 项目迁移后可能得到不同的 `node_modules` 布局。不同布局会暴露两类问题：

- 过去依赖未声明的 phantom dependency 的包可能无法解析。
- 某些工具通过路径推断、symlink 或 `node_modules` 结构读取资源时行为变化。

Vite+ 自身有较复杂的 `vite` alias 和 bundled core 约束，因此必须做依赖树和构建结果对比。

### 5. Windows 与 CI 命令需要切换

当前仓库脚本使用 pnpm：

```powershell
pnpm install
pnpm exec vp dev
```

正式切换需要改为：

```powershell
bun ci
bun run vp dev
```

同时检查：

- `scripts/dev.ps1` 的命令查找和错误提示。
- CI 的 Node/pnpm setup 改为固定 Bun 版本。
- `.env` 自动加载是否与 Vite mode 行为一致。
- Bun Shell 与 PowerShell 的参数/引号/退出码行为。
- `bun run vp dev` 的子进程信号和停止行为。

## Bun 内置能力能否覆盖 Vite+？

### Bun 可以覆盖的部分

Bun 可以直接承担：

- JavaScript/TypeScript CLI 的运行。
- `package.json` scripts 的执行。
- npm registry 依赖安装。
- workspace 和 catalog 的基础依赖管理。
- lockfile 和 frozen CI 安装。
- 基础测试 runner。
- 独立的 bundler。
- 基础文件、HTTP、WebSocket 等 runtime API。

这些能力足够支撑：

```powershell
bun ci
bun run vp dev
bun run vp build
bun run vp check
bun run vp test -- --run
bun run vp preview
```

### Bun 不能完整覆盖的部分

Bun 不能直接替代 Vite+ 的项目层能力：

- Vite+ 对 Vite/Rolldown 的统一集成。
- Vite+ 的命令编排和项目配置约定。
- Vite+ bundled Vitest 与 `vite-plus/test` 入口。
- Vite+ 的 `toolchain`、`migrate`、`hooks`、`staged` 等命令。
- 当前项目需要的 Vite alias、React plugin、Tailwind plugin 和 peer 兼容规则的完整组合。
- Vite+ 官方升级路径及其对 Vite core/React plugin/Vitest 版本的联动管理。

所以不能把目标写成：

```text
Vite+ -> Bun 全部替换
```

而应写成：

```text
pnpm -> Bun package manager
Node -> Bun runtime
Vite+ -> 保留
Vite+ plugins -> 保留
Vitest -> 保留
```

## 推荐迁移方案

### 推荐：Bun package manager + Bun runtime，Vite+ 保留

先在独立分支执行：

```powershell
cd frontend
bun install
bun run vp check
bun run vp build
bun run vp test -- --run
bun run vp preview
```

确认结果后提交：

```text
frontend/bun.lock
frontend/package.json 的 Bun workspace/catalog/override 配置
必要的 trustedDependencies
CI 和 scripts/dev.ps1 的 Bun 命令
```

迁移期间保留：

```text
frontend/pnpm-lock.yaml
Node 24 回退环境
pnpm 安装和验证命令
```

### 不推荐：同时移除 Vite+

不要把以下事情绑定在同一个迁移中：

```text
pnpm -> bun
Node -> bun
vp -> bun build
vite-plus/test -> bun test
```

这样会同时改变依赖解析器、runtime、bundler、测试 runner 和命令编排器，出现问题时无法判断根因。

## 最终判断

**将 pnpm 换成 Bun 是可行的，但当前项目必须做一次真实的 lockfile/workspace 迁移；直接替换命令存在配置漂移和 frozen install 失败问题。**

**Bun 内置功能不能完整覆盖 Vite+，但没有必要覆盖。** 最合理的架构是 Bun 负责安装和运行，Vite+ 继续负责前端项目工具链：

```text
Bun install/ci + Bun runtime
        |
        v
Vite+ vp
        |
        +-- Vite/Rolldown
        +-- React plugin
        +-- Tailwind plugin
        +-- Vitest
```

对本项目的可执行结论：

1. 可以迁移 `pnpm -> bun`，但需要新建并审阅 `bun.lock`。
2. 可以迁移 `node -> bun`，当前 build/test 已通过。
3. 不要迁移 `vp -> bun build`，两者不是同一层级。
4. 不要迁移 `vite-plus/test -> bun:test`，没有必要且会扩大风险。
5. Bun 迁移后正式命令应是 `bun ci`、`bun run vp ...`，而不是删除 `vp`。
6. 在 Bun CI 连续通过前，保留 Node/pnpm 回滚路径。

## 官方来源

- [Vite+ Migration Rules](https://viteplus.dev/guide/migrate-rules)
- [Vite+ Build Config](https://viteplus.dev/config/build)
- [Bun install](https://bun.sh/docs/pm/cli/install)
- [Bun Lockfile](https://bun.sh/docs/pm/lockfile)
- [Bun Isolated Installs](https://bun.sh/docs/pm/isolated-installs)
- [Bun Node.js Compatibility](https://bun.sh/docs/runtime/nodejs-compat)
- [Bun Test Runner](https://bun.sh/docs/test)
- [Bun Bundler](https://bun.sh/docs/bundler)
- [Bun Environment Variables](https://bun.sh/docs/runtime/environment-variables)
