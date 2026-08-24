---
id: PAY-MP-001
status: approved
owner: backend
reviewed_at: 2026-08-12
---

# 后端技术设计

## 1. 目标、输入与硬边界

本设计只覆盖 `BE-P0-1` 和 `BE-P0-2`。产品事实来自 `product/`，HTTP 字段/状态/错误码来自冻结的 `contracts/API.md`；本文不新增或改写共享契约。

硬边界：

- 不新增数据库迁移、不导入历史支付方式、不修改前端或 Admin。
- 继续复用 `AppUserPaymentMethod.payment_method_brand`、加密 Redis Checkout state、`Order.pre_authorization` 和 `PaymentOrder.metadata`。
- Provider 卡类型只有 `credit_card`、`debit_card`、`prepaid_card`。空、未知、冲突或 Provider 未返回类型均失败关闭。
- 证件类型和号码只存在 Hosted HTML 的内存和 MercadoPago.js tokenization 调用中；不进入 confirm JSON、Redis、数据库、日志、分析、Deep Link 或错误追踪。
- 当前用户、服务端推导的租户/充电对象、金额和 MerchantContext 是服务端事实；客户端不能覆盖。
- `PAYMENT_RAILS_ENABLED` 保持 `false`，后端 QA 继续暂停；本设计通过不等于 QA 或生产支付启用。
- 结算金额先由 `BillingService` 生成权威 Invoice：付费充电会将消费计算结果抬高到每会话最低 `1,011.00 COP`，免费模式固定为 `0.00 COP`。`PaymentOrder`、Provider 请求、钱包扣款和欠费补缴只能复用 Invoice 金额，禁止把低于最低金额的原始 MeterValues 计算结果直接发送给 Provider。

## 2. 组件与依赖关系

```text
POST/GET checkout API
        |
        v
CheckoutSessionService ---- CheckoutSessionStore
        |                         |
        |                         +-- encrypted Redis state / one-time token
        |
        +-- PaymentMethodCodec
        +-- PaymentMethodService ---- MercadoPagoProvider ---- MerchantContext/CredentialResolver
        +-- Charging Payment Intent / PaymentReconciliation
        |
        +-- HostedPageRenderer
                |
                +-- MercadoPago.js identification capability
                +-- MercadoPago.js BIN/card Secure Fields
```

`CheckoutSessionService` 负责状态、归属、幂等和安全 hint；`HostedPageRenderer` 只负责 HTML/JS/CSS 和西语用户体验；Provider adapter 负责 Provider 响应 canonicalization；codec 是唯一的本地兼容投影入口。

## 3. BE-P0-1：卡类型契约与 Provider 投影

### 3.1 Canonical 集合与 codec

在 `csms/app/services/payment_method_codec.py` 扩展唯一的 `SUPPORTED_PAYMENT_TYPES`：

```text
credit_card | debit_card | prepaid_card
```

保留现有编码格式 `v1:<normalized_brand>:<payment_type>`，长度仍受数据库列限制。行为固定如下：

| 输入 | encode | decode/API |
|---|---|---|
| 有效 brand + 三类之一 | 写 `v1:<brand>:<type>` | 返回 brand/type |
| 旧纯 brand（如 `visa`） | 不回写 | brand/`payment_type=null` |
| `v1` 中未知 type | 不生成新记录 | brand/`payment_type=null`，不得猜测 |
| 空、非法或敏感 label | 拒绝写入 | 安全空投影或按现有错误边界失败 |

禁止各路由、Provider 或 reconciliation service 自行 `split(":")` 或把 `None` 映射为信用卡。历史值只在读取时兼容，不做批量重写。

### 3.2 Confirm 校验和状态保存

`ConfirmCheckoutRequest.payment_type_id` 的 Literal 扩展为冻结契约中的三类。`CheckoutSessionService.confirm` 按模式执行：

- `payment_method_mode=new_card`：无论 purpose 是 `save_card`、`wallet_top_up` 还是 `charging_direct`，都要求 `payment_method_id` 非空、格式合法，`payment_type_id` 非空且属于 canonical 集合；`issuer_id` 可选但只能是 provider-safe id；`installments` 必须为 `1`。
- `payment_method_mode=saved_card`：`payment_method_id`、`payment_type_id`、`issuer_id` 必须为空或省略；服务端用当前用户和 Checkout state 中的 saved method id 重读本地投影，不能接受客户端覆盖。
- 校验通过后只在 Redis confirmation state 的 `provider_hints` 中保存非敏感 canonical hint；不保存证件资料和原始 Provider response。
- `save_card` 不应再享受现有的“跳过 payment type 校验”例外。即使 Provider 最终会再次校验，API 层也必须拒绝空/未知 hint，避免 UI 成功生成不可审计的卡片投影。

