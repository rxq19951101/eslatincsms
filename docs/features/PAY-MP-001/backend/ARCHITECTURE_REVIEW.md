---
id: PAY-MP-001
status: approved
owner: backend
reviewed_at: 2026-08-12
---

# 后端架构评估

## 结论

P0 增量可以沿用现有 Checkout Session、加密 Redis Token 仓库、`Order.pre_authorization`、`PaymentOrder.metadata` 和 `AppUserPaymentMethod`，不需要数据库迁移、历史数据导入或共享 API 变更。

本轮必须把既有设计从“BE-1..BE-7 基线”重新收敛为两个串行的后端任务：

1. `BE-P0-1` 负责卡类型的规范化和端到端投影。它可以独立实现、独立测试，不依赖 HTML 重排；完成后 `prepaid_card` 才能进入 P0-2 托管页和 Provider 支付提示。
2. `BE-P0-2` 负责托管页的动态证件类型、BIN/Provider 自动识别、西班牙语紧凑布局、保存卡 CVV 和会话安全状态页。它只消费 P0-1 提供的 canonical card capability，不重新定义卡类型。

冻结契约可以支撑上述两个任务，但实现必须失败关闭：空 BIN、识别失败、未知 Provider 类型、证件类型能力加载失败、Provider Card 响应缺少受支持类型，都不能回退为 Visa 或 `credit_card`。

负责人已经确认并重新冻结 Token 用途：只有 `purpose=save_card + payment_method_mode=new_card` 可以设置 `save_card=true`，且该 Token 只用于 Customers/Cards 关联；`charging_direct`、`wallet_top_up`、`unpaid_charge` 以及所有 `saved_card` 模式固定 `save_card=false`，其 Token 只服务当前业务目的。该单用途边界与现有 Checkout Session、Token 原子消费和支付意图链路兼容，不需要新增字段、迁移或其他产品选择。

## 现有架构与证据

| 边界 | 当前实现事实 | P0 缺口/设计判断 |
|---|---|---|
| 本地卡类型 codec | `csms/app/services/payment_method_codec.py` 用 `v1:<brand>:<payment_type>` 复用 `payment_method_brand` 列；当前只接受信用卡/借记卡，旧纯品牌值投影为 `null` | P0-1 只扩展受支持集合到三类；旧值不回写、不猜测、不迁移 |
| Checkout confirm | `csms/app/api/v1/app/payment_checkout.py` 的 `payment_type_id` Literal 只有两类；`CheckoutSessionService.confirm` 对 `save_card` 新卡跳过了非空类型校验 | P0-1 统一新卡校验：`save_card` 与 `charging_direct` 均要求本次识别出的 `payment_method_id`/`payment_type_id`；saved-card 必须不接收客户端卡事实 |
| Provider Card 投影 | `MercadoPagoProvider.create_card` 在类型缺失时接受请求 hint，并只允许两类；`MercadoPagoService.create_card` 透传 Provider Card 的 brand/type | P0-1 由 Provider 响应提供权威类型；缺失/未知失败，绝不默认信用卡；hint 只能作为受信任的请求上下文，不能把未知响应提升为已识别 |
| 保存卡服务/API | `PaymentMethodService` 已有 Customer/Card、用户过滤、默认卡和删除幂等；canonical API 已返回 `payment_type`，旧兼容路由复用投影 | 仅替换 codec/Provider 校验和测试；不改表结构、不放宽跨用户查询 |
| Hosted 页面 | `payment_checkout/hosted_page.py` 已使用 MercadoPago.js Secure Fields、CSP 和 303；当前证件类型隐藏并固定 `CC`，直接支付类型默认 `credit_card`，页面含英文和内部 purpose | P0-2 将证件类型作为 Provider 动态能力、卡类型作为只读 capability 状态，并在页面层失败关闭 |
| Hosted 页面错误 | `get_hosted_page` 对所有非 `created` 状态抛 `CHECKOUT_ALREADY_CONFIRMED`；路由错误统一返回 JSON | P0-2 为 GET HTML 增加独立 404/409/503 西语状态页；confirm 仍保持冻结 JSON envelope |
| Token/事实边界 | Card Token 由 `CheckoutSessionStore` 加密并原子消费；direct-card Intent 保存非敏感 hint，BE-6 在最终 Invoice 后消费 Token | P0-2 不把证件资料、PAN、CVV 或 Token 放入页面初始化数据、Redis state、DB、Deep Link 或日志 |
| Merchant/租户 | C1 `MerchantAccountResolver` 已返回 `platform:eslatin`；Checkout、Intent、PaymentOrder 已保存安全 snapshot | P0 复用现有 resolver；页面能力调用不改变商户上下文，Provider 创建/保存卡仍在 server-side MerchantContext 边界内 |
| 配置/开关 | Checkout TTL、签名、public key、Token 加密 key、return URL/next-action allowlist 已有；`PAYMENT_RAILS_ENABLED` 仍关闭 | P0 不新增生产开关、不改真实密钥、不提前打开支付轨 |

