---
id: PAY-MP-001
status: approved
owner: product
---

# Mercado Pago 单次充电、绑卡与平台收款

## 已确认决策

- `A1`：收费充电结束后按实际账单金额扣款，不把单次消费转成钱包充值。
- `B1`：App 打开 EsLatin 托管的 Mercado Pago 安全结账页；卡号、有效期和 CVV 由 MercadoPago.js 安全字段采集。
- `C1`：首期所有款项进入 EsLatin 的 Mercado Pago 商户账户。
- `D1`：任意未结清收费账单立即阻止用户开始下一次收费充电。
- `D-027`：付费充电每个会话最终至少支付 `1,011 COP`；免费定价模式仍为 `0 COP`，最低金额规则写入用户协议。
- 首次使用新卡时，托管页按 Mercado Pago Colombia 的要求采集证件类型与证件号码；证件资料只进入 MercadoPago.js Token 化调用，不进入 EsLatin API 或持久化。
- 卡品牌、发卡方以及信用卡、借记卡、预付卡类型由 Provider 自动识别并只读展示，用户不手工选择。
- 单次新卡消费始终不保存：`charging_direct` 的一次性 Card Token 只用于当前充电最终扣款，固定 `save_card=false`，页面和 App 均不提供“同时保存”选项。保存卡必须使用独立 `purpose=save_card` Checkout；保存后再次支付只重新采集 CVV，不重复要求证件信息，Provider 额外验证除外。
- 托管页 P0 全部使用西班牙语和紧凑移动端布局，不展示内部 purpose；过期或无效会话不再渲染卡表单。
- P0 没有实现预授权、冻结或预扣，所有文案只说明充电结束后按实际账单金额扣款。
- C1 的实现必须通过商户账户解析接口获得收款上下文，不得在订单、计费或 Webhook 中写死全局商户；后续 C2 可按租户解析 OAuth 商户账户和 Split Payments。

## 当前问题

- App 当前主要围绕钱包充值设计，收费充电结算会直接扣钱包并把账单标记为已支付。
- 现有 Mercado Pago 页面自行收集卡片字段并直接创建 Card Token，不符合首期采用托管安全字段的决定。
- 已保存支付方式只有列表占位和本地演示数据，尚未接入 Mercado Pago Customers/Cards。
- 现有充电结算在余额不足时会把余额扣到零但仍把账单标记为已支付，不能支持真实直接支付和欠费账务。
- 现有充值退款可能在余额已经消费后形成负钱包余额。
- 支付订单当前缺少稳定的收款主体上下文，直接写成 C1 会增加未来 C2 改造范围。
- 当前托管页把证件类型隐藏并固定为 `CC`，无法覆盖 Provider 动态返回的证件类型。
- 当前新卡识别仅接受信用卡/借记卡，并在 BIN 为空或识别失败时默认成信用卡，可能产生错误的 Provider 参数；预付卡被错误排除。
- 当前 Secure Fields 容器高度没有收敛，页面字段异常放大；页面中存在英语标签和内部 `charging_direct` 技术值。
- 当前失效 URL 返回通用 `Checkout session not found`，用户仍可能看到或尝试操作卡表单，缺少返回和重新创建动作。

## 目标

- 同时支持钱包充值、钱包支付、银行卡单次直接支付和已保存银行卡直接支付。
- 支持 Mercado Pago 返回的信用卡、借记卡和预付卡；品牌、类型和发卡方以 Provider 实时识别结果为准，不能由用户选择或由客户端猜测。
- 单次直接支付在充电结束并生成最终账单后，按准确 COP 金额扣款，不增加或减少钱包余额。
- 支持显式绑卡、卡片列表、默认卡、删除卡以及用已保存卡支付。
- 已保存卡每次付款重新采集 CVV；不承诺无感代扣。
- 支持 3DS、处理中、拒绝、超时、全额/部分退款和 Webhook 重放；欠费补缴服务能力保留，但本期 App 欠费列表与补缴体验延期。
- 保持用户、订单、充电会话、租户和收款主体之间的可审计关系。
- C1 首期不新增数据库迁移，并为 C2 商户 OAuth/Split Payments 保留稳定扩展边界。

## 术语和分层

- `settlement_method`：`wallet` 或 `direct_card`。
- `payment_purpose`：`save_card`、`wallet_top_up`、`charging_direct` 或 `unpaid_charge`。
- `Payment Checkout Session`：短期安全结账会话，只负责托管页面、Card Token 和结果回跳。
- `Charging Payment Intent`：收费充电启动前的支付意图；对外使用不可猜测 ID，对内复用现有业务 `Order`。
- `PaymentOrder`：金额已经确定后创建的支付订单。`charging_direct` 不得在最终账单生成前创建金额订单。
- `merchant_account_ref`：非敏感商户引用。首期为平台商户；后续可解析为租户商户。
- `MerchantAccountResolver`：服务端根据受信任的 `tenant_id` 和业务目的解析收款上下文的接口。

