---
id: OPS-PROD-001
title: 生产 Compose 与首次启动闭环
status: ready-for-dev
---

# 目标

提供一套可验证、默认不直接暴露应用端口、可在空 PostgreSQL 上完成角色引导、Alembic 迁移和管理员初始化的生产 Compose 基线。

# 产品与运维规则

- 生产启动必须显式使用 `.env.production`，仓库只提交不含真实密钥的 `.env.production.example`。
- PostgreSQL、Redis、CSMS 和 Admin 不发布宿主机端口；公网流量统一由后续反向代理接入。
- 数据库账号、库名和健康检查必须来自同一组环境变量，不得写死开发值。
- `app_super` 必须在 CSMS 启动前幂等创建、授权并校验。
- 空数据库首次启动必须显式提供两个 bootstrap 密码；已有管理员时允许删除这些变量后正常重启。
- Alembic 仍是唯一 schema 入口，不引入新的数据库迁移。
- CSMS、Admin、PostgreSQL 和 Redis 都必须有有效健康检查与日志轮转。
- 二维码文件必须使用持久化数据卷。
- 生产只启用已验证的 OCPP WebSocket 传输；MQTT、HTTP 传输默认关闭。
- Admin 的 API 地址必须在镜像构建时注入 HTTPS 地址。

# 不在本需求范围

- TLS 证书和 Nginx/Caddy 反向代理。
- PostgreSQL RLS 策略。
- 备份恢复、法律页面、镜像发布流水线和依赖安全扫描。
