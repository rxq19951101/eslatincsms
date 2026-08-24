---
id: PAY-MP-001
status: approved
---

# 验收标准

1. 收费充电支持 `wallet` 和 `direct_card`，直接支付不会先充值钱包，也不产生钱包余额变动流水。
2. 新卡单次消费始终不保存卡：`charging_direct` 固定 `save_card=false`，App 和托管页不存在“同时保存”选择，也不会把该 Token 关联到 Mercado Pago Customer；只有独立 `purpose=save_card` Checkout 可以保存新卡。
3. 已保存信用卡、借记卡或预付卡支付时必须重新输入 CVV，并生成新的单次 Card Token；默认不重复要求证件信息，Provider 额外验证除外。
4. App 与 EsLatin API、日志、数据库和错误追踪中都不存在原始 PAN、有效期或 CVV。
5. App 不再使用现有自定义银行卡字段直接请求 Mercado Pago Card Token API；卡片采集由托管 HTTPS 页面中的 MercadoPago.js 安全字段完成。
6. 添加卡后只保存 Provider、Customer ID、Card ID、品牌、类型、后四位和默认标记；首张卡成为默认卡。
7. 用户只能查看、设为默认或删除自己的支付方式；跨用户 ID 返回 404，不泄漏卡片是否存在。
8. 删除卡同时更新 Mercado Pago 和本地投影；Provider 已不存在时按幂等成功处理。
9. `charging_direct` Payment Intent 由服务端绑定当前用户、设备、枪口、租户和商户引用，客户端不能覆盖这些字段。
10. 收费充电使用 `direct_card` 时，没有有效、匹配且未消费的 Payment Intent 不得下发 OCPP RemoteStart。
11. 一个 Payment Intent 最多启动一次；重复启动同一进行中会话保持幂等，不能用于其他充电桩或枪口。
12. OCPP StartTransaction 后，业务 Order 与 ChargingSession 正确关联；Redis Token 引用与数据库摘要可追踪但不暴露明文 Token。
13. 最终 PaymentOrder 只在会话结束、价格快照结算并得到服务端 Invoice 金额后创建；付费会话 Invoice 最低为 `1,011 COP`，免费会话保持 `0 COP`，金额与币种不可由客户端传入或修改。
14. Direct card PaymentOrder 的金额与 Invoice 完全一致；批准后 Invoice、Payment、Session 和 PaymentOrder 一致地变为已支付。
15. 免费会话不要求支付意图，生成 `0 COP` 已支付账单和审计，但不创建 Provider 订单或钱包流水。
16. 钱包余额不足时收费 Invoice 不得标记已支付，钱包不得被截断到零后视作完整结算。
17. 充值只有在 Provider 批准后增加钱包余额；重复请求和 Webhook 重放只增加一次。
18. 直接支付 `processing`、`action_required`、`approved`、`declined`、`error` 和 `expired` 均有稳定状态映射和用户提示。
19. `action_required` 只打开 Mercado Pago 允许域名返回的 HTTPS URL；完成或放弃 3DS 后由反查/Webhook 收敛。
20. 用户关闭 App 后，支付仍可通过 Webhook 和主动对账完成；重新打开 App 可恢复订单与账单状态。
21. 支付失败或 Token 丢失/过期时，Invoice/Session 进入未支付，不能被伪造为已支付。
22. 当前用户存在任何未支付收费账单时，所有新的收费和免费充电启动均返回 402 `UNPAID_CHARGES`；服务端 D1 事实门禁继续生效，本期 App 不得通过 UI 绕过或伪造解除门禁。
23. 本期 App 遇到 `UNPAID_CHARGES` 时只显示安全、可本地化的阻止提示，不依赖未冻结的欠费列表字段；欠费列表、银行卡/钱包补缴和欠费恢复页标记为 `deferred-by-owner`，后续另立需求验收。
24. 直接支付退款原路返回，支持全额/部分退款，累计退款不超过原支付金额且不修改钱包。
25. 钱包充值退款在可用余额不足时拒绝自动执行并进入人工处理，钱包余额不得变为负数。
26. Webhook 验签后必须按该订单的 MerchantContext 主动反查，校验 external reference、金额、币种和 Provider 状态。
27. C1 下所有新订单的服务端商户解析结果为 `platform:eslatin`；支付业务代码通过 `MerchantAccountResolver` 获取上下文，不直接读取固定全局 Token。
28. Order、PaymentOrder 和审计事件包含服务端推导的 `operator_tenant_id`、`merchant_mode`、`merchant_account_ref` 和 `payment_purpose`，不包含任何商户密钥。
29. 提供 Resolver 契约测试，证明同一支付/退款/Webhook 服务可接收另一 MerchantContext，而不改变 App API 或计费流程。
30. 本需求不增加数据库迁移；现有用户、定价和充电改动不得被覆盖。
31. 后端支付、计费和多租户定向测试，App 支付流程测试以及端到端模拟 Provider 测试全部通过并形成 QA 报告。
32. 首次新卡托管页动态加载 Mercado Pago Colombia 支持的证件类型，页面显示“Tipo de documento”和“Número de documento”，不得把证件类型隐藏或固定为 `CC`。
33. 新卡证件类型与号码只传给 MercadoPago.js Token 化调用，不得出现在 EsLatin confirm JSON、Redis、数据库、日志、分析、审计、错误追踪或 Deep Link 中。
34. 保存卡后续支付页只展示品牌、类型、尾号并重新采集 CVV，不重复渲染新卡卡号、有效期、持卡人姓名或证件字段。
35. 新卡输入 BIN 后自动识别并只读展示卡品牌、发卡方和 `credit_card | debit_card | prepaid_card`；页面不存在卡品牌、类型或发卡银行的手工选择控件。
36. `prepaid_card` 能通过 confirm 请求、服务校验、Provider Card 结果、本地兼容 codec、支付方式 API 和 App 展示完整投影；不得被拒绝或降级为 `credit_card`。
37. BIN 为空、识别失败、返回未知类型或证件类型加载失败时禁止确认并显示西班牙语可行动错误；不得使用默认 Visa、默认信用卡或其他猜测值继续。
38. 托管页全部用户可见文本使用西班牙语；不显示 `charging_direct`、`save_card` 等内部 purpose、Provider 原始错误或英语字段标签。
39. 卡号、有效期和 CVV Secure Fields 在手机和桌面端保持紧凑可用高度，窄屏布局不溢出；键盘、焦点顺序、错误播报和按钮 loading/disabled 可访问。
40. `charging_direct` 页面 CTA 和说明仅表达“验证银行卡并继续、充电结束后按实际金额扣款”，不得出现预授权、冻结、预扣或已付款表述。
41. 创建 Checkout Session 时，`purpose=save_card` 必须使用 `payment_method_mode=new_card`、`save_card=true` 且不带 `saved_payment_method_id`；所有其他 purpose 和所有 `saved_card` 模式必须为 `save_card=false`。任何冲突组合返回 400 `CHECKOUT_REQUEST_INVALID`，刷新、重试和回跳不得改变已冻结用途。
42. 会话过期/缺失、已确认和临时不可用分别渲染安全全页状态；无效会话不加载或不启用卡表单，并提供返回 App/上一页或重新开始动作。
43. confirm 的新卡非敏感提示字段只允许 Provider 自动识别出的 `payment_method_id`、`payment_type_id`、可选 `issuer_id` 和固定 `installments=1`；已保存卡不接受客户端覆盖这些卡片事实。
44. P0 不新增数据库迁移、不导入历史支付数据，也不改变 C1/C2、D1 和欠费 UI 延期决定。

