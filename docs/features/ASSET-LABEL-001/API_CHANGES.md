---
id: ASSET-LABEL-001
status: ready-for-dev
contract: frozen
---

# API 契约

## 公共充电桩展示对象

```json
{
  "id": "internal UUID for routing only",
  "display_code": "CP001",
  "display_name": "地库 A 区",
  "location_hint": "B2 层东侧"
}
```

默认标题为 `display_name || display_code`。`id` 只用于路由和 API 操作，不允许直接渲染为名称。

## 公共充电枪展示对象

```json
{
  "id": "internal UUID for routing only",
  "connector_number": 1,
  "physical_reference": "A-01",
  "connector_type": "Type2",
  "power_kw": 7.0,
  "status": "Available"
}
```

- `connector_number` 为同一充电桩内稳定正整数。
- `physical_reference` 为可选现场标签，不是翻译文案。
- 公共 App 与 Admin 运营对象不返回 `connector_id` 或 `evse_id`。

## Admin 技术对象

Admin 接入诊断接口可以继续返回：

- `ocpp_identity`
- `ocpp_transaction_id`
- `evse_id`
- `connector_id`

上述字段不得作为默认运营名称，也不得由业务远程停止页面提交。

## 切换规则

- 不提供 `connector_id` 到 `connector_number` 的兼容别名。
- App 与 Admin 消费端必须统一切换到 `connector_number`。
- 业务远程停止统一提交 `session_id`，由服务端解析协议字段；协议字段只存在于技术诊断和服务端控制实现中。
