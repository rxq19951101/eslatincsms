---
id: OPS-PROD-002
title: 生产 TLS 反向代理与公网入口
status: ready-for-dev
---

# 目标

在生产 Compose 中增加唯一公网入口，自动签发和续期 TLS 证书，将 Admin、REST API 与 OCPP WebSocket 安全转发到内网服务。

# 产品与运维规则

- `ADMIN_DOMAIN` 提供 Admin HTTPS 入口。
- `API_DOMAIN` 同时提供 REST API 和 OCPP WebSocket 入口。
- 充电桩使用 `wss://<API_DOMAIN>/ocpp/<identity>`，兼容 `/ocpp?id=<identity>`。
- 只有代理发布宿主机 80/TCP、443/TCP 和 443/UDP；Admin、CSMS、PostgreSQL、Redis 不直接暴露公网。
- 自动 HTTPS 的证书和代理运行状态必须持久化。
- 代理必须等待 Admin 与 CSMS 健康后启动，并配置日志轮转与容器健康检查。
- HTTP 自动重定向到 HTTPS，响应包含基础安全头。
- 上线预检必须拒绝占位域名、URL 与域名不一致、Admin/API 使用同一域名、无效 ACME 邮箱和非标准公网绑定配置。

# 不在本需求范围

- 数据库迁移、数据库结构和初始化数据。
- DNS 服务商 API 自动化、Cloudflare Tunnel 或负载均衡集群。
- 数据库备份恢复、多租户 RLS、业务监控和发布流水线。
