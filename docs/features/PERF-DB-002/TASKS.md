---
id: PERF-DB-002
status: ready-for-dev
---

# 任务

- [x] 冻结实时快照、分钟采样和降级规则。
- [x] 冻结 App 增量游标兼容规则。
- [x] 实现 Redis MeterValues 实时快照与消息去重。
- [x] MeterValues 绕过永久 OCPP 消息记录并执行分钟采样。
- [x] App 计量接口合并数据库与 Redis 数据。
- [x] App 状态层区分数据库点和实时点。
- [x] 增加后端和 App 定向回归测试。
- [x] 运行定向测试。
