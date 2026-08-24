---
id: SIM-E2E-001
status: ready-for-dev
---

# 架构审查

现有 `charger-sim` 只能完成单桩 happy path，缺少场景编排、故障注入、后端领域断言和三端 UI 驱动。主要 P0 问题：Authorize 拒绝仍可启动、未知 transaction 停止仍 Accepted、支付错误复用 transaction ID 作为 session UUID、消息去重未基于 UniqueId、支付凭证明文入库、App ID 类型漂移、安全停止受支付状态影响、故障/离线未自动告警。

目标结构：

```text
charger-sim/
├── scenario/      # schema、loader、variables
├── runner/        # orchestrator、steps、result
├── actors/        # charger、admin、app_user、fake_payment
├── protocol/ocpp16/
├── faults/
├── assertions/
├── reports/
└── scenarios/p0/
```

场景 runner 只通过正式 WebSocket/API 观察系统，不直接修改业务数据库。测试夹具通过受控 seed 脚本建立，报告不保留 secret。
