---
id: OPS-PROD-003
title: 生产密钥与首启账号配置
status: ready-for-dev
---

# 目标

生成仅保存在本机/服务器的真实生产配置，并让空库首启管理员账号通过环境变量配置，避免初始化脚本写死测试邮箱。

# 规则

- `.env.production` 必须被 Git 忽略，文件权限为仅当前用户可读写。
- 数据库、Redis、JWT、数据加密、加密盐及两个首启密码分别使用独立随机值。
- 两个首启管理员密码至少 16 位且不得相同。
- 超级管理员登录账号为 `support@eslatin.com.co`。
- 租户管理员登录账号为 `amos.ran@eslatin.com.co`。
- 登录用户名与邮箱均使用对应完整邮箱地址。
- Spaceship Spacemail 使用 `mail.spacemail.com:465`、隐式 SSL，用户名为完整邮箱地址。
- SMTP 密码必须与 Spaceship 中 `support@eslatin.com.co` 邮箱密码一致。
- 真实密钥不得写入文档、测试输出或 Git。

# 不在范围

- 数据库迁移、数据库结构调整和生产数据库操作。
- 修改 Spaceship 账户或代替用户登录第三方控制台。
