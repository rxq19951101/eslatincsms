---
id: PERF-DB-001
status: accepted
---

# QA 结果

## P0 定向回归

- 高频写入、消息处理、充电会话和数据库查询：34 项通过。
- OCPP 设备安全、SIM-E2E P0 和数据库模型：39 项通过。

## 写入行为

- 正常 Heartbeat：0 条 `OCPPMessageEvent`、0 条 `DeviceEvent`。
- `last_seen`：空值或超过 60 秒时更新；60 秒内不重复更新。
- 两个采样点的单条 MeterValues 消息：2 条 MeterValue、1 条 OCPPMessageEvent、1 次事务提交。

## 已知非本任务问题

- `tests/test_uuid_boundary_review.py::test_string_charge_point_filters_resolve_identity_and_enforce_tenant` 单独运行仍因交易返回中的 `charger.ocpp_identity` 缺失而失败；该失败与本次写入止血改动无重叠，未在本任务中扩展修复。