## 后续需求验收边界

- 欠费列表 API 的顶层结构、字段、排序/分页、归属规则和错误语义尚未在本期冻结。
- 银行卡/钱包欠费补缴、支付结果恢复和门禁解除后的用户体验不属于本期验收；不得用当前后端实际返回或本地 mock 代替未来契约。
- 本期验收仍包含 D1 服务端欠费事实门禁和 `UNPAID_CHARGES` 安全错误映射，但不要求 App 显示账单详情。

## 生产发布门禁补充（proposed，待负责人批准）

以下门禁只定义发布最低证据，不改变上方已批准的 P0 功能验收：

1. 发布审查必须区分“预金丝雀准备”“单笔生产金丝雀”“金丝雀后核对/质量评估”“受控试点扩展”和“公开发布”；上一阶段证据不能自动批准下一阶段。
2. 预金丝雀必须完成独立 Backend QA PASS、Frontend QA PASS、测试/sandbox E2E PASS，以及新卡、保存卡、信用/借记/预付卡、3DS、processing、拒绝、网络未知、Webhook、全额/部分退款和重复通知的真实 Mercado Pago sandbox/适用 Provider 证据。
3. 预金丝雀还必须完成收据、支持、事故关闭/恢复演练、监控、法律/隐私/财税/商业签字和人工审查；此阶段 `PAYMENT_RAILS_ENABLED` 的有效值必须为 `false`。
4. 单笔生产金丝雀必须由负责人一次性书面批准一名内部测试人员、一个支付目的、精确窗口、COP 上限和最多一个生产 Payment ID；生产 Payment ID 及基于其执行的 Mercado Pago 质量评估不是预金丝雀门禁。
5. 授权操作人只能在预金丝雀 GO、所有预检完成且内部测试人即将操作时临时启用支付轨；取得唯一 Payment ID、触发停止条件或窗口结束后，必须立即恢复 `PAYMENT_RAILS_ENABLED=false` 并验证新支付失败关闭。本文不授权部署或生产配置变更。
6. 金丝雀后必须在支付轨关闭状态下完成唯一 Payment ID 的 EsLatin/Mercado Pago/实际资金三方对账，并用该 ID 运行 Mercado Pago 生产质量评估；`processing`、差异或质量问题未关闭时不得扩展试点。
7. 受控试点必须另行批准邀请名单、限定站点/时段、单会话/用户每日/全试点 COP 上限、即时停止条件、每个窗口的支付轨启闭和逐笔三方对账。
8. 受控试点保留 D-008 时，支付支持必须能够定位欠费、协助完成合法补缴或纠正错误门禁，并形成审计证据。
9. 公开发布必须提供欠费账单查看、银行卡/钱包补缴、结果恢复和事实结清后的门禁解除；D1 不得形成无出口的永久锁定。
10. 公开发布必须批准并验证预授权/最终捕获或经量化证明的等效资金风险方案；继续无预授权不能仅以 D1 作为充分控制。
11. 法律、隐私、财税和商业负责人必须书面确认 C1 收款主体、税务凭证、退款、拒付、对账单描述和租户结算责任。
12. 具体清单、当前 NO-GO 原因和证据包格式以 [PRODUCTION_LAUNCH_MINIMUM.md](./PRODUCTION_LAUNCH_MINIMUM.md) 为准。
