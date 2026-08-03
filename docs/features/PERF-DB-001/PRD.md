---
id: PERF-DB-001
status: ready-for-dev
---

# P0 数据库高频写入止血

## 背景

正常 Heartbeat 同时写入 `ocpp_message_events`、`device_events` 并更新所有 EVSE 状态；MeterValues 又按每个采样点独立提交事务。该实现会随充电桩规模线性放大数据库行数、索引写入、WAL 和事务提交压力。

## P0 目标

- 正常 Heartbeat 不再写入 `ocpp_message_events` 和 `device_events`。
- Heartbeat 返回结构保持 OCPP 兼容，只保留在线快照更新。
- 同一充电桩的 `EVSEStatus.last_seen` 默认最多每 60 秒持久化一次。
- 一条 MeterValues OCPP 消息中的全部采样点与消息幂等记录使用同一事务提交。

## 产品规则

- Heartbeat 是幂等在线信号，不需要永久保存每次请求和响应。
- 心跳异常、超时、恢复等业务事件在后续聚合重构中记录；本阶段不新增历史表。
- StartTransaction、StopTransaction、MeterValues 等业务关键消息继续保留持久化幂等记录。
- MeterValues 原始数据结构和 App 查询接口本阶段不变化。

## 非目标

- 不新增或修改数据库迁移。
- 不清理当前数据库中的历史数据。
- 不实施 Redis 实时计量、时间聚合、分区和保留策略；这些属于下一阶段重构。