### 3.3 Provider Card 与 Payment Provider 投影

修改范围集中在 `csms/app/services/payment_providers/base.py`、`mercadopago_service.py` 和 `mercadopago_provider.py`：

1. `ProviderCardResult.payment_type` 必须是 canonical 集合成员；可在 Provider adapter 边界用共享 normalizer 校验。
2. Mercado Pago Card response 的 `payment_method.type`/等价字段是 Provider 事实。缺失或未知时抛 `mercadopago_card_response_invalid`，不得使用 `payment_type_id` 或 `credit_card` 作为静默 fallback。
3. brand 也必须通过 safe-label 校验；输入的 `payment_method_id` 只能作为 Provider 请求 hint，不得在 Provider response 缺失时伪造 brand/type 事实。
4. `payment_method_id`、`payment_type_id` 和 issuer 只作为服务端已校验的 Provider request hints 传递；saved-card 支付从服务端本地投影取得，不接受客户端重写。
5. 任何 Provider 返回 `prepaid_card` 都必须原样进入 `ProviderCardResult`、codec、保存卡 API 和支付提示；任何未知类型都返回安全 Provider 错误，不创建本地行。

BE-6/BE-7 已存在的 `provider_hints` 兼容读取保持：通过 codec 读取 saved-card 时 `payment_type=null` 就失败关闭，不回退信用卡；新建 PaymentOrder 的 metadata 仍只保存 provider-safe id/type、purpose、tenant/merchant snapshot 等非敏感事实。

### 3.4 BE-P0-1 事务、幂等和租户

- `PaymentMethodService.save_card` 继续锁当前用户的 Provider payment-method rows；Provider Customer/Card 调用仍使用 C1 MerchantContext；Provider 成功后才写本地 projection。
- 同一用户/Provider Card 的已有幂等行为保持；重复 callback 复用已存在投影，不改变默认卡规则。
- 任何跨用户 payment method id 仍返回 404 等价安全错误；不通过错误信息泄漏存在性。
- codec 失败或 Provider response 不完整时，事务回滚，不留下半成品 `AppUserPaymentMethod`、Customer/Card projection 或支付成功事实。

## 4. BE-P0-2：Hosted Checkout P0

### 4.1 内部页面数据模型

不改变 HTTP 响应 schema；仅扩展后端内部 `HostedCheckoutPage` 及 renderer 输入：

```text
HostedCheckoutPage
├─ checkout_session_id / purpose / payment_method_mode
├─ save_card / amount / public_key
├─ saved_provider_card_id
├─ saved_card_brand / saved_card_payment_type / saved_card_last_four
└─ ui_state=ready  （错误状态由 safe-state renderer 单独生成）
```

`saved_card_payment_type` 必须由 `decode_payment_method_brand` 得到。旧卡为 `null` 时，页面显示通用安全卡文案，不猜测信用卡；如产品要求 saved-card 付款必须有类型，服务端应把旧记录按 provider-safe fallback/重新绑卡流程处理，而不是改变历史记录。

### 4.2 New-card 页面状态机

```text
initializing
  ├─ getIdentificationTypes -> document_ready | capability_error
  └─ Secure Fields binChange
       ├─ empty/short/changed -> capability_idle (clear old facts)
       ├─ getPaymentMethods(bin) -> capability_ready
       └─ empty/unknown/conflicting -> capability_error

capability_ready + valid fields -> confirmable
confirmable --submit--> tokenizing --303--> App Deep Link
```

实现规则：

- 页面加载后调用 `mp.getIdentificationTypes()` 或当前 SDK 对应的官方 capability adapter；结果必须是非空、结构合法的 Provider list。`id`、显示名称、数据类型和长度约束写入页面内存，不能写入 EsLatin API。
- 卡号 Secure Field 的 BIN 变化立即清除旧的 payment method id/type/issuer/brand，并禁用提交；短 BIN、空 BIN、接口失败或响应为空都保持不可提交。
- 只读 capability view 显示 Provider 返回的 brand、issuer 和 `credit_card`/`debit_card`/`prepaid_card` 对应西语标签；没有 select、radio 或可编辑输入供用户选择卡种、银行、分期或 issuer。
- capability normalizer 只接受一个无冲突的 canonical payment method candidate；多个候选若 type/brand/issuer 冲突，显示通用可行动错误并保持禁用。
- `createCardToken` 只在 document/capability/field validation 完成后调用。confirm body 仅提交 `card_token`、Provider-safe `payment_method_id`、`payment_type_id`、可选 `issuer_id` 和固定 `installments=1`。
- 识别失败时不调用 confirm；即使恶意客户端绕过页面提交未知值，服务端 P0-1 校验也必须拒绝。

