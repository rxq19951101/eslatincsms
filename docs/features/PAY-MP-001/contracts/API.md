---
id: PAY-MP-001
status: frozen
contract: frozen
---

# API 契约变更

## 通用约束

- 所有 App API 使用当前 AppUser 身份；客户端不得提交 `tenant_id`、`merchant_account_ref`、Mercado Pago Access Token 或佣金。
- 金额使用十进制字符串，币种首期固定 `COP`，时间使用带时区 ISO-8601 并在服务端保存 UTC。
- 所有创建/确认/支付/退款写操作要求幂等键。
- 安全结账页接收原始卡数据并直接交给 MercadoPago.js；App JSON API 不接受 PAN、有效期或 CVV 字段。
- 首次新卡的证件类型与证件号码只作为 MercadoPago.js Card Token 输入，不属于 EsLatin API 契约，也不得包含在 confirm、Deep Link 或任何查询响应中。
- Provider 卡类型枚举冻结为 `credit_card | debit_card | prepaid_card`；卡品牌、类型、发卡方均由 Mercado Pago 根据 BIN/Token 结果提供，客户端不得手工选择或猜测。
- Card Token 的用途按 Checkout `purpose` 冻结：只有 `purpose=save_card` 可以保存新卡；`charging_direct`、`wallet_top_up` 和 `unpaid_charge` 的 Token 不得同时或随后用于 Customers/Cards 关联。
- 错误格式统一为 `{ "detail": { "code": "...", "message": "..." } }`。

## 本期范围声明

- 本期 App 只依赖通用支付方式、Hosted Checkout、充电启动/结算、支付状态和钱包充值契约。
- 服务端 D1 欠费事实门禁及 `UNPAID_CHARGES` 错误继续有效；本期 App 收到该错误时只显示安全提示并阻止继续充电。
- 欠费列表响应结构、银行卡/钱包欠费补缴 UI 和欠费恢复体验属于后续 `deferred-by-owner` 范围。本文件本期不新增或冻结欠费列表响应字段，前端不得根据后端实际返回或本地 mock 推断字段。
- 现有 `unpaid_charge` 支付目的保留为服务端能力/后续契约基础，不构成本期 App UI 交付；历史兼容端点不属于当前 App API，后续需求需单独补充并冻结欠费列表查询与补缴体验。

## 1. 创建安全结账会话

`POST /api/v1/app/payments/checkout-sessions`

```json
{
  "purpose": "save_card | wallet_top_up | charging_direct | unpaid_charge",
  "payment_method_mode": "new_card | saved_card",
  "saved_payment_method_id": "uuid-or-null",
  "save_card": false,
  "amount": "50000.00",
  "currency": "COP",
  "charge_point_id": "uuid-or-null",
  "connector_id": 1,
  "session_id": "uuid-or-null",
  "return_url": "eslatin://payment-return",
  "idempotency_key": "uuid-v4"
}
```

校验规则：

- `purpose=save_card`：必须使用 `payment_method_mode=new_card`、`save_card=true`、`saved_payment_method_id=null`，且不接受金额、充电桩或 Session。
- `wallet_top_up`：必须提供大于 0 的 `amount`；服务端应用充值上下限。
- `charging_direct`：不接受金额；必须提供 ChargePoint/connector，服务端从设备推导租户和当前有效价格。
- `unpaid_charge`：服务端能力保留；若由后续客户端流程使用，必须提供当前用户的未支付 `session_id`，金额由服务端 Invoice 计算。本期 App 不实现该入口。
- `purpose!=save_card`：必须提交 `save_card=false`；`save_card=true` 返回 400 `CHECKOUT_REQUEST_INVALID`。
- `payment_method_mode=saved_card`：必须提供属于当前用户的 `saved_payment_method_id`，必须提交 `save_card=false`，安全页仍显示 CVV 字段。
- `payment_method_mode=new_card` 且 `purpose!=save_card`：不得提供 `saved_payment_method_id`；生成的 Token 仅用于该 purpose，不创建或更新 Mercado Pago Customer/Card。
- `return_url` 只接受服务端允许列表中的 EsLatin Deep Link。

