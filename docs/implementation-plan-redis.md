# Redis 四项能力详细实施方案

> 状态：能力一（速率限制）、能力二（短 TTL 检索缓存）与能力三（缓存回源锁）已落地；能力四（一般短租约锁）按本文第 11 节
> 的顺序待有真实重复工作指标后接入，当前未接线。
>
> 实施差异（相对本方案）：限流用单条 Lua 脚本把递增、首次过期与剩余窗口放在同一服务端操作；键前缀为
> `clauserag:{purpose}:v1`，环境区分由 `REDIS_KEY_PREFIX` 与 `REDIS_URL` 指向的实例/库共同承担；回源锁 TTL 默认
> 30s（第 6.2 节要求它大于回源 p99）；上传限额取 30/60s（前端支持一次选多个文件顺序上传）；只有通道未失败、
> 重排未降级的投影才入缓存，避免把供应商的瞬时故障固化一个 TTL；缓存端口带 `enabled`，关闭时连语料版本都不查；
> 信封的 `schema_version` 在读取时比对。已删除 `REDIS_RETRY_ON_TIMEOUT`（redis-py 8 已废弃该参数，且其默认 Retry
> 是 10 次抖动重试，这里统一固定为不重放命令），`REDIS_COORDINATION_LOCK_TIMEOUT_SECONDS` 随能力四推迟；
> 业务 Redis 未接入 readiness；缓存一致性由「语料版本进键 + 短 TTL 抖动」承担，未接主动删除（版本进键后旧值
> 不可能再被命中，删除只提前释放内存）。容器路径的三个开关从根 `.env` 透传，写 `false` 重启即完成回滚。
>
> 适用范围：ClauseRAG API、Agent Runtime、Worker 的业务 Redis；Langfuse 使用的 Redis 仍由 Langfuse 独立管理。
>
> 核心原则：Redis 是可降级的派生基础设施。PostgreSQL 仍是业务事实源，RabbitMQ + Taskiq 仍是唯一业务队列。Redis 故障、重启、淘汰或数据丢失不得损坏任务、会话、合同、引用或权限事实。

## 1. 本次交付范围

计划落地四项能力：

1. **速率限制**：限制 API、问答、上传和昂贵供应商调用，保护容量与费用。
2. **短 TTL 检索缓存**：缓存可重建的 Retrieval Debug/候选结果，不缓存最终法律回答。
3. **缓存一致性锁**：用 `redis-py` 内置 `Lock` 协调同一个缓存 key 的回源和失效后的重建，降低 cache stampede。
4. **短租约锁**：同样使用 `redis-py` 内置 `Lock`，只保护非权威的重复工作，不参与 PostgreSQL 任务认领或业务事实提交。

第三、四项都使用 `redis-py` 的 `Lock`，但用途和 keyspace 必须区分：

- `lock:v1:cache-rebuild:*`：缓存回源锁；拿不到锁的请求等待很短时间后读取已有值或旁路执行。
- `lock:v1:coordination:*`：一般短租约协调锁；只保护重复刷新/能力探测等非权威操作。

`redis-py Lock` 不是数据库锁，也不是 PostgreSQL fencing 的替代品。锁到期后，旧持有者仍可能继续执行；所有写入业务事实的操作仍必须通过 PostgreSQL 条件写、job attempt 或 lease token 验证。

## 2. 当前仓库前置改动

实施前需要完成以下基础改动：

### 2.1 依赖

在根目录 `pyproject.toml` 增加已验证版本范围：

```toml
"redis>=8.1,<9",
```

执行 `uv lock`，提交 `uv.lock`。业务代码只使用 `redis.asyncio`，不在异步 FastAPI/Worker 路径调用同步 Redis 客户端。

### 2.2 配置

在 `infrastructure/config/settings.py` 增加以下配置。名称按当前项目的环境变量映射规则使用大写环境变量：