## 产品流程

### 添加银行卡

1. 用户进入“我的 → 支付方式 → 添加银行卡”。
2. App 请求 `save_card` 类型的安全结账会话并打开 HTTPS 结账页。
3. 结账页动态加载 Provider 支持的证件类型，用户填写持卡人姓名、证件类型和号码；卡品牌、发卡方及信用/借记/预付类型由 BIN 自动识别并只读展示。
4. 结账页通过 MercadoPago.js 安全字段生成一次性 Card Token；EsLatin App 和 API 不接收原始 PAN、有效期、CVV、证件类型或证件号码。
5. 后端创建或复用该 AppUser 对应的 Mercado Pago Customer，并关联卡片。
6. 本地只保存 Provider、Customer ID、Card ID、品牌、信用/借记/预付类型、后四位和默认标记。
7. 首张卡自动成为默认卡；后续卡只有用户显式操作才切换默认卡。
8. 用户可删除卡；删除必须同时调用 Mercado Pago 并在成功或已不存在时更新本地投影。
9. 只有该独立流程可以把新卡关联到 Mercado Pago Customer；充值、直接充电和欠费支付不得在同一次 Checkout 中附带保存卡。

### 新卡单次直接充电

1. 用户扫码后查看站点、枪口、计价规则和“实际金额将在充电结束后扣取”的提示。
2. 用户选择“本次使用新卡”；该卡固定仅用于当前充电，App 和托管页不显示保存卡开关。若用户希望以后复用，必须先从“我的 → 支付方式 → 添加银行卡”完成独立 `save_card` Checkout，再回到充电流程选择已保存卡。
3. App 打开 `charging_direct` 安全结账页；页面采集首次新卡的持卡人和证件资料，自动识别卡品牌/类型并生成一次性 Card Token。页面 CTA 使用“验证银行卡并继续”，不得描述为预授权或已经扣款。
4. 后端创建 Charging Payment Intent，服务端绑定 AppUser、租户、充电桩、枪口、价格快照来源和 `merchant_account_ref`。
5. 加密 Token 只保存到 Redis 并设置 TTL；数据库只保存非敏感意图摘要和 Redis 引用。
6. App 携带 Payment Intent 启动充电；后端再次校验用户、设备、租户、枪口、有效期和未消费状态后才下发 RemoteStart。
7. OCPP StartTransaction 创建会话后，将业务 Order 与 ChargingSession 关联并把意图标记为已消费/进行中。
8. 充电结束后按价格快照创建待支付 Invoice；付费模式最终金额为计费结果与 `1,011 COP` 中较高者，免费模式保持 `0 COP`。PaymentOrder 使用该 Invoice 金额，再用一次性 Token 发起 Mercado Pago 支付。
9. 支付批准后 Invoice、Payment 和 ChargingSession 变为已支付；直接支付不得产生钱包余额流水。

### 已保存卡直接充电

- 用户选择已保存卡后仍须在安全结账页输入 CVV。
- 页面展示卡品牌、信用/借记/预付类型和后四位；不再次采集持卡人姓名或证件信息，除非 Mercado Pago 返回额外验证要求。
- 安全页使用 Mercado Pago Card ID 与 CVV 生成新的单次 Token，后续流程与新卡单次充电一致。
- 绑卡不代表授权 EsLatin 在没有本次 CVV/Token 的情况下静默扣款。

### 托管安全页体验

- P0 页面语言固定为西班牙语（`es-CO`），不得混用英语标签、Provider 原始英文错误或内部业务代码。
- 新卡字段顺序为：卡号、只读卡品牌/类型、有效期、CVV、持卡人姓名、证件类型、证件号码；证件类型由 Mercado Pago 动态能力返回，不硬编码 `CC`。
- 卡号、有效期和 CVV Secure Fields 使用紧凑、可点击、移动端可读的高度；双列在窄屏自动改为单列。
- 页面不提供 Visa/Mastercard、信用/借记/预付或发卡银行的手工选择，也不展示分期选择。
- BIN 为空、识别失败、Provider 返回不支持类型或证件类型加载失败时，页面显示西班牙语可行动错误并禁止确认，不得回退为信用卡。
- `save_card` 的按钮为“Guardar tarjeta”；`charging_direct` 为“Validar tarjeta y continuar”；金额确定型支付才可以显示实际金额和“Pagar”。
- 页面说明卡数据直接发送给 Mercado Pago，并说明证件资料用途；不得宣称 EsLatin 对银行卡进行了扣款、冻结或预授权。
- 会话过期/缺失、已确认或服务暂不可用时，返回独立全页状态，禁用或不渲染卡表单，并提供安全返回 App/上一页或重新开始动作。

