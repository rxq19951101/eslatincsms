---
id: BUG-OCPP-AUTH-001
status: ready-for-dev
contract: frozen
---

# 契约说明

本修复不修改 HTTP API、数据库或 OCPP 1.6J 消息契约。

冻结规则：

- OCPP identity 继续允许 `^[A-Za-z0-9._:-]{1,64}$`。
- WebSocket identity 仍来自规范 URL `/ocpp?id=<identity>` 或兼容路径形式。
- 设备独立密钥仍可通过 Basic Auth、`X-API-Key` 或现有 Bearer 兼容入口提供。
- Basic Auth 校验必须以路由中已经解析出的完整 identity 为准，不能按 identity 内部的
  第一个冒号截断目标设备标识。
