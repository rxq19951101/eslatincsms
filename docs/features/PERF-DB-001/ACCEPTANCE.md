---
id: PERF-DB-001
status: ready-for-dev
---

# 验收标准

- [x] Heartbeat 响应继续返回 `currentTime`。
- [x] Heartbeat 不创建 `OCPPMessageEvent`。
- [x] Heartbeat 不创建 `DeviceEvent`。
- [x] `last_seen` 为空或超过持久化间隔时被更新。
- [x] 持久化间隔内的重复 Heartbeat 不改写 `last_seen`。
- [x] 一条多采样点 MeterValues 消息只在消息边界提交事务。
- [x] MeterValues 重放幂等行为保持不变。
- [x] StartTransaction 和 StopTransaction 持久化幂等行为保持不变。
- [x] 不新增数据库迁移。
