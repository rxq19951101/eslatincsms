# CHG-20260817-PAY-API-GOVERNANCE

Status: implementation-ready
Requested by: Product Owner
Date: 2026-08-17
Coupling Level: C2

## Requested Change

统一 App 当前支付接口，当前产品只实现 Mercado Pago；同时保留服务端 Provider 适配边界，使未来接入其他支付方式时不新增 `/create-<provider>` 业务接口。

## Product Decision

1. App 的支付创建、托管页、确认和结果查询统一使用 Checkout Session 契约。
2. 当前产品文档和可用 Provider 只有 Mercado Pago。
3. Vendor、tenant、merchant、Access Token 和 Provider 选择不由客户端提交；当前 C1 由服务端解析为 EsLatin 平台收款主体。
4. 未来 Provider 通过服务端 Provider Registry/Adapter、Credential Resolver 和 Provider Webhook Adapter 接入，不改变 App Checkout Session 契约。
5. 历史 `/wallet/payments/*` 业务入口不承担兼容义务，不再注册为当前 App API；无迁移、无历史支付数据导入。

## Current Architecture

- `payment_checkout` router 提供 Checkout Session 创建、托管页、确认和查询。
- `payments` 模块混合了历史 Wompi、旧 Mercado Pago 创建/状态接口以及 Webhook。
- App 同时存在 Checkout Session 调用和旧钱包/Provider 创建调用。
- Provider Registry、MerchantContext 和 Mercado Pago Adapter 已存在，但公共 App 接口尚未完全收敛。

## Affected Product Domains

- App 支付方式、钱包充值、直接充电支付、绑卡。
- Mercado Pago Webhook 和支付状态回写。
- 未来 Provider 扩展边界。

## Affected Technical Components

- Backend route registration, payment webhook router, tenant middleware allowlist.
- App payment API, wallet top-up delegation, payment result recovery, navigation/provider options.
- Product/technical architecture, frozen API contract, test fixtures and environment documentation.

## Contract Decision

### Public App payment contract

- `POST /api/v1/app/payments/checkout-sessions`
- `GET /api/v1/app/payments/checkout-sessions/{checkout_session_id}`
- `GET /api/v1/app/payments/checkout/{signed_token}`
- `POST /api/v1/app/payments/checkout/{signed_token}/confirm`
- `GET/PATCH/DELETE /api/v1/app/payment-methods...`

业务目的由 `purpose` 表达：`save_card`、`wallet_top_up`、`charging_direct`、`unpaid_charge`。App 不提交 `provider`、收款方、佣金或凭证。

### Provider webhook contract

Provider 回调不是 App 业务支付创建接口，统一放在独立适配边界：

- `POST /api/v1/app/payments/webhooks/mercadopago`
- `POST /api/v1/app/payments/webhooks/sim`（仅 development/test）

每个 Provider 的验签、主动反查、字段映射和幂等处理只能存在于对应 Adapter/Webhook Adapter；内部结果必须进入同一支付状态机。

### Removed from active API

以下历史入口不再注册为当前 App API：

- `/api/v1/app/wallet/payments/create`
- `/api/v1/app/wallet/payments/create-mp`
- `/api/v1/app/wallet/payments/{order_id}/status`
- `/api/v1/app/wallet/payments/webhook`
- `/api/v1/app/wallet/payments/webhook-mp`
- `/api/v1/app/wallet/payments/sim-webhook`

钱包余额、交易记录和欠费事实读取仍属于独立领域；欠费补缴 UI 仍按产品文档延期，不作为本次统一支付入口的理由新增接口。

## Future Provider Extension Rules

新增 Provider 必须：

1. 实现统一 Provider Adapter/Registry 能力接口。
2. 通过 Credential Resolver 取得服务端密钥，不接收客户端凭证。
3. 增加 Provider-specific Webhook Adapter，并映射到统一 PaymentOrder/Checkout 状态机。
4. 增加独立的 Provider contract tests、签名/幂等/金额币种校验和回归证据。
5. 不新增 `/create-<provider>`、`/pay-<provider>`、`provider` 客户端参数或第二套 App Checkout 响应。

## Data Model Impact

无数据库迁移。复用现有 CheckoutSession、PaymentOrder、MerchantContext 和 Provider Registry 数据/服务边界。

## Backward Compatibility

历史接口兼容不在本产品范围；旧入口移出当前路由注册。测试和文档同步切换到新 canonical path。已有数据库记录不迁移、不清理。

## Security and Tenant Impact

- Webhook 继续使用独立免租户解析白名单和 Provider 验签；旧路径从白名单移除。
- App 只发送业务目的和业务对象，不发送 tenant/merchant/provider/token。
- Provider Access Token 只由服务端 Credential Resolver 解析。

## Implementation Sequence

1. 更新产品、技术和 API 契约治理规则。
2. 将历史支付模块拆为未注册 legacy router 与 canonical Provider webhook router。
3. 将 App wallet top-up、支付结果和支付方式读取改为 canonical API。
4. 移除 Wompi/旧 Provider 业务入口在导航和 Provider 选项中的使用。
5. 更新 webhook allowlist、环境示例和测试请求路径。
6. 运行后端支付回归、OpenAPI 路由清单和 App TypeScript/Jest 检查。

## Rollback Strategy

代码回滚需恢复本 Change 的路由注册、前端调用和文档；不执行数据库回滚，不修改生产配置。

## Acceptance Criteria

- OpenAPI 中 App 支付创建/查询只有 Checkout Session；不存在旧 `create`/`create-mp`/旧 status 路由。
- App 业务代码不调用旧钱包支付创建、旧状态或 Wompi 页面。
- Mercado Pago 和 SIM Webhook 使用新的 provider-specific canonical path。
- Provider 选择只存在服务端 Adapter/Registry 内部。
- 后端回归测试、路由清单和 App 类型/单元检查通过。
