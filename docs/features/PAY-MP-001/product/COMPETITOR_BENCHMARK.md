---
id: PAY-MP-001
document: competitor-payment-benchmark
status: research-complete-owner-review
owner: product
market_context: Colombia
research_date: 2026-08-12
---

# 充电运营平台支付模式对标

## 1. 研究范围与方法

本文对标 ChargePoint、EVgo、Electrify America、Tesla Supercharging 和 Shell Recharge 的用户支付模式，并补充 Mercado Pago Colombia 对 EsLatin 当前实现的 Provider 约束。

研究规则：

- 只把平台或支付服务商官方页面明确陈述的内容写作“来源事实”。
- 官方页面未说明的能力标记为“本次来源未确认”，不推断其不存在。
- 美国平台的支付行为用于识别成熟充电产品模式，不代表哥伦比亚法律、税务或卡组织规则。
- “对 EsLatin 的启示”和“建议”均为产品推导，不伪装为竞品事实。
- 官方页面会变化；进入公开发布审批前应重新核验来源日期和地区适用性。

## 2. 官方事实对比

### 2.1 汇总矩阵

| 平台 | 账户/卡在档 | 访客或 Pay-as-you-go | 钱包/数字钱包 | 开始前授权冻结 | 最终结算 | 欠费恢复 | 收据与支持 |
|---|---|---|---|---|---|---|---|
| ChargePoint | 官方支持页列出信用卡、借记卡、PayPal、Apple Wallet、Google Pay，并指引在 App 账户中维护支付信息 | 本次查阅来源未确认免账户流程 | 支持 Apple Wallet、Google Pay；这不等同于储值余额钱包 | 支付处理方可能在会话开始前放置临时授权；实际会话金额结算后由银行释放 | 只处理实际充电金额 | 本次查阅来源未确认自助欠费入口 | 官方提供 24/7 电话和在线支持；本次来源未确认收据路径 |
| EVgo | 账户激活要求有效卡在档；支持信用、借记和预付卡，首张卡成为默认卡 | 无账户用户可在支持的站点读卡器/终端使用实体卡；官方说明无账户交易没有收据 | 实体终端对 Apple Pay/Google Pay 的支持有限；本次来源未确认储值钱包 | 一般说明卡终端授权可到 60 USD；访客帮助页另说明部分设备可到 100 USD，取决于设备/场景 | 只有实际会话总额入账；账户同日计费 | 超过冻结额度且最终扣款失败时可更新支付方式补足；负账户会被冻结，未处理可能暂停 | 账户用户有历史/收据；访客无收据；Charging Crew 24/7 支持 |
| Electrify America | Pass/Pass+ 账户需要添加有效支付方式；费用在会话结束后扣到卡在档 | 所有站点提供信用卡读卡器，访客可直接刷卡 | 支持 App、Apple Pay、Google Wallet；储值/自动充值余额正在退出，余额用完后直接扣卡 | 访客卡通常 50 USD；App 用户开始时 20 USD，长会话可增加 20 USD 冻结 | 结束后只扣实际会话、税费和适用费用，冻结由银行释放 | 支付方式无效或拒绝时要求更新；无效支付时充电不继续 | 账户历史可分享收据；访客可在开始时提供手机号接收短信收据，终端显示总额；24/7 支持 |
| Tesla Supercharging | 使用前必须在 Tesla App 添加并指定默认支付方式，可保存多张卡 | Tesla 车辆支付由 App 管理；本次来源不把非 Tesla 地区流程概括为通用访客模式 | 本次来源未确认独立储值钱包；部分免费充电 credits 可用于合格场景 | 本次查阅的 Supercharging 支持页未声明预授权冻结 | 拔枪后从 App 指定支付方式自动处理；价格按插枪时规则确定 | App 显示未付余额并提供 `Pay Now`；欠费或错误支付方式可能阻止继续超充 | App Charging History 可查看和下载发票；官方支持渠道处理问题 |
| Shell Recharge | Shell App 确认支付详情后启动；部分充电桩支持信用卡 | 官方明确为无订阅的 pay-as-you-go | App 内支付；本次来源未把其描述为储值余额钱包 | 会话开始时对信用/借记卡做临时授权，金额依 App 或实体终端而异 | 会话结束后入账最终金额，临时授权通常在 48–72 小时释放，具体由银行决定 | 本次查阅来源未确认自助欠费入口 | Shell App 在充电完成后提供数字收据和充电历史 |

### 2.2 ChargePoint 来源事实