## P0-1 架构边界：卡类型与 Provider 投影

调用链固定为：

```text
Hosted BIN/Provider capability
        -> frozen confirm hints
        -> CheckoutSessionService canonical validation
        -> encrypted Redis confirmation state
        -> PaymentMethodService / PaymentReconciliationService
        -> MercadoPagoProvider
        -> ProviderCardResult / PaymentOrder provider_hints
        -> codec/API projection
```

职责划分：

- `payment_method_codec` 是唯一的本地 brand/type 编码与兼容读取入口。任何 API、Hosted 页面、保存卡支付和补缴 hint 不得自行拆 `v1:` 字符串。
- `CheckoutSessionService` 只做冻结契约的语法/状态校验：new-card 要求非空 `payment_method_id` 和三类之一的 `payment_type_id`；saved-card 的三项卡事实必须为空并由当前用户的本地投影解析。
- `MercadoPagoProvider` 将 Provider Card 响应 canonicalize；`payment_type` 缺失、未知或与受支持集合不一致时抛安全 Provider 错误。不能使用 `credit_card` 作为缺省值。
- `PaymentMethodService` 只保存已 canonicalize 的 brand/type；旧记录继续返回 `payment_type=null`。保存卡、默认卡、删除卡的用户隔离和事务边界保持不变。
- `PaymentReconciliationService` 使用同一 codec 生成 saved-card provider hints；缺少类型时不发送猜测值，支付创建失败关闭并保留原有未支付事实。

这一边界使 BE-P0-1 可独立验收：只要用 fake Provider 返回三类、未知、缺失和旧记录，就能验证 codec、confirm、Provider Card、API projection 和下游 hint，不需要真实 HTML 或数据库迁移。

## P0-2 架构边界：托管页与会话恢复

托管页仍是后端生成 HTML、浏览器直接加载 MercadoPago.js 的边界，App/API 不接收原始卡字段。页面分为两种模式：

- `new_card`：Secure Fields 持有卡号、有效期和 CVV；页面调用 Provider 的 identification-types 能力动态生成证件类型，调用 BIN 能力得到品牌、issuer 和三类 `payment_type_id` 的只读 capability；全部 capability 未 ready 前不可确认。
- `saved_card`：只从服务端重新读取当前用户的 Card ID 和本地 canonical projection，展示品牌、类型、尾号，Secure Fields 只挂载 CVV；不渲染卡号、有效期、姓名或证件字段。

页面状态与 HTTP 语义分离：

| 服务端事实 | GET HTML | 页面内容 |
|---|---:|---|
| 签名无效、Redis 缺失、TTL 过期、状态为 `expired` | 404 | 西语“会话已过期或不可用”全页；不创建卡字段；只提供 allowlist 内返回/重新开始动作 |
| 已确认或已进入结果状态（`ready`、`processing`、`action_required`、`approved`、`declined`、`error`） | 409 | 西语“该操作已提交/请返回 App 查询结果”全页；不允许重复提交 |
| Redis/配置/Provider capability 暂时不可用 | 503 | 西语暂不可用全页；不声称成功或失败；提供安全重试/返回 |
| `created` 且依赖能力可用 | 200 | 渲染对应模式的 Secure Fields |