```text
REDIS_ENABLED=false
REDIS_URL=redis://:password@redis-business:6379/0
REDIS_CONNECT_TIMEOUT_SECONDS=1
REDIS_SOCKET_TIMEOUT_SECONDS=1
REDIS_HEALTH_TIMEOUT_SECONDS=1
REDIS_MAX_CONNECTIONS=32
# REDIS_RETRY_ON_TIMEOUT 已删除：见文首实施差异（redis-py 8 已废弃该参数，统一固定为不重放命令）
REDIS_RATE_LIMIT_ENABLED=false
REDIS_CACHE_ENABLED=false
REDIS_CACHE_TTL_SECONDS=60
REDIS_CACHE_TTL_JITTER_SECONDS=10
REDIS_CACHE_LOCK_BLOCKING_TIMEOUT_SECONDS=0.15
REDIS_CACHE_LOCK_TIMEOUT_SECONDS=5
REDIS_COORDINATION_LOCK_TIMEOUT_SECONDS=10
REDIS_MAX_CACHE_VALUE_BYTES=1048576
```

约束：

- `REDIS_ENABLED=false` 时，不创建业务 Redis 客户端，不探测业务 Redis，不影响业务启动。
- `REDIS_URL` 使用 `SecretStr`，不能进入 `/api/v1/config`、异常详情或日志。
- 业务 Redis URL 不得指向 Langfuse 的 DB 1；建议使用独立实例，至少使用独立 ACL 用户和 key prefix。
- 所有 timeout 必须有上限；禁止无限连接或无限等待锁。
- `REDIS_RETRY_ON_TIMEOUT` 默认关闭。应用层只对明确的瞬态连接建立失败做有界重试，禁止命令无界重放。

### 2.3 装配与生命周期

新增明确边界的基础设施模块，不创建 `utils`、`common` 或 `manager`：

```text
backend/src/infrastructure/redis/client.py
backend/src/infrastructure/redis/rate_limiter.py
backend/src/infrastructure/redis/cache.py
backend/src/infrastructure/redis/locks.py
backend/src/composition/shared/redis.py
```

建议接口方向：

```text
application 只依赖：
  RateLimiterPort
  RetrievalCachePort
  CacheRebuildLockPort
  CoordinationLockPort

infrastructure 实现这些端口并依赖 redis.asyncio。
composition 负责创建一个进程内 Redis 客户端/连接池并在 shutdown 时 await aclose()。
domain 不导入 Redis。
```

先不要抽象成通用 `RedisManager` 或 `CacheManager`。四项能力虽然共享连接池，但业务语义不同，接口应保持窄而明确。

## 3. Keyspace 与数据分类

统一前缀：

```text
clauserag:{environment}:{purpose}:v1:{...}
```

示例：

```text
clauserag:prod:rl:v1:{principal}:{route}:{window}
clauserag:prod:cache:v1:retrieval:{tenant}:{knowledge_base}:{revision}:{query_hash}:{config_hash}
clauserag:prod:lock:v1:cache-rebuild:{cache_key_hash}
clauserag:prod:lock:v1:coordination:{resource_hash}
```

规则：

- key 不包含合同正文、完整问题、邮箱、API key、密码或 access token。
- 用户可控文本只进入带版本的 SHA-256 摘要；摘要本身不作为安全授权依据。
- key 必须含环境和用途，避免开发/测试/生产碰撞。
- cache value 必须含 `schema_version`、`corpus_revision`、`created_at` 和来源状态。
- 所有临时 key 必须带 TTL；禁止永久写入。
- 速率限制 key、缓存 key、锁 key 使用不同前缀，并尽量使用不同 Redis 实例。

## 4. 能力一：速率限制

### 4.1 首期策略

首期实现固定窗口计数，不提前实现滑动窗口或令牌桶。目标是先保护资源并建立真实流量基线。

每个路由声明策略：

```text
route                         window       limit       Redis down
POST /api/v1/conversations    60s          30          fail-closed
POST /api/v1/documents        60s          10          fail-closed
POST /api/v1/retry            60s          20          fail-closed
provider call budget          60s          configured  fail-closed
low-risk read                 60s          configured  fail-open + metric
```

