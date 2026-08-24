---
id: PRC-MODE-001
status: ready-for-dev
contract: frozen
---

# API 契约变更

## 定价写请求

`PUT /api/v1/sites/{site_id}/pricing`

```json
{
  "pricing_mode": "paid | free | unavailable",
  "base_price_per_kwh": "2700.00",
  "service_fee": "0.00",
  "free_reason": null,
  "valid_until": null
}
```

`PUT /api/v1/chargers/{charge_point_id}/pricing`

```json
{
  "pricing_mode": "inherit | paid | free | unavailable",
  "base_price_per_kwh": "2700.00",
  "service_fee": "0.00",
  "free_reason": null,
  "valid_until": null
}
```

校验规则：

- `paid`：必须提供大于 0 的十进制 `base_price_per_kwh`；不得提供 `free_reason`。
- `free`：价格和服务费固定为 0；必须提供 3-500 字符的 `free_reason` 和未来 `valid_until`。
- `unavailable`：不接受价格和免费原因。
- `inherit`：仅充电桩接口接受，不接受价格和免费原因。
- 所有时间均为带时区 ISO-8601；服务端保存 UTC。

## 定价响应

两个写接口和相关 Admin/App 读接口统一返回或嵌入：

```json
{
  "pricing_mode": "paid",
  "pricing_source": "charger | site | none",
  "tariff_id": "uuid-or-null",
  "base_price_per_kwh": "2700.00",
  "service_fee": "0.00",
  "currency": "COP",
  "free_reason": null,
  "valid_from": "2026-08-05T12:00:00Z",
  "valid_until": null
}
```

- 金额使用十进制字符串；现有兼容字段可暂时保留为 number，但新 UI 必须使用统一定价对象。
- `unavailable` 时 `pricing_source=none` 或显式覆盖层级，金额字段为 `null`。
- `free` 时金额返回 `"0.00"`，并返回原因和截止时间。

## 投运错误

`POST /api/v1/chargers/{charge_point_id}/commission`

```json
{
  "detail": {
    "code": "TARIFF_NOT_CONFIGURED",
    "message": "A paid or free tariff is required before commissioning."
  }
}
```

HTTP 状态为 `409`。

## App 扫码检查/启动错误

```json
{
  "detail": {
    "code": "TARIFF_NOT_CONFIGURED",
    "message": "This charger is not currently available for commercial charging."
  }
}
```

HTTP 状态为 `409`；服务端不得下发 OCPP RemoteStart。

## 价格快照

- OCPP StartTransaction 创建 ChargingSession 时必须创建关联的 `PricingSnapshot`。
- 快照 `snapshot_data` 至少包含 `pricing_mode`、`currency`、`pricing_source`、`tariff_id`、费率组成和原始有效期。
- 结算响应继续返回现有金额字段，数据来源改为会话快照。

