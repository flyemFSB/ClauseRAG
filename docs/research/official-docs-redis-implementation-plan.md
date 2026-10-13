# Redis 官方资料核验补充

本页原方案结论不变：Redis 仅可选用于可降级的缓存、速率限制和短租约锁；不作为业务队列或事实源。Langfuse Redis 与业务 Redis 分离。

## 核验结果

- **INCR/EXPIRE 限流原子性**：Redis `INCR` 文档的官方 rate-limiter pattern 明确指出，单独执行 `INCR` 后再执行 `EXPIRE` 存在客户端中断导致 key 泄漏的竞态；建议使用 `MULTI/EXEC`，或用 Lua/EVAL 将递增和过期设置放在同一服务端原子执行中。原方案“原子计数、过期和 Lua/Functions”表述准确。来源：[INCR](https://redis.io/docs/latest/commands/incr/)。
- **内存上限和淘汰**：官方 eviction 文档确认达到内存上限时按策略删除 key；`noeviction` 则拒绝新写入，`allkeys-lru`/`allkeys-lfu` 可用于缓存。该页面是 Redis Enterprise 7.4 文档，标注将于 2026-11-30 EOL；原方案链接事实正确，但版本路径不是长期稳定引用。来源：[Eviction policy](https://redis.io/docs/latest/operate/rs/7.4/databases/memory-performance/eviction-policy/)。
- **锁 token 安全释放与限制**：官方分布式锁文档要求 `SET resource token NX PX ttl`，释放时必须仅在 value 仍等于 token 时删除，不能裸 `DEL`；文档还明确指出锁有效期结束后互斥只在有效期内成立，并建议 fencing tokens，且 Redis TTL 使用非单调时钟。原方案的 token-safe release、过期后旧持有者风险及 PostgreSQL fencing 要求准确。当前官方 URL 已规范为 `/docs/latest/develop/clients/patterns/distributed-locks/`；原文件中的 `/docs/latest/develop/use/patterns/distributed-locks/` 会重定向/不再是规范路径，已修正。来源：[Distributed Locks with Redis](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/)。
- **ACL/TLS**：ACL 官方文档支持按命令和 key pattern 限制用户；TLS 官方文档说明可保护客户端连接，并可启用 mutual TLS。原方案的最小权限 ACL、业务与 Langfuse 分账号/实例、生产启用 TLS 建议准确。来源：[ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)，[Enable TLS](https://redis.io/docs/latest/operate/rs/7.8/security/encryption/tls/enable-tls/)。
- **持久化和指标**：官方资料确认 RDB snapshot 与 AOF 是不同持久化策略，AOF durability 通常高于快照但资源/恢复代价更高；`INFO` 提供 `memory`、`persistence`、`stats`、`latencystats` 等区段，并包含 `used_memory`、`maxmemory`、`evicted_keys`、`expired_keys`、`keyspace_hits/misses`、连接拒绝等字段。原方案“数据可丢失并重建，不把 Redis 持久化当 PostgreSQL 备份”仍是适合本项目的数据分类结论。来源：[Configure database persistence](https://redis.io/docs/latest/operate/rs/7.4/databases/configure/database-persistence/)，[INFO](https://redis.io/docs/latest/commands/info/)。

## 必要修正

仅修正一处官方 URL：分布式锁参考改为 `https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/`。其余原方案无需改变。Eviction 和 persistence 链接均为 Redis Enterprise 版本页，实施前应按实际部署产品/版本重新核对对应配置页面。