confirm 仍使用冻结的 JSON 错误 envelope，成功仍只 303 到 allowlist Deep Link；Deep Link 只带 `checkout_session_id` 和安全状态。

官方 Mercado Pago Colombia 文档提供 `getIdentificationTypes` 用于动态证件类型、`getPaymentMethods`/BIN 能力用于卡能力查询；实现应通过一个页面内的 capability adapter 隔离 SDK 版本差异，并以 sandbox 真实返回为准。若 Provider 返回缺少或冲突的类型，页面必须显示可行动的西语错误并保持确认禁用，而不是猜测。

## 数据、租户与安全审查

- 不新增列、索引、迁移或历史导入。P0-1 继续把新 projection 写入现有 64 字符 `payment_method_brand`，P0-2 继续把短期状态写入加密 Redis。
- `operator_tenant_id`、ChargePoint、connector、Invoice、Session 和 MerchantContext 均由服务端已有链路推导；客户端的卡 hint 不能覆盖租户、金额、支付对象或商户。
- Redis 中只能有加密 Card Token；Checkout state 只允许非敏感 `provider_hints`、结果引用和安全 snapshot。证件 type/number 只存在托管页面内存并直接进入 MercadoPago.js tokenization。
- 日志只记录 checkout/PaymentOrder/Invoice/Session 引用、merchant account ref、安全错误码和状态；不记录 `card_token`、证件资料、PAN、CVV、credential handle、完整 Provider response 或原始错误。
- 页面 CSP、`no-store`、`frame-ancestors`、HTTPS Provider allowlist、Deep Link allowlist 和 next-action allowlist 沿用现有基础设施；P0 不以放宽 CSP 解决 SDK 问题。

## 测试架构与可行性

BE-P0-1 的独立测试入口：

- `csms/tests/test_payment_methods.py`：三类 Provider Card、codec v1、旧值、未知/缺失类型、保存卡 projection、用户隔离。
- `csms/tests/test_checkout_session_api.py`：三类 confirm、new-card 空 hint 拒绝、saved-card 客户端覆盖拒绝、敏感字段不进入 Redis/redirect。
- `csms/tests/test_payment_reconciliation_be6.py` 和 `test_payment_refunds_be7.py`：saved-card/PaymentOrder hint 不猜测、不回退，既有 direct-card 回归。

BE-P0-2 的独立测试入口：

- `csms/tests/test_checkout_session_api.py`：动态证件类型 DOM/调用、三类 BIN projection、无 BIN/未知/能力失败禁用确认、saved-card 只挂 CVV、全西语/无 purpose/无英文内部值、窄屏 CSS、GET 404/409/503 HTML 状态页、重复 confirm。
- 新增的 Hosted renderer/service 单元测试可用浏览器无关的 HTML contract assertions；不把真实 Provider 网络调用放入单元测试。
- 真实 sandbox/Redis/PostgreSQL/隐私和视觉可访问性验证仍属于恢复后的 backend QA，不得把开发测试当 QA 通过。

## 可实施性裁决与门禁

- `BE-P0-1`：技术上可实施，与冻结契约兼容，状态为 `ready-for-dev`。
- `BE-P0-2`：Hosted 页面、动态 capability、卡类型展示、saved-card CVV、单用途 Token 校验和错误状态页技术上可实施；仅因共享后端文件和 canonical card capability 依赖，状态为 `blocked-by-BE-P0-1`。
- 本架构评估和配套技术设计已批准。`PAYMENT_RAILS_ENABLED` 保持 `false`，后端 QA 暂停事实继续有效；设计批准不等于 QA、生产支付启用或生产部署批准。

参考：Mercado Pago Colombia 的[证件类型 API](https://www.mercadopago.com.co/developers/es/reference/online-payments/checkout-api/identification-types/get)和[卡片集成文档](https://www.mercadopago.com.co/developers/es/docs/checkout-api-payments/integration-configuration/card/integration-via-cardform)。
