---
id: PAY-MP-001
status: approved
owner: product
---

# 产品决策

| 编号 | 决策 | 选择 | 原因 | 影响范围 | 状态 |
|---|---|---|---|---|---|
| D-001 | 单次充电结算 | A1：结束后按准确金额扣款 | 避免充值和差额退款，账单与实际电量一致 | shared | approved |
| D-002 | 卡片采集 | B1：托管安全结账页 | 降低 PAN/CVV 暴露和 PCI 风险 | frontend/backend | approved |
| D-003 | 首期收款主体 | C1：EsLatin 平台商户 | 当前上线范围最小，不引入租户 OAuth | backend | approved |
| D-004 | C2 扩展 | MerchantAccountResolver + MerchantContext | 后续租户 OAuth/Split 不改变 App 与计费主流程 | backend/shared | approved |
| D-005 | 欠费门禁 | D1：任何欠费阻止下一次充电 | 限制 A1 后付失败造成的持续损失 | shared | approved |
| D-006 | 已保存卡 | 每次重新输入 CVV | Mercado Pago 不保存 CVV，不承诺无感代扣 | frontend/backend | approved |
| D-007 | 数据库迁移 | 本期不新增 | 复用 Order、PaymentOrder、PaymentMethod 和 Redis | backend | approved |
| D-008 | 欠费用户体验 | 欠费列表、银行卡/钱包补缴 UI 和欠费恢复页延期 | 属于边缘场景；本期先保留 D1 服务端事实门禁和安全阻止提示，不让未冻结契约阻塞 Mercado Pago 主流程 | frontend/shared | approved |
| D-009 | 首次新卡证件信息 | 新卡 Token 化时采集 Mercado Pago Colombia 要求的证件类型与号码；不上传证件照片 | 满足 Provider 风控要求，同时避免 EsLatin 扩大身份数据处理范围 | hosted checkout/backend | approved |
| D-010 | 证件数据边界 | 证件类型与号码只交给 MercadoPago.js 生成 Card Token，不进入 EsLatin confirm JSON、数据库、日志、分析或错误追踪 | 降低隐私和合规风险 | shared | approved |
| D-011 | 卡种识别 | 卡品牌、发卡方和信用/借记/预付类型均根据 BIN/Provider 响应自动识别，只读展示，不允许用户手工选择 | 避免用户选错卡种和错误 Provider 参数 | hosted checkout/shared | approved |
| D-012 | 支持卡类型 | P0 支持 `credit_card`、`debit_card`、`prepaid_card`；无法识别或不支持时失败关闭 | 覆盖 Mercado Pago 当前卡类型，不再把未知卡默认为信用卡 | backend/frontend/contract | approved |
| D-013 | 托管页体验 | P0 使用全西班牙语、移动端优先的紧凑表单；不显示内部 purpose/代码值 | 降低支付摩擦并避免泄露技术实现 | hosted checkout/backend | approved |
| D-014 | 会话恢复 | 过期、缺失、已确认和临时不可用必须显示独立安全状态及返回/重建动作；过期页面不再展示可提交卡表单 | 防止用户在无效会话中继续输入敏感数据 | shared | approved |
| D-015 | 卡片保存 | 单次新卡消费固定 `save_card=false` 且不提供同时保存；保存卡只能使用独立 `purpose=save_card` Checkout | 避免一个 Provider 一次性 Token 同时承担最终扣款和 Customers/Cards 关联，并让用户意图明确 | frontend/backend/contract | approved |
| D-016 | 保存卡后续支付 | 已保存卡展示品牌、类型和尾号，后续支付只重新采集 CVV；不重复要求证件信息，Provider 额外验证除外 | 接近高频出行产品的低摩擦体验 | hosted checkout/frontend | approved |
| D-017 | 预授权表述 | P0 不实现也不宣称冻结、预扣或预授权；充电场景仅说明结束后按实际账单金额扣款 | 避免虚假承诺与用户误解 | shared | approved |
| D-018 | 分期 | 充电与绑卡流程固定一次付款，不向用户展示分期选择 | 充电最终金额场景不适合首期分期交互 | hosted checkout/backend | approved |
| D-019 | 一次性 Token 用途 | `charging_direct` Token 只用于当前充电最终扣款；`save_card` Token 只用于保存卡；两者不得双重消费或静默复用 | Mercado Pago Card Token 为一次性凭证，双用途会造成保存或扣款链路不确定 | shared | approved |
| D-020 | 首次真实上线等级 | 先通过预金丝雀门禁；再一次性批准单人/单笔生产金丝雀；关闭支付轨后完成三方对账和 Mercado Pago 生产质量评估；证据通过后单独审批受控试点扩展，公开发布再另审 | 生产 Payment ID 和基于它的质量测量只能在有限生产验证后形成，分段门禁既避免循环条件，也限制真实资金风险 | product/operations | proposed |
| D-021 | 金丝雀与试点资金敞口 | 金丝雀在启动前批准一名内部测试人、一个目的、精确窗口、最多一个生产 Payment ID 和 COP 上限；试点另行批准邀请用户、站点、时段、单会话/用户每日/总试点上限及停止阈值 | A1 无预授权时必须量化每个生产阶段的最大可损失金额，并把支付轨启闭限制在批准窗口 | product/risk/operations | proposed |
| D-022 | 公开发布资金风险 | 优先评估预授权并按最终准确金额捕获；如不采用，必须批准并证明等效低敞口方案 | ChargePoint、EVgo、Electrify America、Shell 均公开采用授权冻结；当前 D1 不能追回已交付电量 | shared/C3 | proposed |
| D-023 | D-008 发布边界 | D-008 只允许延续至受控试点；公开发布前交付自助欠费查看、补缴和恢复 | 竞品后付模式将阻断与 Pay Now/更新支付方式配套，避免用户无出口锁定 | frontend/shared | proposed |
| D-024 | 访客支付 | 首期试点和公开发布维持登录账户；访客支付另立需求 | 访客需要独立风控、收据、退款定位和站端能力，不是单次新卡的同义词 | product/shared | proposed |
| D-025 | 支持与退款承诺 | 批准西语支持时段、响应/退款处理时限和升级责任人 | 支付失败、重复扣款、欠费和退款必须有可执行运营闭环 | operations | proposed |
| D-026 | C1 商业责任 | 法律、财税、隐私和商业负责人书面确认收款、税务、退款、拒付和租户结算责任 | C1 使 EsLatin 成为 Provider 侧统一收款方并承担资金运营责任 | legal/finance/commercial | proposed |
| D-027 | 付费充电最低金额 | 付费充电每个会话最终至少支付 1,011 COP；免费定价模式仍为 0 COP | Mercado Pago Colombia Sandbox 实测 1,010 COP 及以下返回 2072，1,011 COP 起成功；同时让用户协议明确最低收费 | product/backend/frontend/legal | approved |

## 后续但不阻塞本期

- C2 启用前需要确定租户 KYC、OAuth 凭证加密存储、Split Payments、佣金和退款责任。
- A1 无法保证充电结束后的银行卡扣款成功，D1 只能限制后续损失。
- D-020 至 D-026 尚未批准；在负责人选择前，本文不得被解释为已同意预授权、改变 D-008 或授权真实上线。
