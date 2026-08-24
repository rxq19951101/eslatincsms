---
id: PERF-DB-002
status: ready-for-dev
---

# MeterValues 实时与持久化分层

## 背景

充电桩可每 5 秒上报 MeterValues。当前实现同时保存完整 OCPP 消息和每个采样点，数据库写入频率与活跃充电会话数线性增长。

## 目标

- Redis 保存每个充电会话的最新实时计量快照，供 App 5 秒轮询读取。
- PostgreSQL 在 Redis 可用时每个会话最多每 60 秒持久化一个最新采样点。
- MeterValues 不再写入 `ocpp_message_events`；Redis 在24小时内对消息 ID 去重。
- StartTransaction、StopTransaction、订单、结算和最终电量逻辑保持不变。

## 产品规则

- 实时快照 TTL 为24小时，键按租户和充电会话隔离。
- 数据库分钟采样保留最新一个采样点，不保存同一周期内的全部原始点。
- Redis 不可用时降级为数据库保存该消息全部采样点，优先保证数据不丢失。
- Redis 实时点不作为数据库增量游标；App 只使用数据库来源点更新 `since_id`。
- 现有历史数据不清理。

## 非目标

- 不新增数据库表或迁移。
- 不处理数据库分区、历史保留和重复索引。
- 不改变最终账单使用 `meter_start` / `meter_stop` 的规则。