页面静态用户文案固定为 `es-CO` 西班牙语；purpose 只选择文案，不出现在 DOM、用户文本或错误消息中：

| purpose | CTA/说明 |
|---|---|
| `save_card` | `Guardar tarjeta`；说明数据直接发送给 Mercado Pago |
| `charging_direct` | `Validar tarjeta y continuar`；“La tarjeta se cobrará al finalizar la carga por el importe calculado, con un mínimo de 1.011 COP.” |
| `wallet_top_up` / `unpaid_charge` | 金额确定时显示安全付款 CTA 和 COP 金额 |

不得出现 `charging_direct`、`save_card`、Provider 原始英文、预授权、冻结、预扣或“已付款”表述。

### 4.3 Saved-card 页面

- 服务端 `_saved_payment_method` 同时按 Checkout state 中的 id、当前 AppUser、Provider 过滤；页面使用该记录的 Provider Card ID 和 codec projection。
- 页面显示 brand、类型（信用卡/借记卡/预付卡的西语标签）和尾号，只挂载 `securityCode` Secure Field。
- `createCardToken({cardId})` 生成新的单次 Token；confirm body 的三个 card facts 为空或省略。页面不包含 `card-number`、`expiration-date`、`cardholder-name`、identification type/number DOM。
- Provider 额外要求证件信息时，Provider/页面能力必须转为安全错误或额外验证状态，不由 EsLatin 自己持久化证件资料。

### 4.4 会话安全状态页

新增 renderer 分支，而不是把异常 JSON 直接嵌入 HTML：

| 错误/状态 | HTTP | 是否渲染 Secure Fields | 文案/动作 |
|---|---:|---|---|
| 签名错误、缺失、TTL 过期、`expired` | 404 | 否 | 西语过期/不可用；只给 allowlist Deep Link 返回和重新开始提示 |
| 已确认、`ready`、处理中或其他已提交状态 | 409 | 否 | 西语已提交；返回 App 查询原会话，不允许重复提交 |
| Redis、配置或 Provider capability 暂不可用 | 503 | 否 | 西语暂不可用；安全刷新/返回，不声称成功或失败 |

GET 路由在捕获 `CheckoutSessionMissing`、`CheckoutAlreadyConfirmed`、`CheckoutServiceUnavailable` 时调用状态页 renderer，并沿用 `no-store`、CSP、`Referrer-Policy`、`X-Content-Type-Options` 等响应头。confirm 路由继续返回冻结 JSON error envelope。

错误页的返回动作只能来自配置 allowlist 的安全 EsLatin Deep Link；无可验证 session 时不反射任意 query 或 Referer。状态页 HTML 不包含 `card_token`、signed token、用户邮箱、merchant secret 或完整错误对象。

### 4.5 Checkout 用途与单次 Token

`CreateCheckoutSessionCommand.save_card` 必须在创建会话时按以下冻结矩阵校验，并写入幂等请求指纹和 Redis state；刷新、重试、确认和回跳都不得改变用途：

| purpose | payment method mode | save_card | Token 唯一用途 |
|---|---|---:|---|
| `save_card` | `new_card` | `true` | 关联 Mercado Pago Customer/Card |
| `charging_direct` | `new_card` 或 `saved_card` | `false` | 当前充电结束后的最终扣款 |
| `wallet_top_up` | `new_card` 或 `saved_card` | `false` | 当前钱包充值 |
| `unpaid_charge` | `new_card` 或 `saved_card` | `false` | 当前欠费账单补缴 |

`purpose=save_card` 使用其他模式、其他 purpose 设置 `save_card=true`、任何 `saved_card` 模式设置 `save_card=true`，均在创建 Checkout Session 且写入 Redis/调用 Provider 前返回 `400 CHECKOUT_REQUEST_INVALID`。托管页根据已经冻结的状态渲染，不提供改变保存行为的控件。每个 Card Token 只能被对应 purpose 的既有原子消费链路消费一次。

## 5. 事务、幂等、恢复与观测

