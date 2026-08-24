---
id: PERF-DB-002
status: accepted
---

# QA 结果

## 定向回归

- 后端 Redis 遥测、OCPP 消息、充电会话、设备安全和数据库查询：42 项通过。
- App 计量 API 契约和状态层：12 项通过。

## 写入行为

- Redis 可用：每条消息更新会话实时快照；60 秒持久化门闩内只写一条最新采样。
- Redis 不可用：同一消息的全部采样点在一个 PostgreSQL 事务内写入。
- MeterValues：不再创建永久 `OCPPMessageEvent`。
- 数据库写入失败：释放 Redis 消息去重键和持久化门闩，允许设备安全重试。

## App 行为

- 数据库记录标记 `source=database`，Redis 快照标记 `source=realtime`。
- 新实时点替换旧实时点；只有数据库记录更新 UUID 增量游标。

## 约束与后续项

- 本任务没有数据库迁移，也没有清理现有历史数据。
- 数据库分区、历史保留和重复索引治理留待独立后续任务。
- 既有 `test_uuid_boundary_review.py::test_string_charge_point_filters_resolve_identity_and_enforce_tenant` 失败与本任务无关，未扩展修复。
