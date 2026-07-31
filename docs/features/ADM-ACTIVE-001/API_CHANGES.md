---
id: ADM-ACTIVE-001
status: ready-for-dev
contract: frozen
---

# API 契约

`GET /api/v1/transactions/active` 返回业务会话和公共资产展示字段：

```json
{
  "site": {
    "id": "site public code",
    "name": "Site name",
    "address": "Site address"
  },
  "charger": {
    "id": "internal UUID used by existing control API",
    "display_code": "CP001",
    "display_name": "Lobby charger"
  },
  "connector": {
    "id": "internal UUID for routing only",
    "connector_number": 1,
    "physical_reference": "CP001-1"
  },
  "user_reference": "masked or tenant-safe user reference",
  "last_meter_at": "2026-07-21T20:00:00Z",
  "estimated_cost": "6804.00",
  "currency": "COP"
}
```

规则：

- `estimated_cost` 使用十进制定点字符串返回，不能使用二进制浮点金额。
- 无可靠电量或费率时，`estimated_cost` 与 `currency` 可以为 `null`。
- 费率选择沿用当前 BillingService 规则，不创建新的计费口径。
- `site.id` 为公开 site_code；内部 UUID 不展示给运营人员。
- `charger.id` 和 `connector.id` 仅用于路由，不在 UI 中显示。
- 响应不返回 OCPP Identity、OCPP transaction ID 或 EVSE ID。

## `POST /api/v1/ocpp/remote-stop-session`

```json
{
  "session_id": "charging session UUID",
  "operation_reason": "Driver requested support"
}
```

- 必须携带 `Idempotency-Key`。
- 服务端根据当前租户和 `session_id` 解析充电桩与 OCPP transaction ID。
- 仅允许停止当前租户的 ongoing 会话。
- 客户端不得提交 OCPP Identity 或 OCPP transaction ID。
- 旧 `remote-stop-transaction` 接口删除，不提供兼容别名。
