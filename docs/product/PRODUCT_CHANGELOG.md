# Product Changelog

本文件记录产品架构的显著变化；当前完整状态以 `PRODUCT_ARCHITECTURE.md` 为准。

## PAY-MP-001 — Provider-compatible minimum charging amount

- Date: 2026-08-18
- Summary: 付费充电最低结算金额由 `1,000 COP` 调整为 `1,011 COP`；免费定价模式仍为 `0 COP`。
- Reason: Mercado Pago Colombia Sandbox 使用固定 EsLatin 测试应用和 APRO 测试卡时，`1,010 COP` 及以下重复返回 `2072 Invalid value for transaction_amount`，`1,011 COP` 起返回 `approved/accredited`。
- Scope: BillingService、Hosted Checkout/App/法律文案、PAY-MP-001 当前产品/后端/契约文档；无数据库迁移、无历史数据改写、无 Provider API 变更。

## CHG-20260817-PAY-API-GOVERNANCE — App 支付接口统一

- Date: 2026-08-17
- Summary: App 支付统一使用 Checkout Session；当前产品只启用 Mercado Pago；Provider 选择、收款主体和凭证留在服务端；未来 Provider 复用同一 App 契约并通过 Adapter/Registry 扩展。
- Scope: 历史 `/wallet/payments/*` 创建、状态和旧 Webhook 不再作为当前 App API；无数据库迁移、无历史数据导入。
- Related Change: `docs/changes/CHG-20260817-PAY-API-GOVERNANCE.md`。

## PAY-MP-002 — 公开上线支付恢复与运营闭环（产品基线批准）

- Date: 2026-08-13
- Summary: 批准欠费全额补缴与 D1 重检、结束后按准确 Invoice 扣款方向、基础历史、双人退款、每日三方对账、双轴紧急关闭、上下文支持和 R0～R4 分阶段发布。
- Remaining Gate: D-204 风险预算数值、停止条件和 SLA 已移入 TODO，不阻塞架构审核，但继续阻塞 BE-205 风险运行时和真实资金发布；架构、契约、实现、QA/E2E 和生产 GO 均未批准。
- Affected Domains: 支付、账单、充电风险、App、Admin、客服、财务、运营与发布治理。
- Architecture Impact: C3；需要后续 architecture-agent 审核，当前不得实现或启用生产支付轨。
- Related Change: `docs/changes/CHG-20260812-002/`。
- Related feature: `docs/features/PAY-MP-002/`。

## PAY-MP-002 — D-204-B 自动风险闭环产品批准

- Date: 2026-08-15
- Summary: Product Owner explicitly approved D-204-B: 200,000 COP / 100 kWh / 180-minute session cap; 250,000 COP user open-unpaid cap; 1,000,000 COP site periodic cap; 5,000,000 COP platform cap; automated MeterValues/offline stop behavior; Provider unknown reconciliation for up to 24 hours without duplicate charge; automated RemoteStop/recovery flow with human handling limited to exceptional cases.
- Remaining Gate: D-204-B architecture review, contract refresh, implementation, independent QA, E2E and human release review; production payment remains NO-GO.
- Related Change: `docs/changes/CHG-20260812-002/`.
- Related feature: `docs/features/PAY-MP-002/`.

## CHG-20260812-001 — 建立持久产品架构治理

- Date: 2026-08-12
- Summary: 建立当前完整产品架构作为长期事实来源，并将 Agent 记忆降级为临时执行上下文。
- Reason: 避免功能文档和临时 Agent 对话碎片化产品认知。
- Affected Domains: 全产品治理。
- Architecture Impact: 治理层 C3；不改变运行时业务行为。
- Related ADR: `ADR-001-repository-documentation-as-project-memory.md`。
- Related implementation: `AGENTS.md`、`docs/product/`、`docs/architecture/`、`docs/changes/CHG-20260812-001.md`。

## PAY-MP-001 — Mercado Pago 支付与单用途 Checkout

- Date: 2026-08-12
- Summary: 支持 Mercado Pago 托管新卡、独立保存卡、保存卡 CVV、钱包充值、直接充电支付、对账与退款基础能力。
- Reason: 为哥伦比亚 App 用户提供非充值单次消费和可复用银行卡能力。
- Affected Domains: 支付、钱包、充电、账单、App。
- Architecture Impact: C3 支付架构；当前仍处于 QA/生产支付轨门禁。
- Related ADR: `ADR-004-mercadopago-hosted-payment-boundary.md`。
- Related implementation: `docs/features/PAY-MP-001/`。

## PRC-MODE-001 — 明确定价模式

- Date: 2026-08-11
- Summary: 将价格状态收敛为 paid/free/unavailable，并按会话冻结价格事实。
- Reason: 防止无价格充电桩直接上线收费或错误展示为免费。
- Affected Domains: 站点、充电桩、定价、账单、App/Admin。
- Architecture Impact: C2。
- Related ADR: 无全局 ADR；功能证据位于 `docs/features/PRC-MODE-001/`。
- Related implementation: pricing service、Admin/App 价格投影与测试。
