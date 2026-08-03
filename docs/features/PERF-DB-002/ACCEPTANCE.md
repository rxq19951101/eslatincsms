---
id: PERF-DB-002
status: ready-for-dev
---

# 验收标准

- [x] Redis 可用时，每条 MeterValues 更新实时快照。
- [x] Redis 可用时，同一会话60秒内最多新增一条 `meter_values`。
- [x] Redis 可用时，重复消息 ID 不重复处理。
- [x] MeterValues 不新增 `OCPPMessageEvent`。
- [x] Redis 不可用时，全部采样点使用单事务降级写入 PostgreSQL。
- [x] App 计量接口同时返回数据库历史点和更新的 Redis 实时点。
- [x] App 仅使用 `source=database` 的记录更新增量游标。
- [x] StartTransaction、StopTransaction 和结算逻辑回归通过。
- [x] 不新增数据库迁移。