当前没有可靠认证主体时，使用反向代理提供并校验后的来源地址；不能直接信任任意客户端提交的 `X-Forwarded-For`。认证主体稳定后改为 `tenant_id/principal_id`，IP 仅作为匿名补充维度。

### 4.2 原子实现

不要在客户端独立执行 `INCR` 再执行 `EXPIRE`。客户端中断可能留下没有 TTL 的计数 key。使用一个 Redis transaction 或 Lua 脚本把递增、首次过期设置和结果返回放到同一服务端操作中：

```text
count = INCR key
if count == 1:
    EXPIRE key window_seconds + jitter
return count
```

返回结构至少包含：`allowed`、`count`、`limit`、`retry_after_seconds`。超过限制时不再重复写入业务数据，也不触发昂贵供应商调用。

### 4.3 限流故障合同

- Redis 正常：严格按计数结果返回 200/429。
- Redis 连接超时：高成本/写操作返回 503 或 429，不能继续调用 LLM/OCR；低风险读接口可旁路并记录 `rate_limit_degraded=true`。
- Redis 重启：窗口计数丢失是允许的，但必须有应用层并发/容量保护和告警；不能声称限流仍然严格。
- Redis 淘汰：速率限制实例不使用缓存淘汰策略，建议独立实例并设置 `noeviction`，写失败按 fail-closed 处理。

### 4.4 观测指标

```text
redis_rate_limit_requests_total{route,result}
redis_rate_limit_command_duration_seconds{command}
redis_rate_limit_degraded_total{route}
http_requests_total{route,status=429}
```

不记录原始 IP、合同内容或完整查询。

## 5. 能力二：短 TTL 检索缓存

### 5.1 缓存对象

首期只缓存 Retrieval Debug 或候选投影，不缓存完整最终法律回答。缓存值可以包含候选 chunk ID、排名、通道状态和版本信息；生成回答时仍须重新完成授权、上下文组装、证据门控和引用校验。

不缓存：

- 跨租户共享的查询结果；
- 未带 `corpus_revision` 的结果；
- 大段合同正文；
- 未脱敏的用户身份或供应商密钥；
- 最终带引用的法律结论。

### 5.2 Cache-aside 流程

```text
1. API 校验请求和授权范围。
2. 从 PostgreSQL 读取当前 corpus_revision/检索配置版本。
3. 生成 cache key。
4. GET cache。
5. 命中且 schema/revision/TTL 有效：返回候选投影，但仍做响应级授权校验。
6. 未命中：尝试 redis-py Lock(cache-rebuild-key)。
7. 获锁者执行 PostgreSQL Dense + BM25 + RRF + rerank。
8. 获锁者以短 TTL 写入 Redis。
9. 未获锁者短暂等待后再次 GET；仍未命中则直接访问 PostgreSQL，不能无限等待。
```

缓存不是授权边界。任何 cache hit 都必须绑定调用方的 tenant/knowledge base 范围；key 错误或反序列化错误按 cache miss 处理并删除坏值。

### 5.3 一致性策略

缓存一致性采用“版本化 key + 主动失效 + 短 TTL”三层策略：

- **版本化 key**：文档版本、索引状态或知识库内容变化后生成新的 `corpus_revision`，旧 key 自然不再命中。
- **主动失效**：文档上传、删除、重试、reindex、检索配置变更成功提交后，删除受影响 key 或 revision 前缀下的已知 key。不能用无界 `KEYS`；若必须扫描，使用 `SCAN` 且限量分批。
- **短 TTL**：主动删除失败时，旧结果最多存活一个很短窗口；TTL 加随机抖动避免同时过期。

PostgreSQL 提交是事实发生点。Redis 写失败不能回滚数据库，也不能阻塞事实提交；只记录 `cache_write_failed` 并旁路。

### 5.4 内存与值大小

