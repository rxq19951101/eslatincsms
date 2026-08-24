---
id: ADM-TRANSACTIONS-001
status: ready-for-dev
contract: frozen
---

# GET `/api/v1/transactions`

权限：`transactions.read`

查询参数：

- `search?: string`，最多 100 字符
- `status?: ongoing|completed|cancelled`
- `payment_status?: string`
- `site_id?: string`，接受站点公开编号或内部 UUID，但必须属于当前租户
- `charge_point_id?: string`，接受充电桩公开引用或内部 UUID，但必须属于当前租户
- `started_from?: ISO-8601 datetime`
- `started_to?: ISO-8601 datetime`
- `limit: 1..200`，默认 50
- `offset >= 0`，默认 0

响应：

```json
{
  "items": [
    {
      "id": "internal-session-uuid",
      "record_number": "CHG-20260721-1827687336",
      "invoice_number": "INV-...",
      "ocpp_transaction_id": 1827687336,
      "site": {"site_code": "site_...", "name": "Centro", "address": "..."},
      "charger": {"display_code": "A-01", "display_name": "Entrada", "ocpp_identity": "..."},
      "connector": {"evse_id": 1, "physical_reference": "Puesto 1", "connector_type": "Type2", "max_power_kw": "7.00"},
      "user_reference": "user@example.com",
      "start_time": "2026-07-21T20:10:33Z",
      "end_time": "2026-07-21T20:41:16Z",
      "energy_kwh": "2.660",
      "duration_minutes": "30.72",
      "amount": "7182.00",
      "currency": "COP",
      "status": "completed",
      "payment_status": "approved",
      "anomaly_codes": []
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

约束：

- 所有 Decimal/Numeric 字段使用字符串；未知值为 `null`。
- `record_number` 是显示引用，不是数据库关系键。格式为 `CHG-YYYYMMDD-<OCPP transaction id>`；若同日同号仍可能跨桩重复，前端不得用它作为 React key，API 的 `id` 才是内部唯一键。
- `anomaly_codes` 可选值：`invalid_meter_delta`、`missing_end_time`、`power_exceeds_rating`。

# GET `/api/v1/transactions/export`

权限和过滤参数同列表（不接受 `limit/offset`），返回 `text/csv; charset=utf-8`。导出上限 10,000 条；超过时返回 422，提示缩小日期范围。

# 兼容性

`GET /api/v1/transactions` 从数组升级为分页对象；Admin 在同一需求内同步更新。App 不消费该后台接口。

