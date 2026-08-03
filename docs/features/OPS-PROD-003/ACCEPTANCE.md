---
id: OPS-PROD-003
status: ready-for-dev
---

# 验收标准

1. `.env.production` 存在、被 Git 忽略且权限为 `600`。
2. 模板和 Compose 支持两个首启管理员邮箱变量。
3. 初始化脚本以环境变量邮箱作为 username 和 email，不再创建 `admin@example.com` 或 `tenant_admin@example.com`。
4. 预检拒绝缺失、相同或短于 16 位的首启密码，并拒绝相同管理员邮箱。
5. 数据库、Redis、JWT、数据加密和加密盐使用独立随机值。
6. Spacemail 配置为 `mail.spacemail.com:465`、`SMTP_SSL=true`、`SMTP_TLS=false`。
7. SMTP 通知发送路径支持隐式 SSL。
8. 不修改或执行数据库迁移。