- 业务缓存实例显式设置 `maxmemory` 和 `allkeys-lfu` 或 `allkeys-lru`。
- 单值超过 `REDIS_MAX_CACHE_VALUE_BYTES` 不写 Redis。
- 命中率、淘汰、序列化失败和回源耗时必须可观测。
- 缓存实例与限流/锁实例分开；若初期共用，必须有容量预算和隔离告警。

指标：

```text
redis_cache_requests_total{cache,result=hit|miss|stale|error}
redis_cache_rebuild_total{result}
redis_cache_rebuild_duration_seconds
redis_cache_value_bytes
redis_cache_invalidation_total{reason}
```

## 6. 能力三：使用 redis-py Lock 保证缓存回源一致性

### 6.1 为什么使用内置 Lock

`redis-py` 的 `Lock` 已封装 token、获取、续期和安全释放所需的 Lua 脚本语义，减少手写锁释放逻辑的风险。本项目只把它用于“同一缓存 key 的回源协调”，不把它当成跨系统事务锁。

异步路径使用 `redis.asyncio.Redis.lock()` 返回的异步 Lock，不能把同步 Lock 放进异步请求处理。

### 6.2 获取与释放

伪代码：

```python
lock = redis.lock(
    name=cache_lock_key,
    timeout=settings.redis_cache_lock_timeout_seconds,
    blocking_timeout=settings.redis_cache_lock_blocking_timeout_seconds,
    thread_local=False,
)
acquired = await lock.acquire()
if not acquired:
    return await read_or_bypass_cache()
try:
    value = await rebuild_from_postgres()
    await write_cache(value)
finally:
    await lock.release()
```

关键条件：

- `timeout` 必须大于正常回源 p99，并小于接口总超时；不能设置为无限。
- `blocking_timeout` 必须很短，避免请求堆积；拿不到锁不应无限等待。
- 释放只允许在当前持有 token 仍有效时执行；不要额外调用裸 `DELETE`。
- 任务取消时进入 `finally`，但必须保护 `CancelledError` 传播；释放异常记录后仍重新抛出取消异常。
- 锁 TTL 到期后，旧回源任务可能与新持有者并行。缓存写入必须携带 revision，只有当前 revision 的结果才允许写入；必要时重新读取 PostgreSQL revision 做条件检查。

### 6.3 防止旧回源覆盖新缓存

锁本身不足以防止超时旧任务写入：

```text
old request obtains lock at t0
lock expires at t5
new request obtains lock at t6 and writes revision R2
old request finishes at t7
```

因此缓存值必须包含 revision，写入前检查仍然是当前 revision；revision 不匹配时丢弃旧结果。缓存只是派生数据，不得让旧缓存影响 PostgreSQL 事实。

## 7. 能力四：一般短租约锁

### 7.1 使用范围

只允许用于：

- 供应商能力探测的重复刷新抑制；
- 非权威缓存预热；
- 同一进程集群中的短期资源刷新协调。

禁止用于：

- PostgreSQL job claim；
- RabbitMQ 消息确认；
- 文档版本发布；
- 向量写入门控；
- 引用校验；
- 权限、计费或任何需要强一致互斥的业务事实。

### 7.2 redis-py Lock 参数

```text
lock name: clauserag:{env}:lock:v1:coordination:{resource_hash}
timeout: 5-30s，按操作 p99 设定
blocking_timeout: 0-0.2s
thread_local: False for async/task handoff scenarios
```

默认不自动续期。只有真实操作可能超过锁 TTL 且能证明续期安全时，才使用 `extend()`；续期失败必须停止写入派生结果。不要把锁 TTL 设为几小时来掩盖慢操作。

### 7.3 故障合同

- 获取失败：允许跳过优化或执行幂等旁路；不能把失败转成业务成功。
- Redis 不可用：非权威刷新允许旁路并产生重复工作；若重复工作会造成供应商费用风险，则该入口 fail-closed。
- 锁丢失：旧执行者必须被视为无锁；其结果只能写可丢失的派生缓存，并进行版本检查。
- Redis 重启/主从切换：不保证锁连续存在；不用于保护事实提交。

## 8. Redis 客户端参数与关闭

