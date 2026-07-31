---
id: ADM-CONTROL-001
status: ready-for-dev
contract: frozen
---

# API 契约

## Remote start

`POST /api/v1/ocpp/remote-start-transaction`

```json
{
  "charge_point_id": "charge point reference",
  "connector_id": 1,
  "operation_reason": "On-site commissioning"
}
```

- `connector_id` 无默认值，必须显式提供。
- `operation_reason` 必填，去除首尾空白后长度 3-200。
- `id_tag` 从公开请求契约移除；服务端生成 `OPS-<admin-id-prefix>`，最大 20 字符。
- 前置条件失败使用 409，并返回稳定错误码：`CHARGER_OFFLINE`、`CONNECTOR_STATUS_UNKNOWN`、`CONNECTOR_NOT_AVAILABLE`、`CONNECTOR_SESSION_ACTIVE`。

## 其他远程命令

以下请求增加必填 `operation_reason`（3-200 字符）：

- `POST /api/v1/ocpp/remote-stop-transaction`
- `POST /api/v1/ocpp/reset`
- `POST /api/v1/ocpp/unlock-connector`

响应结构保持 `RemoteResponse`，命令仍要求 `Idempotency-Key` 并记录 Outbox/AuditLog。
