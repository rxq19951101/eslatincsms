---
id: APP-AUTH-004
status: ready-for-dev
---

# API 契约

本任务不修改后端 API、请求字段或响应格式。

继续沿用现有接口：

- `POST /api/v1/app/auth/login-email`
- `POST /api/v1/app/auth/refresh`
- 受保护接口的标准 `401` 响应

改动仅限 App 客户端对本地 Token、Redux 认证状态、并发刷新队列和导航重置的协调。