业务 Redis 客户端建议：

```python
redis.asyncio.Redis.from_url(
    settings.redis_url.get_secret_value(),
    socket_connect_timeout=settings.redis_connect_timeout_seconds,
    socket_timeout=settings.redis_socket_timeout_seconds,
    max_connections=settings.redis_max_connections,
    retry=Retry(backoff=NoBackoff(), retries=0),  # 见文首实施差异：不重放命令
    health_check_interval=30,
    decode_responses=False,
)
```

- 使用 bytes，缓存序列化格式显式定义，例如 JSON + schema version；不依赖 Python pickle。
- 连接池上限按 API/Agent/Worker 进程分别计算，避免进程数乘池大小超过 Redis `maxclients`。
- startup 做一次 bounded `PING`；业务 Redis 不可用时，若功能开关关闭则不影响启动。
- shutdown 调用 `await redis.aclose()`，确保连接释放。
- 任何 Redis 异常必须映射成业务层可理解的 `cache miss`、`rate limit degraded` 或 `lock unavailable`，不能吞掉取消异常。

## 9. 部署拓扑

建议拆分：

```text
redis-business-cache  -> Retrieval Debug cache
redis-business-guard  -> rate limit + short locks
redis-langfuse        -> Langfuse internal Redis
```

最低配置为两个业务 keyspace，但生产建议两个业务实例：

- cache 实例：有 `maxmemory`，`allkeys-lfu`/`allkeys-lru`，数据可重建。
- guard 实例：`noeviction`，限流计数写失败触发明确 fail-closed，锁仅作短期协调。

两个实例都应：

- 只监听私有网络；不暴露公网；
- 使用 ACL 最小权限账号，按命令和 key pattern 限制；
- 生产启用 TLS，敏感环境启用 mTLS；
- 不使用默认用户/共享 Langfuse 密钥；
- 通过 secrets 注入密码/证书，不提交仓库。

缓存/限流/锁数据都是可丢失派生数据，不把 RDB/AOF 当 PostgreSQL 备份。是否启用持久化按恢复目标决定；若启用，也要做真实恢复演练。

## 10. Readiness 与健康检查

必须区分三种状态：

1. `live`：进程能响应。
2. `ready`：PostgreSQL、RabbitMQ、RustFS 等业务必需依赖可用。
3. Redis 能力状态：业务 Redis enabled 且实际功能要求时，单独报告 healthy/degraded。

Redis 不应在 `REDIS_ENABLED=false` 时加入业务 readiness。启用 Redis 后也不建议直接让所有 API 因 Redis 失败而 503；应按功能合同处理：

- 限流 fail-closed 的接口：返回 503/429，并报告 guard degraded；
- 缓存：旁路 PostgreSQL；
- 短锁：旁路或放弃优化；
- Langfuse Redis：仅观测降级，不影响业务 readiness。

健康响应中不暴露 URL、密码、ACL 用户名或 key 内容。

## 11. 代码实施顺序

### Step 1：客户端与配置

- 增加 `redis` 依赖并锁定。
- 增加 Redis settings 和功能开关。
- 创建共享异步客户端装配和关闭逻辑。
- 业务 Redis 不接入 readiness，先完成配置/连接 smoke check。

### Step 2：速率限制

- 定义 application port 和 route policy。
- infrastructure 实现原子固定窗口计数。
- 在 API/Agent 入口接入，先覆盖问答、上传和重试。
- 接入 429、Retry-After、指标和故障降级。

### Step 3：缓存与 cache rebuild lock

- 定义 Retrieval Cache port 和序列化 schema。
- 引入 `redis-py Lock` 的 cache rebuild lock。
- 先只接 Retrieval Debug；验证 revision 和跨租户隔离后再扩大。
- 接入 mutation 后失效和 TTL jitter。

### Step 4：一般短租约锁

- 只在有实际重复工作指标后接入一个明确用例。
- 为该用例单独定义资源 key、timeout、blocking timeout 和旁路行为。
- 验证锁到期后旧执行无法覆盖新 revision。