充电结算金额规则：服务端在会话结束后根据冻结的价格快照创建唯一 Invoice。付费模式的 `Invoice.total_amount` 为消费计算结果与 `1,000.00 COP` 中的较大值；免费模式为 `0.00 COP`。因此 `charging_direct` 创建的 `PaymentOrder` 和发送给 Provider 的 `transaction_amount` 必须等于该 Invoice，不得使用客户端金额或低于最低金额的原始计算结果。

当前生效覆盖（2026-08-18）：付费模式的 `Invoice.total_amount` 和 Provider `transaction_amount` 最低为 `1,011.00 COP`；实现必须使用该金额，不能使用 `1,000.00 COP` 或任何更低金额。上方原始金额文字仅保留为历史契约记录。

响应：

```json
{
  "checkout_session_id": "opaque-id",
  "checkout_url": "https://api.eslatin.com.co/api/v1/app/payments/checkout/opaque-signed-token",
  "expires_at": "2026-08-06T18:30:00Z",
  "purpose": "charging_direct"
}
```

- `checkout_url` 是短期签名 URL，不包含 Card Token、用户邮箱或商户密钥。
- 同一 AppUser + idempotency key + 相同请求返回同一有效 Checkout Session；请求内容冲突返回 409。

## 2. 托管安全结账页

`GET /api/v1/app/payments/checkout/{signed_token}`

- 返回带严格 CSP 的 HTML 页面，加载官方 MercadoPago.js。
- 页面根据 purpose 显示新卡字段或已保存卡 + CVV。
- 新卡必须动态调用 Mercado Pago 能力获得哥伦比亚证件类型，并显示证件类型/号码；不得硬编码、隐藏或默认固定为 `CC`。
- 新卡必须根据 BIN 自动识别并只读显示卡品牌、发卡方和 `credit_card | debit_card | prepaid_card`。页面不得提供卡品牌、卡类型、发卡银行或分期的手工选择；识别失败或未知类型时禁止提交。
- 已保存卡显示品牌、类型和尾号，只重新采集 CVV；Provider 额外验证除外，不重复采集证件资料。
- P0 用户可见文本固定为西班牙语，表单为紧凑移动端布局；不得显示内部 purpose、Provider 原始错误或英语字段标签。
- `charging_direct` 只能说明充电结束后按实际账单金额扣款，不能使用预授权、冻结、预扣或已付款表述。
- 页面把 Card Token 直接提交到服务端确认端点，不通过 React Native Bridge 暴露 Token。
- 只能加载 Mercado Pago 必需域名；禁止任意第三方脚本、内联日志和分析录屏。
- 会话过期/缺失、已确认或临时不可用时，GET 返回西班牙语安全错误页面，不渲染可提交卡表单，并提供返回 App/上一页或重新开始动作；不得只把 JSON/英文内部错误显示给用户。

`POST /api/v1/app/payments/checkout/{signed_token}/confirm`

- 由托管页面调用。请求体冻结为：

```json
{
  "card_token": "provider-one-time-token",
  "payment_method_id": "master",
  "payment_type_id": "credit_card | debit_card | prepaid_card",
  "issuer_id": "provider-issuer-id-or-null",
  "installments": 1
}
```

- `payment_method_mode=new_card` 时，`payment_method_id` 和 `payment_type_id` 必须来自本次 BIN/Provider 识别并且非空；未知或不支持类型返回 400 `CHECKOUT_REQUEST_INVALID`，不得默认成 `credit_card`。
- `payment_method_mode=saved_card` 时，`payment_method_id`、`payment_type_id` 和 `issuer_id` 必须为 `null` 或省略；服务端从当前用户已保存方式和 Provider Token 结果解析，禁止客户端覆盖。
- `installments` P0 固定为 `1`；其他值返回 400 `CHECKOUT_REQUEST_INVALID`。
- confirm 不接受姓名、证件类型、证件号码、PAN、有效期或 CVV。姓名和证件资料只存在于 MercadoPago.js Token 化调用，原始卡字段由 Secure Fields 持有。
- 对 App 返回 303 到允许列表中的 Deep Link；URL 只包含 `checkout_session_id` 和结果状态，不包含 Provider Token。
- 独立 `purpose=save_card` 返回已保存方式 ID；`charging_direct` 只返回 Payment Intent ID，不保存该新卡；金额确定型目的返回 PaymentOrder ID。