### 钱包充值与钱包支付

- 钱包充值继续创建金额确定的 PaymentOrder；只有 Mercado Pago 反查或可信 Webhook 确认批准后才增加余额。
- 钱包支付继续在充电结束后扣余额，但余额不足时不得把 Invoice 标记为已支付。
- 免费充电生成 `0 COP` Invoice/Payment 审计，不要求支付意图，也不产生钱包流水。

### 支付结果和 3DS

- `approved`：显示成功和账单明细。
- `processing`：显示处理中；App 轮询订单状态，Webhook 负责最终收敛。
- `action_required`：打开 Mercado Pago 返回的受信任 3DS URL；用户完成后继续等待 Webhook。
- `declined/error/expired`：账单进入未支付；本期 App 不提供欠费补缴 UI，后续任务再提供新卡、已保存卡或钱包补缴体验。
- 用户关闭 App 不取消支付；重新进入后从服务端恢复订单状态。

### 欠费和 D1 门禁

- 任何租户下存在当前用户未结清的收费 Invoice/ChargingSession 时，所有新的收费充电启动返回 `UNPAID_CHARGES`。
- 免费充电不受余额门禁影响，但首期同样受欠费门禁约束，避免利用免费场景绕过账户风控。
- 本期 App 遇到 `UNPAID_CHARGES` 时只显示安全、可本地化的“存在未结清账单，暂不能继续充电”提示，并阻止继续启动；不得显示未冻结的欠费字段，不得伪造已支付或通过 UI 乐观解除门禁。
- 欠费列表、银行卡/钱包欠费补缴、欠费恢复页以及对应展示字段和失败原因属于后续边缘场景，标记为 `deferred-by-owner`，不阻塞本期 Mercado Pago 主流程。
- 后续任务需补充并冻结欠费列表契约，再决定列表字段、支付重试和恢复体验；后端已完成的 D1 事实门禁及相关服务端能力继续保留。

### 退款

- 直接充电支付退款原路退回银行卡；不修改钱包余额。
- 直接支付支持全额和部分退款，累计退款不得超过已支付金额。
- 钱包充值只有可用余额不低于退款金额时才允许自动原路退款；否则进入人工审核，不允许把钱包扣成负数。
- Webhook 重放、管理员重复点击和 Provider 重试不得重复记账或重复退款。

## C1 到 C2 的扩展边界

- App 和公共 API 只表达支付目的、用户选择的支付方式和充电对象，不接受客户端提供 `tenant_id`、商户账号、Access Token 或佣金。
- 服务端从 QR/ChargePoint/ChargingSession 推导 `tenant_id`，再调用 `MerchantAccountResolver.resolve(tenant_id, purpose)`。
- C1 Resolver 固定返回 `merchant_mode=platform`、`merchant_account_ref=platform:eslatin`，真实 Access Token 仅来自服务端环境密钥。
- Order、PaymentOrder、Webhook 审计和退款上下文都保存 `merchant_mode`、`merchant_account_ref`、`operator_tenant_id` 和支付目的的非敏感快照。
- Provider 服务只接收解析后的 `MerchantContext`，不得直接读取唯一全局 Mercado Pago Token。
- C2 将新增 `merchant_mode=marketplace` Resolver、租户 OAuth/KYC 状态、加密凭证存储、Token 刷新和 `application_fee`；App 支付流程和 Payment Intent 契约保持不变。
- 首期不得在 JSON、日志或审计事件中保存 Mercado Pago Access Token、Refresh Token、原始卡数据或明文 Card Token。

## 数据和兼容策略

- 本需求不新增数据库迁移。
- 复用现有 `orders.pre_authorization` 保存非敏感支付意图摘要、`merchant_account_ref`、Redis 引用和生命周期状态。
- 复用 `orders.session_id` 将启动意图与实际 OCPP 会话关联。
- 复用 `payment_orders.metadata` 保存 `payment_purpose`、`settlement_method`、Invoice/Session、租户和商户快照。
- 复用 `app_user_payment_methods` 保存 Mercado Pago Customer/Card 投影。
- 一次性 Card Token 使用独立加密密钥加密后暂存生产 Redis，TTL 不超过 Token 的 Provider 有效期；消费后立即删除。
- 一个 Provider 一次性 Card Token 只承担一个业务用途：`save_card` Token 只用于 Customers/Cards 关联，`charging_direct` Token 只用于当前充电结束后的最终扣款；不得双重消费、复制复用或静默改变用途。
- Redis Token 丢失、过期或解密失败时必须失败关闭：不伪造已支付，结束后的账单进入欠费并由 D1 门禁阻止后续充电；补缴入口属于后续任务。
- App 当前只允许使用安全 Checkout Session；`/wallet/payments/create-mp` 等历史 Provider 创建接口不属于当前产品 API，也不承担兼容义务。未来 Provider 必须复用 Checkout Session，不得新增 Provider 专属 App 创建接口。

