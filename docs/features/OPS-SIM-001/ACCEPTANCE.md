---
id: OPS-SIM-001
status: ready-for-dev
---

# 验收标准

- [x] `sim-e2e-seed` 只允许在 simulator/e2e profile 中运行。
- [x] seed 等待 CSMS 健康后执行，并使用现有稳定测试 ID。
- [x] `charger-sim` 等待 seed 成功后启动。
- [x] 清空业务数据后 seed 可重新创建预注册站点、充电桩和 EVSE。
- [x] 模拟器 WebSocket 不再返回 403。
- [x] BootNotification、Heartbeat 和状态上报成功。
- [x] 不关闭 `OCPP_WS_REQUIRE_PRE_REGISTERED`。
- [x] 不新增数据库迁移。