### Step 5：生产配置与隔离

- 拆分 cache/guard/Langfuse Redis 实例或至少 ACL/keyspace。
- 配置 TLS、ACL、maxmemory、eviction、连接上限和告警。
- 完成故障演练和回滚开关验证。

## 12. 验收矩阵

### 12.1 静态门禁

```bash
uv sync --locked --group eval
uv run ruff check backend/src
uv run ruff format --check backend/src
uv run pyright backend/src
uv run python -c "import api.main, agent_runtime.main, worker.main, cli.main"
uv run python scripts/check-architecture.py
pnpm --dir frontend run check
pnpm --dir frontend run test
```

### 12.2 真实容器验收

```bash
docker compose --profile app up -d --build --wait
curl -fsS http://localhost:5173/health/ready
curl -fsS http://localhost:5173/api/v1/config
```

必须额外验证：

| 场景 | 预期 |
|---|---|
| 并发超过限额 | 稳定返回 429/Retry-After，不调用供应商 |
| 限流窗口过期 | 新窗口恢复；旧 key 有 TTL |
| Redis 限流不可用 | 高成本接口按 fail-closed；低风险接口按合同降级 |
| 相同检索并发 miss | 只有有限回源；其他请求短等后命中或旁路 |
| cache value 损坏 | 当作 miss，删除坏值，不影响请求正确性 |
| corpus revision 变化 | 旧缓存不命中；新结果来自 PostgreSQL |
| cache lock TTL 到期 | 旧请求不能覆盖新 revision |
| 一般锁获取失败 | 旁路/放弃优化，不写业务事实 |
| Redis 重启 | 业务事实、RabbitMQ 任务和引用不受影响 |
| cache 达到 maxmemory | 仅缓存被淘汰；guard/业务事实不受影响 |
| ACL/TLS 错误 | 连接快速失败，错误不泄露密钥 |

## 13. 回滚方案

每项能力都必须可独立关闭：

```text
REDIS_RATE_LIMIT_ENABLED=false
REDIS_CACHE_ENABLED=false
REDIS_ENABLED=false
```

回滚顺序：

1. 关闭对应功能开关；
2. 保留 PostgreSQL、RabbitMQ、RustFS 主链路；
3. 删除或等待 Redis key 过期；
4. 观察 API 延迟、供应商调用量和错误率；
5. 修复后先在单实例/低流量恢复。

不得通过清空 PostgreSQL、删除 RabbitMQ 队列或修改业务事实来回滚 Redis 功能。

## 14. 官方依据

- [`INCR`](https://redis.io/docs/latest/commands/incr/)：固定窗口限流以及 `INCR`/`EXPIRE` 原子化竞态。
- [`Distributed Locks with Redis`](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/)：`SET NX PX`、token 安全释放、TTL 到期限制和 fencing token。
- [`Eviction policy`](https://redis.io/docs/latest/operate/rs/7.4/databases/memory-performance/eviction-policy/)：`maxmemory` 与淘汰策略。
- [`ACL`](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)：命令和 key pattern 最小权限。
- [`Enable TLS`](https://redis.io/docs/latest/operate/rs/7.8/security/encryption/tls/enable-tls/)：TLS/mTLS。
- [`Configure database persistence`](https://redis.io/docs/latest/operate/rs/7.4/databases/configure/database-persistence/)：RDB/AOF 取舍。
- [`INFO`](https://redis.io/docs/latest/commands/info/)：内存、统计、持久化和延迟指标。
- [`redis-py Lock API`](https://redis.readthedocs.io/en/stable/lock.html)：`Lock` 的 Python 客户端接口。

## 最终决策

四项能力可以落地，但顺序不可颠倒：先完成客户端边界和故障合同，再上线限流，再上线 Retrieval Debug 缓存与内置 Lock，最后根据指标决定是否启用一般短租约锁。任何阶段都不改变 PostgreSQL 的事实源地位、RabbitMQ 的队列地位或 ClauseRAG 的引用校验闭环。
