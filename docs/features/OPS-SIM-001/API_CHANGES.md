---
id: OPS-SIM-001
status: ready-for-dev
---

# API 变更

本任务不修改 HTTP API 或 OCPP 消息契约。

Compose 新增一次性服务 `sim-e2e-seed`，作为 `charger-sim` 和 `charger-scenario` 的启动依赖。
