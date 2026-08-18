---
id: SIM-E2E-001
status: ready-for-dev
contract: frozen
---

# 冻结契约

## OCPP

- 版本：OCPP 1.6J；子协议 `ocpp1.6`。
- canonical WebSocket：`/ocpp?id=<urlencoded_ocpp_identity>`。
- `ocpp_identity`：`^[A-Za-z0-9._:-]{1,64}$`，与 Boot serial 独立。
- CSMS 不发送非 OCPP greeting；模拟器不接受简化 dict 消息。
- OCPP UniqueId 是协议消息幂等键；重放返回首次结果。
- `ChargingSession.id` 是 UUID；`transaction_id` 是正整数协议编号。
- `BootNotification` 只接受已通过后台预登记的 `ocpp_identity`；未知 identity 返回
  OCPP 1.6J `BootNotificationResponse.status=Rejected`，且不自动创建任何设备资产。

## Admin actor

- 使用现有管理员 API。
- tenant 资源同时发送 Bearer、`X-Tenant-Id`。
- 写命令使用稳定 `Idempotency-Key`。
- Remote API 保持 snake_case。

## App actor

- 使用现有 App API，不发送前端自选 tenant id。
- 充电路径固定为 `/app/charging/check|start|active|meter-values|stop|settle`。
- 所有 session/EVSE/meter resource id 在 JSON 中为 UUID 字符串。

## 场景 DSL 1.0

顶层字段：`schema_version`、`scenario`、`environment`、`actors`、`steps`、`reports`。

步骤字段：`id`、`actor`、`action`、`with`、`expect`、`save`、`timeout`、`retry`、`depends_on`、`parallel`。

首批 action：

- 系统：`provision`、`await`、`assert`、`sleep`。
- 设备：`connect`、`disconnect`、`reconnect`、`boot`、`status`、`authorize`、`start_transaction`、`meter_values`、`stop_transaction`、`duplicate`、`send_raw`。
- Admin：`login`、`create_site`、`register_charger`、`generate_qr`、`adjust_wallet`、`remote_start`、`remote_stop`、`ack_alert`、`resolve_alert`。
- App：`register`、`login`、`check_qr`、`start_charging`、`get_active`、`get_meter_values`、`stop_charging`、`settle`、`get_wallet`、`get_history`。
- 支付：`emit_webhook`，状态只允许 `approved|pending|rejected|timeout`。

Secret 值只能使用 `${ENV_NAME}`；schema 校验禁止凭证字面量。

## 错误和报告

- 场景状态：`PASS|FAIL|BLOCKED|NOT_RUN`。
- 每步记录 `run_id/scenario_id/step_id/start/end/outcome/trace_id`。
- request/response/OCPP frame 进入报告前必须脱敏。

## 本地假支付契约

- 入口：`POST /api/v1/app/payments/webhooks/sim`。
- 仅 `development|test` 启用；其他环境固定返回 404。
- Secret 只能通过 `SIM_E2E_WEBHOOK_SECRET` 注入。
- Header：
  - `Idempotency-Key: <event_id>`
  - `X-Sim-Signature: sha256=<lowercase HMAC-SHA256 hex>`
- Payload 包含 `event_id`、`provider=fake`、`status`，并且
  `payment_order_id` 与 `session_id` 必须且只能提供一个。
- 状态只允许 `approved|pending|rejected|timeout`，分别映射为
  `approved|processing|declined|error`。
- 签名消息为 UTF-8 canonical JSON：key 排序，分隔符为 `,` 和 `:`，
  不进行 ASCII 转义。
- 首次响应必须返回订单状态、钱包余额、Webhook 事件数、账本数和
  `replayed=false`；同一事件重放必须返回 `replayed=true`，事件数和账本数
  仍为 1，余额不得再次变化；同一 `event_id` 携带不同 payload 返回 409。
- 业务状态查询沿用正式接口：
  `GET /api/v1/app/payments/checkout-sessions/{checkout_session_id}` 与
  `GET /api/v1/admin/payments/{payment_order_id}`。

## Seed JSON 1.1

- 脚本只允许在 `development|test` 执行，且必须从环境注入管理员、App 用户、
  只读管理员密码。
- 输出保留 1.0 顶层兼容字段，并增加 `fixtures`：tenant A/B、operator/readonly、
  funded/low_balance/other App 用户、primary/other/tenant_b 充电桩和 QR、稳定归属
  会话、假支付订单与故障告警。
- 输出不得包含密码、JWT、Webhook secret 或完整第三方凭据；连续执行必须产生相同
  ID 且不重复建数。
