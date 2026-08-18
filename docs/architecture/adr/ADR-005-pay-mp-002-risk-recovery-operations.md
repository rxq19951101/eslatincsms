# ADR-005 — PAY-MP-002 风险恢复与支付运营边界

## Status

`accepted-target / contract-frozen / implementation-ready / production-no-go`

已接受 D-201、D-202、D-203、D-205-A、D-206-B、D-207-B、D-208-B、D-209-B、D-210-B 对应的目标架构。`PAY-MP-002-v1` 已通过限定复审并冻结，非 D-204 分批任务可以实施。当前代码尚未符合该目标，QA/E2E 未通过，不能据此声明功能完成或生产可用。

D-204 为 `deferred-todo`：不阻塞本 ADR 的已批准范围，但继续阻塞 BE-205 风险运行时、任何默认风险参数和真实资金发布。

## Context

PAY-MP-001 已建立结束后按准确 Invoice 结算（A1）、Mercado Pago Hosted Secure Fields（B1）、平台集中收款（C1）、服务端 D1、支付查询/退款和基础对账。实际代码还存在以下 P002 缺口：

- 钱包/卡补缴没有共同的 typed RecoveryAttempt/PaymentAllocation；卡路径依赖 `PaymentOrder.metadata` 关联 Invoice、Session 和 tenant。
- 当前 D1 只识别 pending Invoice/completed-unpaid Session，不识别退款、拒付、late reversal、资金 unknown 或对账差异。
- 当前 Admin 支付能力为 superadmin-only，退款可单人直接执行；没有 D-206-B/D-207-B/D-208-B 所需审批和作用域。
- 当前 reconciliation 是单笔 Provider 状态收敛，没有 EsLatin/Provider/实际资金三方批次、差异和临时例外事实。
- `SupportMessage` 不是结构化支持工单；环境门禁不是作用域化 runtime rail control。
- OCPP 已有正确的 Start/Stop/MeterValues owner，但没有且不得默认增加 D-204 风险硬停止运行时。

## Decision

1. **保留 PAY-MP-001 A1。** 当前 P002 继续采用充电结束后由 StopTransaction/最终 MeterValues 形成准确 Invoice，再执行钱包或 Provider 支付。不得把 Payment `approved` 重解释为 authorization，也不在当前范围引入 authorize/capture/void。
2. **原始账单不可变。** Billing 继续拥有 Invoice、PricingSnapshot、用量和最终应收。Recovery、Refund、Support、Reconciliation 和 D1 只能引用这些事实，不能修改其业务含义。
3. **新增 typed recovery/allocation 事实。** 钱包、新卡和保存卡共享 RecoveryAttempt 状态机；PaymentAllocation 决定唯一结算赢家。Invoice/tenant/user/amount/currency/method/idempotency 必须 typed 可查询，不能只放 metadata/Redis。
4. **建立唯一 FinancialEligibility evaluator。** Payment/Billing/Reconciliation 产生 blocking financial facts；evaluator 只计算 `eligible/blocked/recheck_required/unknown` 财务资格。Charging `/start` 组合该结果与服务端解析的 scoped runtime rail preflight 后执行准入。退款、拒付、late reversal、资金 unknown 和对账差异可重新阻断；无资源上下文的全局资格查询不得伪造 site/provider rail 结论。
5. **建立结构化退款/争议事实。** D-206-B 的全额/部分人工退款必须由一人发起、另一人批准，累计不超过实付；Provider 操作、失败、unknown 和用户工单状态可重放。Chargeback 与 refund 分离建模。
6. **建立三方对账域。** D-207-B 使用持续逐笔匹配和 Bogotá 营业日批次，记录 EsLatin/Provider/实际资金、差异、截止时间和 24 小时临时例外；例外由 finance 与 platform 两个不同授权主体批准。
7. **建立双轴 runtime control。** D-208-B 分别控制 paid charging admission 与 payment creation，支持平台/Provider/tenant/site scope。一人可关闭，恢复由不同人员批准且不自动恢复。关闭不停止 Webhook、主动查询、退款、对账、历史和支持，也不自动强停活跃会话。
8. **建立上下文支持域。** D-209-B 使用 SupportCase/CaseEvent 或等价 typed 事实关联账单、支付、退款和充电，只携带非敏感引用；SLA、责任人、邮件通知和站点紧急支持可审计。支持人员不得改写财务事实。
9. **保持 Provider adapter 边界。** Mercado Pago 是当前 adapter，不是 Recovery/D1/Refund/Reconciliation 的领域模型。未来 Provider 可通过 canonical capability 和 reference 扩展，不改写 Billing、OCPP 或 UI 核心状态。
10. **跨域副作用可靠交接。** 支付、账单、D1、支持、对账和控制间需要异步动作时，使用有 owner、唯一键、lease/retry/dead-letter/replay 的 Outbox/worker；Webhook processed、UI、Redis 和日志不是财务事实。冻结方案是在现有 Outbox 单表 additive 增加 `scope_type/scope_ref`、将 tenant 放宽为 nullable 并建立 DB CHECK/scope 唯一键；platform 使用 `tenant_id=NULL, scope_ref=platform:eslatin`，不得伪造 tenant。
11. **基础历史优先查询投影。** D-205-A 仅提供 App 内历史/详情和支付结果，不生成 PDF/下载/邮件收据或 DIAN 发票。只有性能证据需要时才新增可重建 read model。
12. **D-204 独立隔离。** 不创建 risk policy 默认值、risk ledger、MeterValues 风险计数、RemoteStop 阈值或 hard-stop worker。任何这些能力都必须在 D-204 获得 Product Owner 明确批准后重新审查。
13. **使用 additive、版本化兼容。** 无历史数据时不需要业务导入，但仍必须通过 schema version 建立 typed facts。回滚关闭 P002 新入口并保留所有财务/OCPP/审计事实；未确认状态 D1 fail closed。

