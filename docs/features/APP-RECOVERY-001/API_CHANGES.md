---
id: APP-RECOVERY-001
status: frozen
---

# API 变更

## `POST /api/v1/app/auth/reset-password`

请求体由：

```json
{"email":"user@example.com"}
```

扩展为：

```json
{"email":"user@example.com","locale":"es"}
```

- `locale` 可选，允许 `es`、`en`、`zh`。
- 缺省时使用 `es`。
- 响应结构、反邮箱枚举行为和限流规则不变。

其他 API、数据库和权限无变化。