Hosted Checkout P0 错误语义：

| HTTP | code | 用户页行为 |
|---|---|---|
| 400 | `CHECKOUT_REQUEST_INVALID` | 保留有效会话，显示西班牙语字段/卡识别错误并允许用户修正 |
| 404 | `CHECKOUT_SESSION_NOT_FOUND` | 显示“会话已过期或不可用”全页状态，不渲染卡表单 |
| 409 | `CHECKOUT_ALREADY_CONFIRMED` | 显示“该操作已提交”，引导返回 App 查询结果，不允许重复提交 |
| 503 | `CHECKOUT_UNAVAILABLE` | 显示暂不可用和安全重试/返回动作，不声称支付失败或成功 |

## 3. 查询结账/支付意图结果

`GET /api/v1/app/payments/checkout-sessions/{checkout_session_id}`

```json
{
  "id": "opaque-id",
  "purpose": "charging_direct",
  "status": "created | ready | processing | action_required | approved | declined | expired | error",
  "payment_intent_id": "opaque-id-or-null",
  "payment_order_id": "uuid-or-null",
  "saved_payment_method_id": "uuid-or-null",
  "next_action": {
    "type": "open_url",
    "url": "https://trusted-mercadopago-host/..."
  },
  "expires_at": "2026-08-06T18:30:00Z"
}
```

- `next_action` 仅在 `action_required` 返回，URL 必须通过 Provider 允许域名校验。

## 4. 支付方式管理

`GET /api/v1/app/payment-methods`

```json
{
  "items": [
    {
      "id": "uuid",
      "provider": "mercadopago",
      "brand": "master",
      "payment_type": "credit_card | debit_card | prepaid_card | null",
      "last_four": "1234",
      "is_default": true
    }
  ]
}
```

`PATCH /api/v1/app/payment-methods/{payment_method_id}`

```json
{
  "is_default": true
}
```

`DELETE /api/v1/app/payment-methods/{payment_method_id}`

- PATCH/DELETE 只能操作当前用户的支付方式。
- `payment_type=null` 只用于尚未完成新 codec 投影的旧记录；P0 新保存卡必须是 `credit_card | debit_card | prepaid_card` 之一。
- 删除默认卡后，剩余卡按 Provider 结果和创建时间选出新默认卡；没有剩余卡则默认卡为空。
- 不提供旧 `GET /api/v1/app/wallet/saved-payment-methods`；App 统一使用 `GET /api/v1/app/payment-methods`。

## 5. 充电启动

扩展 `POST /api/v1/app/charging/start`：

```json
{
  "qr_token": "opaque-qr-token",
  "settlement_method": "wallet | direct_card",
  "payment_intent_id": "opaque-id-or-null"
}
```

规则：

- `direct_card` 必须提供 `payment_intent_id`；服务端校验用户、ChargePoint、connector、租户、有效期和未消费状态。
- `wallet` 不接受 Payment Intent，继续执行余额门禁。
- `free` 定价忽略支付方式且不要求 Intent，但仍执行 D1 欠费门禁。
- 客户端提交的 ChargePoint/租户信息不能覆盖 QR 的服务端解析结果。
- RemoteStart 失败时 Payment Intent 回到可重试状态；StartTransaction 成功后 Intent 绑定实际 Session 并不可再用于其他会话。

Payment Intent 无效时返回：

```json
{
  "detail": {
    "code": "PAYMENT_INTENT_INVALID",
    "message": "A valid payment method is required before starting this charging session."
  }
}
```

HTTP 409。

存在欠费时返回：

```json
{
  "detail": {
    "code": "UNPAID_CHARGES",
    "message": "Pay outstanding charging bills before starting another session."
  }
}
```

HTTP 402。

## 6. 会话结算

`POST /api/v1/app/charging/settle`

请求保持：

```json
{
  "session_id": "uuid"
}
```

响应扩展为：

