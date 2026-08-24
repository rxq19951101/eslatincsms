---
id: APP-SITE-001
status: ready-for-dev
contract: frozen
---

# API 契约

## `GET /api/v1/app/sites`

查询参数：

- `latitude?: number`
- `longitude?: number`
- `radius?: number`，单位米；仅在经纬度同时存在时生效。
- `limit?: integer`，默认 100，范围 1–200。

响应为数组，每个元素：

```json
{
  "id": "site UUID",
  "name": "Site name",
  "address": "Site address",
  "latitude": 4.61,
  "longitude": -74.08,
  "status": "Available | Charging | Offline | Unavailable | Unknown",
  "charger_count": 2,
  "available_connectors": 3,
  "total_connectors": 4,
  "status_counts": {
    "available": 3,
    "charging": 1,
    "offline": 0,
    "faulted": 0,
    "occupied": 0,
    "unavailable": 0,
    "unknown": 0
  },
  "connector_types": ["CCS2", "Type2"],
  "max_power_kw": 120.0,
  "price_per_kwh": 2700.0,
  "has_pricing": true,
  "distance_km": 1.25
}
```

`distance_km` 仅在请求提供经纬度时出现。状态只使用最近 5 分钟内的接口状态聚合。

`status_counts` 为归一化后的用户状态分组。`Preparing`、`Finishing`、`Reserved`、`SuspendedEV` 和 `SuspendedEVSE` 计入 `occupied`；超过在线窗口的接口计入 `offline`。所有分项之和必须等于 `total_connectors`。

每个 `charging_options` 元素除 `standard`、`current_type`、`max_power_kw`、`available` 和 `total` 外，也返回同结构的 `status_counts`；其分项之和必须等于该选项的 `total`。

## `GET /api/v1/app/sites/{site_id}`

返回上述站点字段，并增加：

```json
{
  "charge_points": [
    {
      "id": "charge point UUID",
      "status": "Available | Charging | Offline | Unavailable | Unknown",
      "vendor": "Vendor",
      "model": "Model",
      "connectors": [
        {
          "id": "EVSE UUID",
          "connector_number": 1,
          "physical_reference": "4A",
          "status": "Available",
          "connector_type": "Type2",
          "power_kw": 7.0
        }
      ]
    }
  ]
}
```

内部 `ocpp_identity`、`evse_id` 和旧 `connector_id` 不作为消费者端字段，本契约不返回这些字段。App 使用 `physical_reference` 或国际化的 `connector_number` 作为充电枪名称。
