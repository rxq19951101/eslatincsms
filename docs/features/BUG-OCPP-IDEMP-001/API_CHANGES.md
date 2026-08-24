---
id: BUG-OCPP-IDEMP-001
status: ready-for-dev
---

# API 契约

接口：`POST /api/v1/ocpp/remote-start-transaction`

请求和成功响应字段不变。

行为修正：

- 相同幂等键与完全相同的远程启动命令重放时，返回首次已记录结果，并在 `details.idempotent_replay` 返回 `true`。
- 同一租户内幂等键已绑定其他充电桩、其他动作或不同参数时，返回 HTTP 409：

```json
{
  "error": {
    "code": "IDEMPOTENCY_KEY_REUSED",
    "message": "Idempotency-Key was already used for a different remote command"
  }
}
```

无数据库与公共类型变更。