- Checkout create 继续使用 AppUser + idempotency key + normalized request fingerprint；相同请求复用，冲突 409。
- Hosted confirm 仍由 Redis compare-and-set 锁住 `created` 状态，Card Token 只经加密仓库原子消费一次。Redis 故障、密文损坏、过期或重复 confirm 都失败关闭。
- P0-1 codec/Provider 校验失败发生在本地状态持久化前；P0-2 capability 错误不调用 confirm。Provider 网络调用的失败由现有 reconciliation/PaymentMethodService 安全映射，不伪造 approved。
- Checkout 303 只携带会话 id/status；App 关闭后由现有 query/reconcile 恢复，不能从页面或本地猜测支付结果。
- 观测字段限于 request id、checkout id、PaymentOrder id、Invoice id、Session id、merchant account ref、安全错误码和耗时。新增指标：`checkout_identification_types_failure`、`checkout_bin_capability_failure`、`checkout_unknown_payment_type`、`checkout_invalid_state_page`；指标标签不得包含用户、Token、证件或完整 Provider payload。

## 6. 文件影响与禁止范围

### BE-P0-1 所有权

- `csms/app/services/payment_method_codec.py`
- `csms/app/api/v1/app/payment_checkout.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/app/services/payment_providers/base.py`
- `csms/app/services/payment_providers/mercadopago_provider.py`
- `csms/app/services/mercadopago_service.py`（只做 Provider card response canonicalization 所需最小调整）
- `csms/app/services/payment_methods.py`
- `csms/app/services/payment_reconciliation.py`（只修正 card hint/codec 边界）
- `csms/tests/test_payment_methods.py`
- `csms/tests/test_checkout_session_api.py`
- 需要时新增限定的 `csms/tests/test_payment_method_codec.py`

### BE-P0-2 所有权

- `csms/app/services/payment_checkout/hosted_page.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/app/api/v1/app/payment_checkout.py`
- 上述 Hosted/Checkout 定向测试文件；如需视觉/HTML contract 测试，新增后端测试文件

两项均禁止修改 `docs/features/PAY-MP-001/contracts/API.md`、数据库模型/迁移、App/Admin、OCPP/计费核心和生产配置真实值。BE-P0-2 只能在 BE-P0-1 交接后取得这些文件所有权，避免同一文件并发编辑。

## 7. 测试计划与通过标准

### BE-P0-1

- codec：三类 encode/decode、旧纯 brand、未知 type、非法 label、长度和无猜测。
- confirm：三类 new-card 通过；空/未知 type、空 payment method、错误 installments、save-card 空 hint 拒绝；saved-card 客户端覆盖被拒绝。
- Provider：三类 Provider Card 响应投影；缺失/未知/冲突 type 失败；绝不 fallback `credit_card`。
- service/API：prepaid 在保存卡、canonical API、checkout result/provider hints 中完整投影；旧记录为 null；跨用户 404；Token/证件字段不落 Redis/DB/log。
- 回归：现有 Checkout/PaymentMethod/PaymentReconciliation/P0 app tests，且不得改变钱包、direct-card金额或 D1 行为。

### BE-P0-2

- new-card HTML：动态 identification types、动态 BIN、brand/issuer/type 只读、prepaid 展示、无手工选择、识别失败禁用确认。
- saved-card HTML：只有 CVV；显示 brand/type/尾号；不出现新卡和证件字段。
- 文案/布局：`lang=es`、静态文案全西语、purpose/Provider 原始错误不出现在可见 DOM；Secure Fields 高度紧凑、窄屏单列、focus/aria/live/disabled/loading 语义存在。
- 状态页：签名缺失/过期 404、已确认 409、暂不可用 503；每种都不含可提交卡字段并提供安全动作。
- 安全：confirm 仍只接受冻结字段；页面/Deep Link/日志无 PAN、有效期、CVV、证件资料、明文 Token、secret。
- 回归与手工：Hosted CSP/303、Checkout query、保存卡、钱包充值、direct intent、真实 sandbox/Redis/PostgreSQL/视觉可访问性由后端 QA 分别验收；未恢复 QA 前不标通过。

## 8. 开发门禁

本设计已按重新冻结的产品规则和共享契约批准：

1. `BE-P0-1` 状态为 `ready-for-dev`，先实现 canonical Provider response、三类卡投影和失败关闭。
2. `BE-P0-2` 状态为 `blocked-by-BE-P0-1`；只有 P0-1 完成交接并经只读复核后，才解除共享文件所有权并开始 Hosted Checkout 实现。
3. 实现不得修改冻结 API、数据库模型/迁移、前端/Admin、生产密钥或 `PAYMENT_RAILS_ENABLED`。

后端 QA 暂停期间只保留开发测试事实；设计批准和开发测试均不等于 QA 通过或生产支付轨启用。
