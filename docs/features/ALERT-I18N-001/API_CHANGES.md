---
id: ALERT-I18N-001
status: ready-for-dev
contract: frozen
---

# API 契约

`GET /api/v1/admin/alerts` 及所有返回 `AlertResponse` 的端点保留既有字段，并新增：

```json
{
  "alert_code": "charger.offline.heartbeat_timeout",
  "message_params": {"timeout_seconds": 90},
  "raw_message": "OCPP WebSocket connection closed",
  "site": {
    "site_code": "site_0123456789abcdef",
    "name": "SIM E2E Test Site",
    "address": "Calle 100 # 10-20, Bogota"
  },
  "charge_point": {
    "ocpp_identity": "SIM-E2E-CP-001",
    "model": "Simulated 7kW",
    "serial_number": "SIM-001"
  },
  "evse": {
    "evse_id": 1,
    "physical_reference": "Bay 1"
  }
}
```

所有新增对象均可为空。`charge_point_id` 和 `evse_id` 继续作为内部关联字段，不在主界面展示。`alert_code` 的 P0 值包括：

- `charger.offline.heartbeat_timeout`
- `charger.offline.websocket_disconnected`
- `charger.faulted`
- `device.event`
- `manual`

未知代码必须由前端使用通用本地化文案并保留 `raw_message`。
