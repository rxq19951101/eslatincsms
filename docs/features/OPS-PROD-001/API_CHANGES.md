---
id: OPS-PROD-001
status: ready-for-dev
---

# API 变化

业务 API 契约不变。

生产默认关闭以下开发文档路由：

- `/docs`
- `/redoc`
- `/openapi.json`

健康探针保持：

- `GET /livez`：进程存活。
- `GET /readyz`：数据库与 Redis 就绪。

无数据库 schema 变化。
