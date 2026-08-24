# Architecture Changelog

当前完整技术架构以 `TECH_ARCHITECTURE.md` 为准。本文件仅记录显著结构变化。

## CHG-20260817-PAY-API-GOVERNANCE — Canonical Checkout and Provider Webhook boundary

- Date: 2026-08-17
- Summary: 将 App 支付创建/确认/结果查询收敛到 Checkout Session；将 Mercado Pago/SIM Webhook 收敛到独立 Provider-specific 路由；不再注册历史 Wompi、旧 create/status 路由。
- Architecture Impact: C2；不新增数据库迁移。
- Extension Rule: 新 Provider 只能实现服务端 Adapter/Registry/Credential Resolver/Webhook Adapter，不得新增 Provider-specific App payment endpoint。
- Related Change: `docs/changes/CHG-20260817-PAY-API-GOVERNANCE.md`。

## CHG-20260812-001 — Repository-first architecture governance

- Date: 2026-08-12
- Summary: 建立六个固定逻辑 Agent、C0–C3 分类、全局当前架构、ADR、边界与 QA 策略。
- Reason: 防止 Agent 临时记忆、feature 文档和代码演进产生未记录架构偏差。
- Affected Domains: 工程治理和全部模块的未来变更流程。
- Architecture Impact: C3 governance；运行时行为不变。
- Related ADR: ADR-001。
- Related implementation: `AGENTS.md`、`agent-skills/`、`docs/{product,architecture,backend,frontend,qa,changes}`。

## PAY-MP-001 — Hosted Mercado Pago payment boundary

- Date: 2026-08-12
- Summary: 在模块化单体内新增 Checkout、Provider adapter、reconciliation、保存卡投影和前端恢复协调器。
- Reason: 卡与证件敏感数据必须停留在 Mercado Pago 安全边界，同时支持单次卡消费和保存卡。
- Affected Domains: Payment、Wallet、Charging、Billing、App。
- Architecture Impact: C3 payment architecture。
- Related ADR: ADR-004。
- Related implementation: `docs/features/PAY-MP-001/`。

## CHG-20260812-002 — PAY-MP-002 C3 architecture approved; contract frozen

- Date: 2026-08-13
- Summary: Product Owner 已批准除 D-204 外的 PAY-MP-002 产品基线；接受 typed recovery/allocation、统一 D1 evaluator、退款/拒付、三方对账、细粒度双控、双轴 runtime rail 和结构化支持的目标架构。
- Reason: 当前 P001 owner 与 Hosted/OCPP 边界可复用，但 metadata、superadmin 单人操作、基础 reconcile 和环境总开关不能满足已批准的公开资金闭环。
- Affected Domains: Payment、Billing、Charging/OCPP、Webhook/Reconciliation、App/Admin、Tenant/Permission、Audit/Operations。
- Architecture Impact: C3 target 记录于 ADR-005；第二次且最后一次限定复审确认状态映射、P001/P002 media-type 兼容、D1/rail scope、platform Outbox、Admin 精确契约和前后端版本均闭合，冻结 `PAY-MP-002-v1`。
- Verdict: `approved`；已批准且非 D-204 的分批任务 implementation-ready，但代码、QA/E2E 和人工发布审查均未完成，生产 NO-GO。D-204 仅阻塞 BE-205、风险参数/UI/runtime 和真实资金发布。
- Related ADR: ADR-005。
- Related Change: `docs/changes/CHG-20260812-002.md`。
- Related feature review: `docs/features/PAY-MP-002/ARCHITECTURE_REVIEW.md`。

## CHG-20260812-002 / D-204-B — Risk budget and stop runtime target approved

- Date: 2026-08-15
- Summary: Product Owner approved window方案 A；D-204-B target architecture is accepted for the same site/platform UTC rolling 24-hour window, with active/unresolved exposure included and released/settled exposure excluded.
- Reason: Resolve the only outstanding product semantics blocker without treating absent runtime, contract, QA/E2E or capacity evidence as a product blocker.
- Affected Domains: Charging/MeterValues, Billing/RiskBudget, Payment/ProviderResolution, OCPP/Outbox, Tenant/RBAC, Audit/Operations, App/Admin projections.
- Architecture Impact: C3 target architecture accepted in ADR-006; PostgreSQL risk authority, typed reserve/consume/release/unresolved state machine, UTC rolling window, OCPP/Outbox handoff and fail-closed unknown handling are recorded. `PAY-MP-002-v1` remains unchanged; v2 contract refresh and implementation/QA/release gates remain required.
- Verdict: `architecture-approved` target; implementation-ready and production-approved remain false.
- Related ADR: ADR-006.
- Related Change: `docs/changes/CHG-20260812-002.md`。

## PERF-DB-001/002 — 高频设备写入治理

- Date: 2026-08-10
- Summary: Heartbeat/MeterValues 使用 Redis 实时事实、去重和 PostgreSQL 采样，减少持续重写入。
- Reason: 控制数据库写放大和历史表增长。
- Affected Domains: OCPP、Monitoring、Database。
- Architecture Impact: C2。
- Related ADR: ADR-003。
- Related implementation: `docs/features/PERF-DB-001/`、`PERF-DB-002/`。

## CHG-20260812-002 / D-204-B — PAY-MP-002-v2 contract frozen

- Date: 2026-08-15
- Summary: Refreshed `PAY-MP-002-v2` for D-204-B safe projections, risk decisions/errors, RemoteStop/StopTransaction SLA, Provider unknown 24-hour terminal projection and `risk-event.v2` internal events.
- Compatibility: P001 default API and `PAY-MP-002-v1` remain compatible; v1 does not expose D-204 fields. D-204 v2 uses `application/vnd.eslatin.pay-mp-002.v2+json`.
- Safety: server-derived tenant/scope/amount/policy/stop/provider facts; raw Provider payload prohibited; 406/409/422/503 and unknown/fail-closed semantics are frozen.
- Verdict: `contract-frozen / implementation-ready-for-BE205`; no endpoint, business code, migration, deployment or production configuration changed. Production remains NO-GO.
- Related ADR: ADR-006。
