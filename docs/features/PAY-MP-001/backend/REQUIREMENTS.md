---
id: PAY-MP-001
status: approved
owner: product
audience: backend
---

# 后端专用产品需求

## 后端责任

- 通过 `MerchantAccountResolver` 根据服务端推导的运营租户和支付目的解析 MerchantContext；C1 返回平台商户，支付服务不得直接假设唯一全局商户。
- 实现 Mercado Pago Customers/Cards、Checkout Session、Charging Payment Intent、最终金额支付、Webhook 和退款的服务端能力；保留 D1 欠费事实门禁及已有欠费补缴服务能力，但本期不交付 App 欠费列表/补缴 UI。
- 把钱包、直接银行卡和免费会话拆成明确结算分支；只有真实入账完成后才能把收费 Invoice/Session 标记为 paid。
- 保证订单、Invoice、Payment、PaymentOrder、ChargingSession、用户、租户和商户上下文可追踪且一致。
- P0 托管页负责首次新卡证件类型/号码、BIN 自动卡识别、全西语紧凑表单和失效会话恢复；托管 HTML 属于后端交付边界，React Native 不接触卡片或证件原始数据。
- 将 Provider 卡类型端到端扩展为 `credit_card | debit_card | prepaid_card`，包括 confirm 校验、保存卡 Provider 结果、本地兼容 codec、API 投影和支付提示；不新增数据库迁移。

## 后端业务不变量

- AppUser 来自认证上下文；`tenant_id`、ChargePoint、connector、Session、Invoice、MerchantContext 和金额均由服务端解析。
- 直接充电的最终 PaymentOrder 只能在会话结束且 Invoice 金额确定后创建，金额必须等于 Invoice。
- 一个 Charging Payment Intent 最多绑定一个 ChargingSession；一个 Invoice 最多成功入账一次。
- 所有 Provider 创建、Webhook、退款和补缴支持幂等和并发竞争。
- 金额使用 Decimal，时间保存 UTC，支付状态通过明确状态机推进。
- PAN、有效期、CVV、明文 Card Token、Access Token 和 Refresh Token不得进入数据库、日志或审计。
- 生产 Redis 只暂存加密单次 Card Token；消费后删除，丢失或过期时失败关闭并形成欠费。
- C1 的 Provider 凭证只从服务端密钥解析；订单仅保存非敏感 `merchant_account_ref=platform:eslatin`。
- 付费充电 Invoice 的 `total_amount` 必须至少为 `1011.00 COP`；免费定价模式保持 `0.00 COP`。Wallet、direct card、欠费补缴和退款均以该 Invoice 权威金额为准，不得把低于最低金额的原始计费结果直接发送给 Provider。
- 新卡的姓名、证件类型和证件号码只由托管页交给 MercadoPago.js；confirm schema、Redis Session、数据库、日志和审计不得接收或保存证件资料。
- 新卡 `payment_method_id` 与 `payment_type_id` 必须来自 BIN/Provider 自动识别；空值、未知类型和识别失败均失败关闭，不得默认 `credit_card`、Visa 或任意发卡方。
- 已保存卡 confirm 只接收本次 CVV 生成的 Card Token；品牌、类型、尾号和 Provider Card ID 从当前用户服务端投影解析，客户端不能覆盖。
- Checkout purpose 与保存行为必须失败关闭：仅 `purpose=save_card + payment_method_mode=new_card` 接受 `save_card=true`；其他 purpose 和所有 saved-card 模式只接受 `false`。`charging_direct` Token 只服务当前充电最终扣款，不得调用 Customers/Cards。

## 接口与状态

- 完整字段、错误和状态以 `contracts/API.md` 为唯一契约。
- App 支付创建和结果查询只使用 Checkout Session；Provider Webhook 通过独立 Provider-specific 路由进入统一 reconciliation。历史支付创建/状态/Webhook 路径不注册为当前 App API。
- `action_required`、`processing`、`approved`、`declined`、`expired`、`error` 和 `refunded` 必须稳定映射。

