---
id: PERF-DB-001
status: ready-for-dev
---

# API 变更

本次不改变 HTTP API 或 OCPP 响应字段。

- Heartbeat 仍返回 `currentTime`。
- MeterValues 仍返回现有 OCPP 结果。
- 数据库内部不再为正常 Heartbeat 建立原始历史行。
- 现有心跳历史统计接口暂不重构，聚合数据契约将在下一阶段单独冻结。
