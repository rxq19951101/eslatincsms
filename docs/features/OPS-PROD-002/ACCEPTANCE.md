---
id: OPS-PROD-002
status: ready-for-dev
---

# 验收标准

1. 生产 Compose 包含官方 Caddy 反向代理，并持久化 `/data` 与 `/config`。
2. 只有代理发布公网 80/443；Admin 和 CSMS 仅通过 Compose 内网提供给代理。
3. Admin 域名转发到 `admin:3000`，API 域名转发到 `csms:9000`。
4. `/ocpp` 和 `/ocpp/<identity>` 无需额外路径改写即可升级为 WebSocket。
5. Caddy 配置能够通过 `caddy validate`。
6. 环境预检要求真实 `ADMIN_DOMAIN`、`API_DOMAIN` 和 `ACME_EMAIL`。
7. `CORS_ALLOW_ORIGINS` 等于 Admin HTTPS Origin；公开 API 与前端构建 API 地址等于 API HTTPS Origin。
8. Admin 与 API 域名不同，域名变量不包含协议、端口、路径或通配符。
9. TLS 证书状态卷、日志轮转、健康检查和依赖顺序存在。
10. 不修改或执行任何数据库迁移。
