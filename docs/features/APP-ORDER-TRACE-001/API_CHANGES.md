---
id: APP-ORDER-TRACE-001
status: ready-for-dev
contract: frozen
---

# API 契约变更

## `GET /api/v1/app/transactions/{session_id}`

在现有响应中增加：

```json
{
  "invoice_number": "INV-...",
  "total_amount": "437.40",
  "currency": "COP",
  "billing_status": "paid",
  "connector_number": 1,
  "connector_label": "枪口 1",
  "charge_point_label": "CP001"
}
```

规则：

- 未生成账单时，`invoice_number`、`total_amount` 和 `billing_status` 为 `null`。
- `total_amount` 使用十进制字符串，禁止返回二进制浮点金额。
- `currency` 当前固定返回 `COP`。
- 服务端继续校验会话归属当前 App 用户。
- 现有协议字段可以暂时保留在响应中，但 App 不得展示。

## `GET /api/v1/app/wallet/transactions`

每条流水增加：

```json
{
  "charging_session_id": "uuid-or-null"
}
```

规则：

- 仅充电扣费返回关联会话 ID。
- 非充电流水或无法确认关联时返回 `null`。
- 关联会话必须属于当前 App 用户。

## 数据关系

- `Invoice.session_id` 是账单到充电会话的权威关联。
- 钱包充电扣费必须保存可验证的账单关联；具体数据库外键由后端实现确定，但不得依靠前端解析描述文本。