```json
{
  "session_id": "uuid",
  "invoice_id": "uuid",
  "settlement_method": "direct_card",
  "payment_status": "processing | action_required | paid | unpaid",
  "payment_order_id": "uuid-or-null",
  "charged_amount": "18760.00",
  "currency": "COP",
  "energy_kwh": "6.80",
  "price_per_kwh": "2760.00",
  "balance": null,
  "next_action": null,
  "already_settled": false
}
```

- `direct_card`：先创建 pending Invoice，再创建相同金额的 PaymentOrder；Provider 批准后才把 Invoice/Session 标记为 paid。
- `wallet`：余额足够才原子扣款并标记 paid；余额不足返回 unpaid，不能截断余额后记为 paid。
- `free`：金额为 `"0.00"`、状态 paid、PaymentOrder 为 null。
- 并发 settle 使用 Session/Invoice 幂等约束，只能创建一个最终 Invoice 和一次成功入账。

## 7. 支付订单状态

App 不再提供独立的旧 PaymentOrder 状态接口；统一查询 Checkout Session：

`GET /api/v1/app/payments/checkout-sessions/{checkout_session_id}`

该接口的 `payment_order_id` 只作为非敏感结果引用返回，状态以 Checkout Session 状态为准。历史 `GET /api/v1/app/wallet/payments/{order_id}/status` 不注册。

历史响应（仅供内部迁移审计，不是当前 API 契约）：

```json
{
  "order_id": "uuid",
  "purpose": "charging_direct",
  "status": "created | processing | action_required | approved | declined | voided | error | expired | refunded",
  "status_detail": "provider-specific-safe-code-or-null",
  "amount": "18760.00",
  "currency": "COP",
  "invoice_id": "uuid-or-null",
  "session_id": "uuid-or-null",
  "next_action": null,
  "paid_at": "2026-08-06T19:00:00Z",
  "expires_at": "2026-08-06T19:30:00Z"
}
```

## 8. 欠费补缴（服务端保留，App 体验后续冻结）

- 现有能力通过 `POST /payments/checkout-sessions` 且 `purpose=unpaid_charge` 创建安全结账会话；本期 App 不依赖或调用该入口。
- 选择钱包时的补缴服务仍须校验余额足够并原子完成 Invoice/Payment/Session；历史 `POST /api/v1/app/wallet/pay-unpaid-charge` 不属于当前 App API，本期不交付对应 App UI。
- 同一 Invoice 多次银行卡重试创建独立 PaymentOrder 尝试；第一个 approved 赢得入账，后续批准必须自动进入退款/人工异常队列，不能重复结清；该补缴用户体验留待后续需求。
- `GET /api/v1/app/wallet/unpaid-charges` 的实际后端路由及其响应结构不在本期冻结契约中；后续需求必须单独定义路径约束、顶层响应、字段、分页/排序、错误语义和跨用户/租户归属规则。

## 9. Mercado Pago Webhook

`POST /api/v1/app/payments/webhooks/mercadopago`

Provider-specific Webhook 只负责验签、主动反查和映射，结果必须进入统一 PaymentOrder/Checkout 状态机。历史 `/api/v1/app/wallet/payments/webhook-mp` 不注册。

- 通过 Provider ID/external reference 查找 PaymentOrder，再读取订单保存的 `merchant_account_ref`。
- 使用 `MerchantAccountResolver` 获得对应 MerchantContext 后主动反查。
- C1 MerchantContext 为平台商户；Webhook 处理代码不得直接读取唯一全局 Token。
- 验签、事件幂等、金额/币种/订单归属校验通过后才能更新业务状态。
- Webhook HTTP 响应不得泄漏订单、用户、租户或 Provider 错误详情。

## 10. 商户账户内部契约

内部接口，不对 App 暴露：

```text
MerchantAccountResolver.resolve(operator_tenant_id, payment_purpose)
  -> MerchantContext(
       merchant_mode,
       merchant_account_ref,
       provider,
       credential_handle,
       marketplace_fee_policy
     )
```

- C1 返回 `merchant_mode=platform` 和 `merchant_account_ref=platform:eslatin`。
- `credential_handle` 只供 Provider Adapter 在服务端解析密钥，不可写入 Order、PaymentOrder、Webhook payload 或日志。
- C2 可按租户返回 OAuth credential handle 和 application fee policy；不得改变本文件中的 App API。
