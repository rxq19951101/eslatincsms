---
id: OPS-PROD-002
status: ready-for-dev
---

# API 变化

业务 API 路径和响应契约不变。

生产公网入口固定为：

- Admin：`https://admin.eslatin.com.co`
- REST API：`https://api.eslatin.com.co`
- OCPP WebSocket：`wss://api.eslatin.com.co/ocpp/<identity>`
- OCPP 兼容入口：`wss://api.eslatin.com.co/ocpp?id=<identity>`

代理向后端保留 `Host`，并发送标准 `X-Forwarded-*` 请求信息。Caddy 原生处理 WebSocket Upgrade。

无数据库 schema 或迁移变化。
