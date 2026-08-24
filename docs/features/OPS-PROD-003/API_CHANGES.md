---
id: OPS-PROD-003
status: ready-for-dev
---

# API 变化

业务 API 不变。

新增首启环境变量：

- `CSMS_BOOTSTRAP_SUPER_ADMIN_EMAIL`
- `CSMS_BOOTSTRAP_TENANT_ADMIN_EMAIL`

两个邮箱同时作为后台登录用户名。无数据库 schema 或迁移变化。