## Reason

已批准产品范围同时涉及 Billing、Payment、D1、OCPP、Provider、租户、RBAC、退款、对账和运行控制。若继续依赖 metadata、单一 superadmin endpoint 或 UI 状态，会产生重复结算、跨租户访问、退款后仍解锁、无法证明资金闭环和无法安全关闭新增风险等不可接受结果。独立 typed facts 和明确 owner 能在保留 PAY-MP-001 的同时提供可审计、可重放且 Provider-neutral 的扩展边界。

## Alternatives Considered

- 直接扩展现有 `PaymentOrder.metadata` 和 `SupportMessage`。
- 保持所有 Admin 支付动作 superadmin 单人执行。
- 只依据 Invoice `paid` 或 Provider `approved` 判定 D1。
- 用环境变量或前端开关承担紧急关闭。
- 立即切换到 Provider authorization/capture。
- 为 D-205-A 立即建立独立历史读库。

## Rejected Alternatives

- JSON/Redis 无法承担并发唯一性、状态迁移、查询、审批和审计权威。
- 单一 superadmin 不能满足退款、对账例外和恢复的职责分离。
- Invoice `paid`/Provider `approved` 无法表达退款、拒付、unknown、资金差异和迟到反转。
- 环境变量没有运行时 scope、版本、审批和安全恢复语义；前端不能成为生产控制面。
- 当前产品选择是 A1 + 风险预算方向，且 D-204 未批准；不得自行切换支付时序或填默认参数。
- P0 基础历史可由权威表查询投影满足，过早建立读库增加一致性负担。

## Consequences

- 目标架构已接受；2026-08-13 第二次且最后一次限定复审确认 CF-201～CF-206 已闭合，`PAY-MP-002-v1` 已冻结，非 D-204 分批任务 architecture-approved / implementation-ready。
- 后端需要 additive typed schema、状态机、唯一约束、RBAC/approval 和对账/控制服务；前端只能消费冻结契约。
- PAY-MP-001 现有 Hosted/Provider/Invoice/OCPP 路径继续兼容；P002 不得把旧 metadata 自动升级为新财务事实。
- 当前直接退款和支付 Admin 页面只能视为 P001 运维能力，不能宣称满足 D-206-B～D-208-B。
- 架构批准不表示 typed schema/API/worker/UI 已实现，也不表示 QA、E2E 或人工发布审查通过。
- `PAYMENT_RAILS_ENABLED` 继续受既有 QA/人工审查关闭门禁；本 ADR 不授权配置、部署或真实资金操作。
- D-204 获批后必须新建或更新架构记录，明确风险 policy、预算维度、OCPP 确认、SLA、监控和回滚。

## Affected Modules

- Billing/Charging：Invoice、PricingSnapshot、ChargingSession、D1 evaluator。
- Payment：RecoveryAttempt、PaymentAllocation、PaymentOrder、Wallet、Checkout、Provider adapter、Webhook、refund/chargeback/reconciliation。
- OCPP：RemoteStart/Stop、Start/StopTransaction、MeterValues、Outbox；当前不增加 risk runtime。
- App/Admin：欠费恢复、基础历史、退款/支持、对账和 rail-control 投影。
- Identity/Operations：tenant/resource scope、RBAC、approval intent、SupportCase、AuditLog。
- Data/Async：PostgreSQL typed facts、additive schema、Outbox/worker 和可重建 projection。

## Date

2026-08-13

## Related Change ID

CHG-20260812-002

## Related Documents

- `docs/changes/CHG-20260812-002/PRODUCT_APPROVAL.md`
- `docs/features/PAY-MP-002/ARCHITECTURE_REVIEW.md`
- `docs/features/PAY-MP-002/STATUS.md`
- `docs/architecture/adr/ADR-003-ocpp-realtime-and-sampled-persistence.md`
- `docs/architecture/adr/ADR-004-mercadopago-hosted-payment-boundary.md`