## 安全和审计

- 原始 PAN、有效期和 CVV 不得进入 React Native 状态、EsLatin API 请求、日志、数据库或错误追踪。
- Card Token、3DS URL、Provider ID 和幂等键按敏感等级脱敏记录。
- 证件类型与证件号码只存在于托管页内存并直接传给 MercadoPago.js；不进入 EsLatin confirm 请求、Redis、数据库、日志、分析、审计或错误追踪。
- Webhook 必须验签，并使用对应 MerchantContext 主动反查 Provider 状态、金额、币种和 external reference。
- 订单创建、支付批准、拒绝、欠费、退款、绑卡、删卡和默认卡变更必须记录审计事件。
- 所有读写按当前 AppUser 和服务端推导租户隔离；支付方式 ID 不可跨用户使用。
- 金额使用 Decimal/十进制字符串，时间保存 UTC。

## 非范围

- 本期不实现 C2 租户 OAuth、Split Payments 或平台抽佣，只保留扩展接口。
- 不实现 PSE、Nequi、Mercado Pago 余额、现金或分期优惠；本 P0 固定一次付款。
- 不实现开始前固定额度扣款、信用卡预授权或差额退款模式。
- 不提供卡品牌、信用/借记/预付类型或发卡银行的手工选择。
- 不实现无 CVV 静默代扣、订阅、自动续费或车队月结。
- 本期不交付 App 欠费列表、银行卡/钱包欠费支付 UI、欠费恢复页或未冻结 `UnpaidCharge` 字段映射；后续另立需求补充契约、查询和补缴体验。
- 不修改或导入历史支付数据，不新增数据库迁移，不部署生产环境。

## 生产发布分级与最低门禁

- 生产上线最低要求见 [PRODUCTION_LAUNCH_MINIMUM.md](./PRODUCTION_LAUNCH_MINIMUM.md)，竞品官方事实和产品推导见 [COMPETITOR_BENCHMARK.md](./COMPETITOR_BENCHMARK.md)。
- “功能开发完成”“开发测试通过”和“生产可发布”是三个不同状态；只有独立 QA、E2E、Provider、运营、对账、法律/隐私/财税和人工审查证据完整后，才允许判定相应发布等级为 GO。
- 首次真实上线建议按四段推进：先通过不产生真实扣款的预金丝雀门禁；再由负责人一次性批准一名内部测试人员、一个窗口和最多一个低额生产 Payment ID；关闭支付轨后完成该笔三方对账及 Mercado Pago 生产质量评估；证据通过后才另行审批受控试点扩展。公开发布再单独审批。该建议为 D-020/D-021 `proposed`，不构成部署或生产配置授权。
- 生产 Payment ID 和基于该 ID 的 Mercado Pago 质量评估属于获批金丝雀后的证据，不得作为允许第一次金丝雀之前的前置条件。
- 受控试点可以继续保留 D-008 和 D-017，但必须有支持主导的欠费恢复、逐笔对账、明确资金敞口上限和即时关闭能力。
- 公开发布前必须由负责人处理两项冲突：批准充电前预授权或经证明的等效资金风险方案；将 D-008 延期能力补齐为用户自助欠费查看、补缴和门禁恢复。
- `PAYMENT_RAILS_ENABLED` 的默认和窗口外有效值必须为 `false`。只有预金丝雀全部通过且具体金丝雀获得书面批准后，授权操作人才能在内部测试人即将操作前临时启用；取得唯一 Payment ID、触发停止条件或窗口结束后必须立即恢复为 `false` 并验证失败关闭。再次启用需要新批准。
- 当前预金丝雀为 NO-GO，单笔生产金丝雀未授权，受控试点和公开发布均为 NO-GO。

## 业务风险说明

- A1 在充电结束前不能保证最终扣款成功；D1 只能限制后续损失，不能追回已经交付的电量。
- C1 表示 EsLatin 是 Provider 侧收款主体；若未来第三方租户是实际销售方，税务、退款、拒付和资金结算责任应在启用该租户前完成法律与财税确认，或切换 C2。
