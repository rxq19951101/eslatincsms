# ADR-006 — D-204-B 风险预算与自动停止运行时

## Status

`accepted-target / contract-refresh-required / implementation-no-go`

本 ADR 已接受 D-204-B 目标架构，但仍要求 contract refresh；它不能授权 BE-205、数据库迁移、部署、生产配置或真实支付。

## Context

PAY-MP-001 采用结束后按准确 Invoice 扣款的 A1 路线。产品负责人已批准 D-204-B 的单会话、用户、站点、平台、MeterValues、离线/unknown、RemoteStop、StopTransaction 和恢复参数，但当前 ADR-005 与 `PAY-MP-002-v1` 将 D-204 明确排除在风险运行时和冻结契约之外。当前代码也没有风险账本、停止 worker 或 Provider unknown 24 小时自动收敛事实。

Product Owner 已明确批准窗口方案 A：site/platform 使用同一 UTC timestamp rolling 24-hour window；无 calendar-midnight reset；active reservations 与 unresolved exposure 计入；released/settled exposure 排除。该语义作为 RiskPolicyVersion 的正式 aggregate window 输入。

## Decision

接受以下 D-204-B 目标架构；本接受不等于实现、契约冻结、QA 或生产批准：

提议建立 Provider-neutral `RiskBudget` 子域：

1. PostgreSQL 的 immutable `RiskPolicyVersion`、append-only `RiskLedgerEntry`、typed `RiskReservation`、`RiskStopAction` 和 `ProviderResolution` 是 authority；Redis 只做缓存/协调。
2. Reservation 在 `/charging/start` 最终 preflight 后、RemoteStart 前以 `platform → site → user` 锁顺序原子创建；MeterValues/elapsed checkpoint 产生 consume，StopTransaction + final Invoice + payment resolution 完成 release，否则进入 unresolved。
3. 金额/能量/时长任一阈值、MeterValues 120/300 秒、offline/unknown 15,000 COP/5 分钟均通过 pinned policy version 产生一次性 stop decision。RemoteStop 经 Outbox/OCPP control，首发起 10 秒内、最多 3 次；Accepted 不等于物理停止，5 分钟无 StopTransaction 进入 unresolved/manual physical-stop path。
4. Provider unknown 在 24 小时内只使用同一 operation key 做 query/webhook recheck，不创建第二笔支付；24 小时仍未知自动保持 D1 blocked/debt-freeze 并进入人工队列。
5. user/site/platform 是风险聚合 scope；tenant_id 是 ownership/authorization scope，本次不新增未经批准的 tenant monetary cap。所有状态迁移、重试、scope、审计和回滚事实必须 typed、幂等、可重放、fail closed。
6. 当前 v1 保持不变；由 contract owner 新增 `PAY-MP-002-v2`（或等价 vendor media type）承载 risk projection、safe errors、commands 和 internal events。窗口语义已确认，但 v2 refresh 仍是实现前置门。

## Reason

风险预算的关键性质是并发下不能超额 reserve、未知状态不能释放预算、设备命令不能伪造物理停止、Provider unknown 不能重复扣款，并且跨租户平台聚合必须可审计。PostgreSQL typed facts + OCPP/Outbox handoff 能复用既有 owner，同时不把 Payment、Redis、UI 或 Provider Webhook 提升为不适合的 authority。

## Alternatives Considered

- 仅用 Redis 计数器或 UI/环境变量控制预算。
- 让 Payment service 直接调用 OCPP socket 并把 RemoteStop accepted 视为停止。
- 在 Provider unknown 时创建新的 payment attempt。
- 用当前 `PAY-MP-002-v1` 增加未版本化字段。
- 以 D-210 R2/R3 样本上限替代 D-204 风险预算。

## Rejected Alternatives

- Redis/UI/环境变量无法提供持久 authority、并发唯一性、审计和崩溃恢复。
- Payment 持有 OCPP socket 会破坏 Charging/OCPP owner 和事实收敛边界。
- Provider unknown 重复 create 会造成重复扣款和无法解释的 allocation。
- 未版本化修改 v1 会破坏既有 P001/P002 客户端兼容。
- 发布样本上限不是会话/站点/平台损失上限。

## Consequences

- 需要 additive schema、scope/window policy、数据库锁/唯一键、risk worker、Outbox/OCPP retry、Provider recheck、审计与可重建 ledger balance。
- 需要新版本化公共投影和 internal event contract；frontend/backend 必须同步，不能各自发明状态。
- D-204 active session 的回滚必须是关闭新入口并继续 pinned-policy convergence，不能删除事实或静默退回无界 A1。
- 当前实现、QA、E2E、容量和 Provider Sandbox 证据均不足，继续 implementation-not-ready 与 production NO-GO；这些是后续实现/QA/发布 gates，不构成目标架构 blocker。

## Affected Modules

Billing/Invoice（只读 authority）、ChargingSession/Pricing/MeterValues、FinancialEligibility、Payment/Provider/Recovery、OCPP control、Outbox/worker、Identity/Tenant/RBAC、Audit/Support、App/Admin projections、PostgreSQL/Redis。

## Date

2026-08-15

## Related Change ID

CHG-20260812-002

## Related Documents

- `docs/changes/CHG-20260812-002/D204-B_ARCHITECTURE_GATE.md`
- `docs/architecture/adr/ADR-005-pay-mp-002-risk-recovery-operations.md`
- `docs/features/PAY-MP-002/contracts/API.md`
- `docs/features/PAY-MP-002/backend/TASKS.md`（BE-205）