- ChargePoint 说明可能在充电开始前对支付方式做临时授权，以确认支付方式和资金可用；该金额显示为 pending，最终只结算实际充电金额，释放时间由银行控制。[临时授权说明](https://www.chargepoint.com/drivers/support/faqs/what-pre-authorization-hold)
- 官方列出的支付方式包括信用卡、借记卡、PayPal、Apple Wallet 和 Google Pay，并指引用户在 App 的账户支付区域维护信息。[支付方式](https://www.chargepoint.com/drivers/support/faqs/what-payment-methods-can-i-use)
- 官方支持页提供全天候电话支持。本次两份来源没有确认访客交易、欠费补缴或收据路径，因此矩阵不作推断。

### 2.3 EVgo 来源事实

- EVgo 账户要求有效支付方式在档，支持信用卡、借记卡和预付卡，首张卡自动设为默认卡。[添加支付方式](https://helpcenter.evgo.com/hc/en-us/articles/8927262806551-Add-a-new-payment-method)
- 没有账户的用户可在支持的站点通过读卡器、集中终端或 Charging Crew 启动；官方同时说明此类无账户交易不提供收据，并建议使用免费 Pay As You Go 账户获取完整历史。[访客刷卡](https://helpcenter.evgo.com/hc/en-us/articles/16197083743127-Start-a-charge-Credit-card-at-the-station)
- 通用授权说明写明卡终端可能放置最高 60 USD 的临时授权；访客刷卡帮助页另写明某些充电设备可最高 100 USD。两者是官方当前页面中的场景差异，不应对外统一承诺为一个固定金额。[授权冻结](https://helpcenter.evgo.com/hc/en-us/articles/20444993723543-Pre-Authorization-Holds) · [访客刷卡](https://helpcenter.evgo.com/hc/en-us/articles/16197083743127-Start-a-charge-Credit-card-at-the-station)
- 若会话超过授权额度且借记/预付卡余额不足导致最终扣款失败，用户可更新支付方式处理剩余金额；负账户会被冻结，未及时付款可能暂停并进入追收。[账户补缴](https://helpcenter.evgo.com/hc/en-us/articles/20446273768855-Make-an-account-payment)

### 2.4 Electrify America 来源事实

- 会员可用 App 或数字会员凭证启动；没有账户的访客可直接在所有站点信用卡读卡器使用 Visa/Mastercard。[公开充电 FAQ](https://www.electrifyamerica.com/mobile-faq/)
- 访客卡支付使用 50 USD 临时授权；App 用户通常在开始时做 20 USD 授权，长会话可能追加 20 USD。最终只扣实际充电、税费和适用费用，授权释放由银行决定。[支付与授权 FAQ](https://www.electrifyamerica.com/mobile-faq/)
- 官方说明储值余额和自动充值正在退出：剩余余额先抵扣，不足部分扣卡；余额用完后未来会话直接扣卡在档。[钱包调整](https://www.electrifyamerica.com/mobile-faq/)
- 支付方式无效或会话中拒绝时要求用户更新，支付无效则充电不继续。[无效支付](https://www.electrifyamerica.com/mobile-faq/)
- 账户用户可在 Charging History 分享收据；访客提供手机号后可收到短信收据，充电桩屏幕也显示最终总额。[收据](https://www.electrifyamerica.com/mobile-faq/)

### 2.5 Tesla Supercharging 来源事实

- Tesla 车主在使用 Supercharger 前必须在 App 中添加并指定默认支付方式；可以维护多张卡，但必须有一张主支付方式。[Supercharging 支付](https://www.tesla.com/support/charging/supercharging)
- 拔枪后会从 App 指定方式处理付款；支持页没有声明该流程使用预授权冻结，因此本文不推断有或没有其他底层风控。[充电与付款](https://www.tesla.com/support/charging/supercharging)
- App 会显示未付余额并提供 `Pay Now`；未付余额或错误支付方式可能阻止继续使用 Supercharger。[欠费恢复](https://www.tesla.com/support/charging/supercharging)
- 用户可在 Charging History 查看并下载发票；站点价格和正常税费在 App/车机中展示，价格按插枪时规则确定，不在会话中途变化。[发票和价格](https://www.tesla.com/support/charging/supercharging)

### 2.6 Shell Recharge 来源事实

- Shell Recharge 官方描述为无订阅的 pay-as-you-go，可通过 Shell App 支付，部分充电桩还支持信用卡。[Shell App EV FAQ](https://www.shell.us/electric-vehicle-charging/shell-app-ev-faqs.html)
- 会话开始时会对信用/借记卡放置临时授权，金额依 App 或实体终端而异；会话结束后只入账最终金额，临时授权一般在 48–72 小时释放，具体时间由银行决定。[预授权说明](https://www.shell.us/electric-vehicle-charging/shell-app-ev-faqs.html)
- App 支持确认支付详情、启动/停止、监控和查看实时价格；充电结束后可查看数字收据及历史。[Shell EV charging](https://www.shell.us/electric-vehicle-charging.html) · [Shell App](https://www.shell.us/rewards-and-savings/shell-app.html)
- 本次查阅来源没有确认未付余额的自助恢复模式，因此不作推断。

## 3. Mercado Pago Colombia 的相关官方约束

以下是 Provider 事实，不是竞品行为：

- Mercado Pago 支持 Customer/Card 保存和复用；保存卡付款仍需要重新采集 CVV，因为 Provider 不保存该安全码。[保存卡](https://www.mercadopago.com.co/developers/en/docs/checkout-api-payments/how-tos/payment-approval/saved-cards)
- 3DS 需要 Challenge 时，支付保持 `pending/pending_challenge`，返回受信任的 Challenge 资源；用户通常约有 5 分钟完成，超时可能被拒绝。[3DS](https://www.mercadopago.com.co/developers/en/docs/checkout-api-payments/how-tos/integrate-3ds)
- Webhook 可实时通知支付创建/更新；生产配置要求 HTTPS URL，并可通过 `x-signature` 和应用 secret 验证来源。[支付通知](https://www.mercadopago.com.co/developers/en/docs/checkout-pro/payment-notifications)
- 已批准付款可做全额或部分退款；官方当前说明退款窗口最长 180 天，并要求商户账户有足够可用余额。[取消与退款](https://www.mercadopago.com.co/developers/es/docs/checkout-api-payments/payment-management/cancellations-and-refunds)
- 拒付会使争议资金处于冻结状态，并可能要求商户在截止日期前提交交易证据；结果可能导致资金被扣回或返还。[拒付管理](https://www.mercadopago.com.co/developers/en/docs/checkout-pro/chargebacks)
- 生产要求包括生产凭证、HTTPS、集成质量、通知和财务报告；生产集成质量测量需要一个生产 Payment ID，因此实际质量结果只能在获批的有限生产验证产生该 ID 后形成。测试账户报告可能没有真实资金数据。[生产要求](https://www.mercadopago.com.co/developers/en/docs/checkout-api-payments/integration-test/go-to-production-requirements) · [资金释放报告](https://www.mercadopago.com.co/developers/en/docs/reports/released-money/introduction)
- Mercado Pago 当前 Checkout API 参考列出自动处理及手动授权/捕获能力，但是否适用于 EsLatin 当前 Payments API 路径、哥伦比亚卡种、金额调整和充电场景，必须由后续 architecture/backend 研究与真实 Provider 验证，不能仅凭参考页认定可直接上线。[Checkout API 参考](https://www.mercadopago.com.co/developers/en/reference/online-payments/checkout-api/overview)

## 4. 跨平台产品模式

### 模式一：会话前授权，结束后按实际金额结算

**来源事实：** ChargePoint、EVgo、Electrify America 和 Shell Recharge 的官方资料都明确描述了临时授权；最终只处理实际会话金额。具体冻结额度和释放时间因平台、渠道、设备和银行而异。

**产品推导：** 这是开放式、最终金额未知的充电场景中最常见的资金风险控制。它把“支付方式存在”提升为“开始前有一定资金可用”，但会造成用户可用额度暂时减少，因此必须清楚披露。

### 模式二：强账户/卡在档，结束后自动扣款，并提供欠费恢复

**来源事实：** Tesla 要求默认支付方式，拔枪后扣款；如果形成未付余额，App 显示提醒和 `Pay Now`，未付余额可能阻止后续充电。EVgo 也会冻结负账户并要求补足余额。

**产品推导：** 后付模式的“阻断”与“恢复”必须成对存在。只有阻断而没有可理解、可支付、可恢复的入口，会把风险控制转化为永久用户流失和客服事故。

### 模式三：访客可用，但风险和凭证体验不同

**来源事实：** Electrify America 和部分 EVgo/Shell 站点支持无账户或实体卡支付；此类流程通常使用较高授权冻结。EVgo 明确说明无账户刷卡交易没有收据，而 Electrify America 通过短信/终端补充访客收据。

**产品推导：** 访客支付不是首期必须能力。它要求站端支付硬件、身份弱化后的风控、收据送达、退款定位和支持查询均另行设计；不应为了“单次消费”而误把 EsLatin 当前登录用户的一次性新卡流程称为 guest checkout。

### 模式四：从预充值钱包迁移到直接卡支付

**来源事实：** Electrify America 正在退出自动充值和余额模式，剩余余额用完后直接扣卡在档。

**产品推导：** 钱包可以保留为一种支付方式，但不应成为所有用户使用充电的强制中间层。EsLatin A1 的非充值单次扣卡方向符合这一趋势；真正缺口在风险控制和欠费恢复，不在是否强迫充值。

### 模式五：收据、支持和争议是支付主旅程的一部分

**来源事实：** Electrify America、Tesla 和 Shell 都提供会话历史或数字收据；多个平台提供全天候充电支持。Mercado Pago 要求商户处理退款、通知、对账和拒付证据。

**产品推导：** 支付成功页面不是旅程终点。生产最低产品必须覆盖收据、退款进度、欠费恢复、支持查询、对账差异和拒付证据。

## 5. 对 A1/B1/C1/D1 的影响

| EsLatin 决策 | 对标结论 | 保留项 | 最低补强 |
|---|---|---|---|
| A1：结束后准确扣款 | 与竞品“最终只收实际金额”一致，但竞品通常在开始前先授权，Tesla 则依赖强账户和欠费恢复 | 保留准确账单和不强制充值 | 试点定义 COP 敞口上限；公开版批准预授权或经证明的等效风险方案 |
| B1：托管安全页 | 与 Provider Token 化、3DS 和减少敏感数据范围相容 | 保留托管安全边界、独立绑卡和保存卡 CVV | 完成真实 3DS、移动端、无障碍、恢复、拒绝和 Provider 故障验证 |
| C1：EsLatin 统一收款 | 可作为首期最小商户集成，但 EsLatin 将直接承担退款、拒付、资金冻结、对账和用户账单主体责任 | 保留 MerchantAccountResolver 的 C2 边界 | 上线前取得法律/财税/隐私/商业签字和租户结算运行方案 |
| D1：欠费阻断 | 与 Tesla/EVgo 的账户限制方向一致 | 保留服务端事实门禁 | D-008 只能作为受控试点暂缓项；公开版必须增加自助查看、补缴和恢复 |

## 6. 对 EsLatin 发布等级的建议

以下均为推导/建议，不是已批准决定。

### 6.1 预金丝雀与单笔生产金丝雀

- 先在支付轨关闭状态下完成独立 QA、测试/sandbox E2E、Provider、运营、对账、法律和人工门禁；此阶段不要求先有生产 Payment ID。
- 预门禁通过后，单独批准一名内部测试人员、一个支付目的、精确窗口、COP 上限和最多一个生产 Payment ID。
- 仅在测试人即将操作前临时开启支付轨，取得唯一 Payment ID、触发停止条件或窗口结束后立即关闭；该建议不授权部署或生产配置变更。
- 支付轨关闭后逐笔三方对账，并使用该 Payment ID 执行 Mercado Pago 生产质量评估；证据未通过时不得扩大范围。

### 6.2 受控试点扩展

- 保留 A1/B1/C1/D1、D-008 和 D-017，不在本次文档任务中改变实现。
- 仅邀请用户、有限站点和明确 COP 风险预算；支付/财务/工程在试点期间在线。
- 允许欠费通过支持运行手册处理，但每笔必须可定位、可补缴或可纠错、可审计。
- 逐笔完成 EsLatin、Mercado Pago 和实际资金三方对账；任何未解释差异立即停止下一批。

### 6.3 公开发布

- D-008 不再满足最低闭环：必须提供欠费账单、支付重试、状态恢复和门禁解除。
- 对预授权进行独立 C3 可行性研究。若 Mercado Pago 当前集成不适用，则负责人必须批准经量化证明的替代风险控制，而不是默认为无风险。
- 不要求首期加入 guest、PSE、Nequi、分期或更多钱包；这些不是解决当前后付风险的前置条件。
- 必须把收据、退款、拒付、支持和财务对账作为核心产品能力而不是后台附属事项。

## 7. 对标结论

EsLatin 当前主方向并非错误：准确后结算、托管卡片安全页、账户支付方式和 D1 门禁都能在成熟平台中找到相似部分。真正的生产差距在于两组闭环尚未同时成立：

1. **开始前风险闭环：** 当前没有竞品常见的授权冻结，也没有已批准的等效敞口控制。
2. **失败后恢复闭环：** 当前有 D1 阻断和服务端补缴基础，但 D-008 延期了用户自助查看、支付和恢复。

因此，当前产品可以继续推进预金丝雀准备，但现有后端 QA 报告为 `blocked`、前端 QA 为 `blocked`、E2E 尚未正式闭环，预金丝雀仍是 NO-GO。单笔生产金丝雀必须在预门禁通过后单独批准；金丝雀对账和 Mercado Pago 质量评估通过后才能审批受控试点扩展。公开发布还必须先由负责人处理 D-022 和 D-023 提案。