## 数据和异步链路

- 复用 `Order.pre_authorization` 保存非敏感支付意图摘要，`Order.session_id` 关联 OCPP 会话。
- 复用 `PaymentOrder.order_metadata`（数据库列名 `metadata`）保存 purpose、settlement method、Invoice/Session、operator tenant 和 merchant snapshot。
- 复用 `AppUserPaymentMethod` 作为 Mercado Pago Customer/Card 本地投影。
- RemoteStart 失败时 Intent 可安全重试；StartTransaction 后立即消费并绑定 Intent。
- Webhook 必须验签、按正确 MerchantContext 主动反查，并校验金额、币种、external reference 与业务归属。
- App 关闭不影响异步收敛；后台对账能恢复 processing/action-required 订单。

## 结算与退款

- Wallet：余额足够才原子扣款并标记 paid；不足时不能截断余额后伪装完整支付。
- Direct card：Invoice pending → PaymentOrder → Provider → approved 后再 paid，不写钱包流水。
- Free：`0 COP` 审计，不创建 Provider PaymentOrder 和钱包流水。
- 直接支付退款原路退回；累计部分退款不得超过已付金额。
- 钱包充值退款前锁定用户余额；可用余额不足时拒绝自动退款并进入人工处理。

## 后端验收重点

- Merchant Resolver 可替换契约、租户隔离、敏感日志、金额一致、状态机、并发幂等、Redis Token 失败关闭、退款和脏数据检查。

## P0 托管页与卡类型要求

- 新卡页面动态读取 Mercado Pago Colombia 的可用证件类型；加载失败时禁止确认并显示西班牙语安全错误，不硬编码或隐藏 `CC`。
- BIN 变化时自动解析并只读显示卡品牌、信用/借记/预付类型和可用发卡方；清空或更换卡号必须清除旧识别结果。
- 支持 `prepaid_card` 通过 confirm、Provider Card 创建、codec 和 payment-method projection；未知旧 codec 仍安全投影为 `null`。
- 托管页所有用户文本为西班牙语，Secure Fields 高度紧凑且移动端响应式；不显示 `charging_direct` 等内部 purpose、Provider 原始错误、调试值或手工卡种/分期控件。
- `save_card`、`charging_direct`、`wallet_top_up` 使用各自准确 CTA 和说明；`charging_direct` 只说明充电结束后按实际账单扣款，不出现预授权/冻结/预扣表述。
- 单次新卡不是“默认不保存”而是固定不保存：`charging_direct`、`wallet_top_up` 和 `unpaid_charge` 必须 `save_card=false`，托管页不显示保存选择；显式添加卡必须创建独立 `purpose=save_card` Checkout 并固定 `save_card=true`。
- 会话 404/过期、409 已确认和 503 暂不可用返回 HTML 安全状态页，不渲染可提交卡表单；confirm JSON 保持统一错误 envelope。
- 不新增数据库迁移，不导入或重写历史支付方式；现有纯 brand/未知类型记录继续兼容读取。

## 欠费范围调整

- D1 仍是本期服务端必须保留的风控门禁：任意未结清事实都可以阻止新的充电启动，并返回冻结的 `UNPAID_CHARGES` 错误。
- 欠费列表查询字段、银行卡/钱包补缴 App 体验和欠费恢复页标记为 `deferred-by-owner`，后续另立需求补充契约和产品流程。
- BE-7 已完成的服务端实现事实不回退、不删除；本范围调整只改变本期产品交付边界，不引入迁移或历史数据处理。

## 后端非范围

- App/Admin 页面、导航、组件、客户端状态和本地化。
- C2 OAuth/Split Payments 的真实接入和数据库凭证模型。
- 新数据库迁移和历史支付导入。
- 本期 App 欠费列表、银行卡/钱包欠费补缴 UI 和欠费恢复页；后续需求再定义其查询契约与用户体验。
- 保存证件资料、证件照片上传、EsLatin 身份认证、卡类型手工选择、分期、信用卡预授权或冻结额度。
