---
id: OPS-PROD-001
status: ready-for-dev
---

# 验收标准

1. 仓库不存在被跟踪的真实 `.env.production`，提供完整的 `.env.production.example`。
2. 生产预检能够拒绝空值、占位密钥、非 HTTPS Admin/API 地址、通配 CORS 和错误传输组合。
3. 使用完整测试参数运行 `docker compose ... config --quiet` 成功；缺失必填参数时失败并指出变量名。
4. PostgreSQL 健康检查使用配置的 `DB_USER` 和 `DB_NAME`。
5. Redis 健康检查使用配置的密码，CSMS `REDIS_URL` 与该密码一致。
6. `db-role-init` 在 CSMS 前幂等创建并验证 `app_super`。
7. 空卷首次启动依次完成数据库健康、角色引导、Alembic `head`、管理员初始化、CSMS `/readyz` 和 Admin 健康检查。
8. 首次启动缺少 bootstrap 密码时，预检必须失败；已有管理员后 bootstrap 密码可为空。
9. CSMS 健康检查使用镜像内存在的 `curl`。
10. Admin 必须等待 CSMS healthy 后启动。
11. CSMS/Admin/PostgreSQL/Redis 无宿主机端口，公网端口由独立反向代理发布。
12. 二维码目录挂载持久化卷，重建 CSMS 后文件仍存在。
13. 生产环境禁用 Swagger/ReDoc/OpenAPI 时路由返回 404。
14. 不新增数据库迁移，不操作生产数据库。
