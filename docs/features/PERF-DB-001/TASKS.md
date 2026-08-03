---
id: PERF-DB-001
status: ready-for-dev
---

# 任务

- [x] 冻结 P0 写入止血规则。
- [x] 冻结 API 与 OCPP 兼容边界。
- [x] Heartbeat 绕过持久化消息记录和设备事件记录。
- [x] 对 `EVSEStatus.last_seen` 增加持久化限频。
- [x] MeterValues 改为消息级单事务提交。
- [x] 增加写入数量、限频和幂等回归测试。
- [x] 运行后端定向测试。
