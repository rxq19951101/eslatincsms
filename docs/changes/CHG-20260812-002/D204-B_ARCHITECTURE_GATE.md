---
change_id: CHG-20260812-002
feature_id: PAY-MP-002
decision_id: D-204-B
status: architecture-approved
verdict: architecture-approved-target
coupling_level: C3
product_approval_gate: passed
contract_status: PAY-MP-002-v1-frozen-d204-excluded; v2-refresh-required
architecture_target: approved
implementation_authorization: none
production_authorization: none
owner: architecture-agent
date_utc: 2026-08-15
---

# D-204-B 独立架构门禁

## 1. 门禁结论

**最终目标架构门禁：`architecture-approved`。**

产品批准前置门已通过：用户明确批准“批准 D-204-B 窗口方案 A”。站点与平台使用同一 UTC timestamp rolling 24-hour window；不按日历午夜重置；active reservations 与 unresolved exposure 计入；released/settled exposure 排除。该决定已记录在 PAY-MP-002 状态交接中，本次复审将其作为 RiskPolicyVersion 的正式窗口输入。

因此 D-204-B 的目标 authority、状态机、并发/幂等、OCPP/Outbox 交接、阈值、scope、审计、回滚与容量/QA 证据门禁已获架构批准；这不等于批准 BE-205 实现、API v2 冻结、QA 通过或生产 GO：

1. 当前 `PAY-MP-002-v1` 明确排除 risk ledger、默认阈值、硬停止和风险 UI；D-204 所需的公共状态、错误、审计投影和内部事件尚未进入任何冻结契约。
2. 当前代码没有 D-204 风险账本、reserve/consume/release/unresolved 状态机、MeterValues 风险新鲜度事实、RemoteStop 重试状态或 Provider-unknown 24 小时收敛 worker。
3. `PAY-MP-002-v1` 仍冻结且排除 D-204；契约刷新是实现前置门，不是本次目标架构 blocker。
4. 现有 QA/E2E/容量证据只覆盖 P002 非 D-204 范围或本地/SQLite/fake 观察，不能证明 D-204 的并发预算、停止 SLA、Provider unknown 收敛或跨层事实；这些保留为实现/QA/发布门禁。

本结论批准的是**D-204-B 目标架构**，不是实现授权、契约冻结、QA 通过或生产 GO。ADR-006 进入 accepted-target；下游仍必须完成 v2 contract refresh、BE-205、独立 QA/E2E、真实容量证据与人工发布审查。

## 2. 影响分析

```text
CHANGE_ID: CHG-20260812-002
Requested Change: 在 PAY-MP-001 A1 后付费路线中加入 D-204-B 风险预算、自动停止和自动恢复收敛。
Current Architecture: PAY-MP-001 Invoice/Payment/OCPP + PAY-MP-002 typed facts/FinancialEligibility/Outbox；没有 D-204 风险运行时。
Affected Product Domains: 充电、计费、支付、欠费、站点运营、租户、支持、审计、发布治理。
Affected Technical Components: Billing/Invoice、ChargingSession/MeterValues、Payment/Provider、FinancialEligibility、OCPP control、Outbox/worker、RBAC/Audit、App/Admin projections。
Existing Owner Module: Billing owns Invoice/usage; Charging/OCPP owns device facts; Payment/Reconciliation owns financial facts; Operations owns control/support; Identity owns scope.
Data Model Impact: C3 additive typed risk policy/reservation/ledger/stop/provider-resolution facts; no metadata/Redis authority。
API Impact: 必须新增版本化 D-204 risk projection/command/error/event contract；当前 PAY-MP-002-v1 不修改。
Permission Impact: App 只能读取自己的安全投影；tenant Admin 只能读取授权 tenant/site；平台事故/运营角色处理平台风险与人工异常。
Tenant Impact: session/site facts 必须绑定可信 tenant；platform aggregate 使用 platform scope，不伪造 tenant；不新增未批准 tenant monetary cap。
Integration Impact: Risk service 通过 Outbox/OCPP control 交接 RemoteStop；Provider unknown 只复用同一 operation key 查询，不创建第二笔扣款。
Backward Compatibility: PAY-MP-001 A1/B1/C1/D1 与 PAY-MP-002-v1 默认请求/响应保持；D-204 使用新版本/新投影。
Potential Coupling: High/C3；通过 immutable ledger、FinancialEligibility、OCPP control 和 Outbox 隔离。
Circular Dependency Risk: risk ↔ OCPP ↔ billing ↔ provider；禁止直接互写，以 facts + commands + final reconciliation 解环。
Migration Required: YES for implementation; additive schema/version/checks/indexes required;本次不创建/执行迁移。
Coupling Level: C3
Architecture Change Required: YES
Recommended Integration Strategy: 新增 Provider-neutral RiskBudget 子域，复用 Billing/Charging/Provider/OCPP/Outbox owner，不改变 Invoice 业务含义。
Rejected Integration Strategies: Redis/UI 计数、Payment 直接持 socket、RemoteStop accepted 视为已停止、Webhook approved 视为已结清、环境变量代替 risk policy、静默填充周期。
Reason: D-204 改变支付后付风险与 OCPP 停止假设，必须独立架构和契约门禁。
Implementation Dependencies: ADR-006 accepted-target → contract v2 refresh → schema/worker → backend QA → frontend QA → E2E → capacity evidence → human release review。
```

## 3. Authority 与事实所有权

### 3.1 风险账本 authority

- PostgreSQL 是风险账本、风险策略版本、Reservation、StopAction、ProviderResolution 和审计关联的持久权威；Redis 只做实时缓存、短期去重和调度协调，丢失时必须 fail closed，不得释放预算或判定已停止。
- `RiskPolicyVersion` 是不可变策略快照，至少绑定 `policy_version`、COP/kWh/时长上限、unknown/offline 缓冲、SLA、scope、effective time、approved reference 和 schema version。运行中的会话固定引用创建时的策略版本，不能被后续配置覆盖。
- `RiskLedgerEntry` 是 append-only 业务事实，动作只有 `reserve`、`consume`、`release`、`unresolved`（以及受控的 `correction`）。`RiskExposureBalance` 可以作为可重建/事务维护的索引，但不能取代 entry authority。
- 每个 entry 必须绑定 `app_user_id`、真实 `tenant_id`（platform entry 除外）、site、session、invoice（若已生成）、policy version、amount/currency、energy/duration snapshot、source event、idempotency key、时间和 before/after balance。
- Invoice、PricingSnapshot、MeterValues、ChargingSession、Payment/Provider facts 仍由原 owner 持有；RiskBudget 只引用它们，不重写它们的业务含义。

### 3.2 Scope

- `user` scope 聚合该用户跨运营租户的未结风险；AppUser 的 D1 仍是平台级事实。
- `site` scope 聚合该站点在批准窗口内的 active reservation 与 unresolved exposure。
- `platform` scope 使用 `platform:eslatin`，跨租户聚合；Outbox 的 platform event 使用 `tenant_id=NULL`，不得借用系统租户或真实租户。
- `tenant_id` 是所有站点/会话/财务事实的 ownership 和授权边界；本次产品批准没有独立 tenant 金额上限，因此不得擅自增加 tenant cap。租户管理员只能读取其 tenant/site 投影，不能读取平台总账或其他租户用户事实。

## 4. Reserve / consume / release / unresolved 状态机

风险账本采用两层状态：不可变 ledger actions + 一个由数据库事务维护的 `RiskReservation` 生命周期。目标迁移如下：

```text
preflight
  -> reserve (user + site + platform rows locked)
  -> reserved
  -> consuming (accepted MeterValues / elapsed checkpoints)
  -> stop_requested
  -> physical_stop_pending
  -> settlement_pending
  -> release_pending
  -> released

任何阶段的权威事实不可证明
  -> unresolved
  -> resolving (automatic query/replay)
  -> released              # 最终支付/账务事实完整且物理停止已确认
  -> unresolved             # 仍未知；不得自动放行或释放
```

不变量：

- `reserve` 在服务端 `/charging/start` 的最终组合 preflight 内完成，并在 RemoteStart 前提交；没有成功 reservation 不得发送 RemoteStart。
- `consume` 以单调 MeterValues、StopTransaction final meter、冻结价格快照和 UTC elapsed checkpoint 计算；重复/乱序事件由 session+source event/message key 去重，不能负向消费。
- `release` 只释放未使用的 reservation；最终 Invoice、Provider status、funds/reconciliation 和 physical stop 未全部收敛时，相关 unpaid exposure 进入 `unresolved`，不能因发送了 RemoteStop 或 Provider `approved` 就 release。
- `unresolved` 是 fail-closed 状态；它可以由自动事实收敛转为 `released`，但不能由 UI、人工备注、单个 Webhook 或 Redis TTL 转换。
- 单会话 COP/energy/duration 任一先达到上限即生成一次版本化 `stop_requested`；同一 session+policy+trigger 只有一个有效 stop decision。预算不足时新会话在 reserve 阶段拒绝，不依赖事后补救。

## 5. 并发、幂等与数据库事务

- Reserve 按固定顺序锁定 `platform → site → user` 的 scope balance rows；同一 scope 的并发 start 串行裁决，跨 scope 仍可并行。使用数据库唯一键和版本检查兜底，不能依赖 Python process lock。
- 幂等键至少包括 `session_id + policy_version + action + source_event_id`；`RiskReservation` 对 session/policy 唯一；ledger entry 对 scope/action/source/idempotency 唯一。相同 fingerprint 返回原结果，冲突返回 canonical conflict。
- MeterValues 事件以 OCPP message key/设备 transaction/session/source timestamp 去重，并拒绝旧值倒退；阈值 crossing、stop request、StopTransaction 和 Provider resolution 都必须可重放。
- Provider HTTP 不得持有数据库事务/行锁；先提交 operation key 与 `processing/unknown`，外部查询后短事务回写。任何 unknown retry 只 query 原 operation key，不再 create payment。
- OCPP command 只通过 Charging/OCPP control service；risk service 不持有 socket。Outbox/worker lease 必须支持 retry、DLQ、replay 和事件版本乱序保护。

## 6. MeterValues、离线与阈值交接

- 保留 ADR-003 的 Redis realtime + PostgreSQL sampled persistence，但 D-204 增加 durable risk checkpoint：每个用于风险决策的 checkpoint、阈值 crossing 和 stale transition 必须落 PostgreSQL；Redis latest 不是 risk authority。
- `MeterValues` age `<120s` 为 fresh；达到 `120s` 进入 `meter_degraded`，保留最后可信 checkpoint 并启动 bounded recovery/alert；达到 `300s` 无可信新值必须自动生成一次 `stop_requested`，不能等到最终 Invoice。
- 离线/unknown buffer 分为 money delta `15,000.00 COP` 与 elapsed `5 minutes` 两个边界，取先达到者；该 buffer 只在当前 session 的 stale/offline/unresolved 状态使用，不能在同时存在多类 unknown 时重复叠加。正式 contract 必须固定首次进入、重置和合并语义。
- 设备恢复后只能追加单调 checkpoint；迟到 MeterValues 不能撤销已发出的 stop decision。最终 StopTransaction/meter final fact 由 OCPP owner 写入，RiskBudget 消费并与 Invoice reconciliation。
- 若 Redis、风险 worker 或 durable checkpoint 不可用，收费 admission fail closed；活跃会话进入 `unresolved`/stop recovery，不得继续无边界后付。

## 7. OCPP / Outbox 交接与 RemoteStop SLA

- Risk service 在同一 PostgreSQL transaction 中写 `RiskStopAction` 和 `charging.risk_stop_requested` Outbox event；payload 仅含 session/tenant/site/charge point/transaction/policy/trigger/version 的非敏感引用。
- Outbox worker 通过既有 OCPP control/connection manager 发 RemoteStop，不能直接 import socket。第一条 RemoteStop 必须在触发事实被持久化后 10 秒内发起；自动尝试总数最多 3 次，重复事件必须复用同一 command identity。
- RemoteStop response `Accepted` 只表示桩接受命令，不表示会话已结束。只有 `StopTransaction`（及最终 MeterValues/账单）才能进入 `physical_stop_confirmed`/`settlement_pending`。
- 从首次 RemoteStop 发起起 5 分钟未收到有效 StopTransaction，RiskStopAction 进入 `physical_stop_failed/unresolved`，生成告警和结构化 SupportCase；不伪造 stop、不自动结算、不自动解除风险。
- 物理停止失败、重大账务差异、Provider unknown 超过 24 小时是唯一允许进入人工队列的 D-204 类别；日常 retry/query/recheck 必须自动完成。
- 现有 `OutboxService.enqueue` 仍按 `tenant_id` 查重，D-204 实现必须先统一为 `(scope_type, scope_ref, idempotency_key)`，并补齐 platform/tenant worker 的消费与 delivery ownership 证据。

## 8. Provider unknown 自动收敛

- Provider create/query 使用同一个 typed `provider_operation_key`；`unknown` 记录 `ProviderResolution`，写 `unresolved` ledger action，并创建带 due time/backoff 的唯一 recheck work item。
- 自动 recheck 在 24 小时内使用签名 webhook + 主动 query 收敛；重复 webhook/query 只更新同一 canonical fact，不新建 payment、allocation 或 refund。
- 解析为成功：先校验 amount/currency/merchant/tenant/session/invoice ownership，再产生唯一 payment allocation，触发 D1 recheck，最后 release 已不再需要的 reservation。
- 解析为拒绝/失败：保留 Invoice unpaid 与 user/site/platform unresolved exposure，触发 D1 blocked 和账户债务状态；不得把支付失败当作 release 或成功。
- 24 小时仍未知：系统自动标记 unresolved/debt-freeze，保持 D1 blocked，创建人工队列；人工只能处理该队列，不得通过备注清除账务事实。

## 9. 人工、权限、租户与审计

- App 只能看到自己的风险安全投影、approved policy display summary、当前状态、safe reason、last update 和 next action；不得提交 tenant、scope、amount、policy version 或 stop result。
- tenant Admin 只可读取本 tenant/site 的运营投影；平台事故角色可处理平台 scope 的 stop/recovery；所有资源 scope 由服务端从 session/site/charge point/Invoice 关联推导。
- AuditLog 记录 policy approval reference、system/actor、scope、session/invoice、action、old/new state、amount/currency、policy version、source event、idempotency key、command attempts、reason、result 和 timestamps；原始 Provider payload、PAN/CVV/证件/token 不进入 risk facts/audit/support。
- 风险状态、RemoteStop command、Provider resolution、manual handoff 和 policy activation 都是独立 typed facts；AuditLog 不能替代它们。

## 10. 回滚与故障安全

- 回滚不是删除风险事实、回退 Invoice 或把活跃 D-204 session 放回无界 P001 后付。任何新入口关闭后，已有 session 继续使用其 pinned policy 完成 stop/reconcile；未确认状态保持 `unresolved`/D1 blocked。
- 风险 worker/Outbox/Redis 健康未知时，关闭新的 paid admission，并继续运行 OCPP StopTransaction、Provider query、reconciliation 和 audit convergence；不得自动 reopen 或自动 resume。
- 数据库迁移采用 additive expand → validate → cutover；回滚只关闭 D-204 新入口/commands，保留 policy、ledger、stop、provider 和 audit facts，不 drop、不伪造、不自动退款。
- `PAYMENT_RAILS_ENABLED` 仍是独立部署总门禁，不能代替 D-204 risk runtime，也不能被本次架构审核修改。

## 11. 容量与 QA/E2E 证据门禁

当前证据不足以关闭 D-204：

| 证据域 | 已有证据 | D-204 仍需的最小证据 |
|---|---|---|
| Backend/DB | BE-201～BE-211 独立 QA；BE-211 仅 SQLite/local/fake | PostgreSQL 15 真实 schema 上的并发 reserve、scope lock、唯一键、migration/rollback、ledger rebuild、脏数据与跨 tenant 负例 |
| MeterValues | Redis realtime + 分钟采样测试 | 120s degraded/300s stop、Redis 丢失、乱序/重复/迟到 meter、durable checkpoint 与 billing final fact 的测试 |
| OCPP stop | 本地 RemoteStop/StopTransaction happy path | 10s first-attempt、最多 3 retries、5m StopTransaction timeout、offline/unknown、跨实例 connection ownership 和 DLQ/replay 证据 |
| Provider unknown | P002 fake/provider failure-closed/idempotency；Sandbox create 仍 external pending | 24h bounded query/retry、webhook/query race、同 operation key no-duplicate-create、成功/拒绝/仍未知三路 readback |
| Tenant/scope/audit | P002 scoped rail/RBAC tests | user/site/platform aggregate concurrency、tenant ownership、platform event scope、完整 ledger/stop/audit readback |
| Capacity | `production_capacity_claim=false` 的 200-row SQLite/fake observation | PostgreSQL/Redis/worker/Outbox under MeterValues rate and concurrent starts; report p95/p99 queue lag, lock wait, worker lag and SLA margin; no local result may be promoted to production claim |
| Frontend | P002 FE-201 and FE-204/205 first-slice QA | risk display/unknown/stop-pending/recovery UI, Spanish copy, accessibility, app restart/offline and no client authority |
| E2E | local P002 journeys; live Provider/Webhook pending external | D1→reserve→charge→MeterValues stale→RemoteStop→StopTransaction→Invoice→Provider unknown/recheck→release/unresolved, plus cross-tenant and rollback journeys |

## 12. Architecture change / contract refresh proposal

当前 `docs/features/PAY-MP-002/contracts/API.md` 的 `PAY-MP-002-v1` 保持不变。本审核只提出以下 refresh，不直接编辑契约：

- 建议创建 `PAY-MP-002-v2`（或等价的新 vendor media type），继续让 P001 默认和 v1 projection 向后兼容。
- App `preflight/start` 需要服务端生成的 `risk_decision`/`risk_policy_display` 安全投影：状态、safe reason、policy version、meter freshness、stop/recovery next action；不接受客户端阈值、tenant、scope 或金额。
- App/Admin 需要只读 RiskSession/RiskStop/ProviderResolution 投影；Admin 还需要 tenant/site/platform scope 过滤与 allowed actions。公共投影不得暴露 raw Provider payload 或内部全量 ledger 明细。
- 内部 Outbox event 需要 canonical `risk.reservation.created`、`risk.consumed`、`risk.release_requested`、`risk.unresolved`、`risk.stop_requested`、`risk.stop_confirmed`、`risk.provider_recheck_requested`、`risk.finalized`，带 `event_id/schema_version/aggregate/version/scope/idempotency_key/occurred_at`。
- 需要固定 canonical errors：`RISK_BUDGET_BLOCKED`、`RISK_STATE_UNKNOWN`、`METER_VALUES_DEGRADED`、`RISK_STOP_PENDING`、`PHYSICAL_STOP_TIMEOUT`、`PROVIDER_UNKNOWN`；所有写操作保留 idempotency/expected_version。
- Contract refresh 必须明确站点/平台窗口、buffer 首次进入/重置、risk public status mapping、RemoteStop attempts/timeout projection、Provider unknown 24h terminal projection 和 P001/v1 compatibility golden tests。

**禁止事项：** 不得将上述提案直接写入 `API.md`，不得由 backend/frontend 各自新增字段或使用 D-210 R2/R3 数字替代 D-204。

## 13. 精确 blocker 与所需证据

### BLOCKER-D204-001 — RESOLVED：站点/平台暴露窗口已批准

- **批准事实：** Product Owner 明确批准“批准 D-204-B 窗口方案 A”。site/platform 使用同一 rolling 24-hour window，以 UTC timestamps 计算；无 calendar-midnight reset；active reservations 与 unresolved exposure 计入；released/settled exposure 排除。
- **结论：** `BLOCKER-D204-001` 已解决。RiskPolicyVersion 可以使用 `scope ∈ {site, platform}` 与 UTC rolling-24h aggregate window；不得再回退为 Bogotá 日历日或隐含午夜 reset。

### IMPLEMENTATION-GATE-D204-002 — 当前 frozen contract 不承载 D-204

- **事实：** `PAY-MP-002-v1` §1 明确写出 D-204 risk ledger/threshold/hard-stop 不得包含；现有 API/事件没有 RiskStop/ProviderResolution 公共/内部契约。
- **所需证据：** architecture-agent 批准 ADR-006 后，由 contract owner 提交 `PAY-MP-002-v2` refresh，完成 backend/frontend 同步、golden compatibility、error/status/event review。
- **分类：** 这是 architecture-approved 之后的 contract-refresh/implementation gate，不是未决产品 blocker。
- **影响：** BE-205 实现、Risk UI/runtime 和 implementation-ready 状态保持 blocked；不得修改 v1 绕过门禁。

### IMPLEMENTATION-QA-GATE-D204-003 — 运行时/容量/QA/E2E 证据缺失

- **事实：** 当前代码/QA 明确没有风险 ledger/worker/threshold runtime；BE-211 capacity 是 local SQLite/fake 且声明 `production_capacity_claim=false`；E2E 没有 D-204 旅程，Sandbox Provider/Webhook 仍 pending。
- **所需证据：** BE-205 additive migration + worker implementation、独立 backend QA、frontend risk-state QA、完整 cross-module E2E、PostgreSQL/Redis/Outbox/OCPP capacity report、人工发布审查。
- **分类：** 这是实现、独立 QA/E2E、容量与人工发布 gate，不否定已批准的目标架构，也不是产品 blocker。
- **影响：** 不能宣称 D-204 已实现、资金风险已闭环或允许 R2/R3/R4/生产支付。

## 14. 下一允许动作

1. 按 ADR-006 的 accepted-target 结论，由 contract owner 以 v2 为单一共享契约完成 schema/event/public projection、兼容性和前后端同步；本次不实施。
2. 之后才允许 backend-agent 进入 BE-205 additive runtime；不得修改 v1、数据库或生产配置绕过门禁。
3. 独立 qa-agent（backend、frontend）和 e2e-agent 按证据矩阵验收真实 PostgreSQL/Redis/Outbox/OCPP、并发、幂等、阈值和 Provider unknown 24h 收敛。
4. 完成容量报告、人工发布审查及所有 R0～R4 门禁后，才可重新评估生产授权。
5. `PAYMENT_RAILS_ENABLED` 保持 false；不部署、不操作生产数据库、不启用真实支付。

## 15. Mandatory SELF_CHECK（final）

```text
ORIGINAL_SCOPE: architecture-agent 仅审核并记录 CHG-20260812-002 / PAY-MP-002 / D-204-B；不修改业务代码、数据库、迁移、部署或生产配置。
CURRENT_ACTIVITY: 已记录 D-204 目标 authority、状态机、并发/幂等、OCPP/Outbox、MeterValues/unknown、SLA、scope、审计、回滚、容量和 QA/E2E 门禁，并记录 contract refresh/architecture change proposal。
DIRECT_PROGRESS: Product Owner 已批准窗口方案 A；BLOCKER-D204-001 已解决；ADR-006 已进入 accepted-target，D-204-B 目标架构门禁现为 architecture-approved；实现与发布授权仍未推断。
NEW_EVIDENCE: site/platform 同一 UTC timestamp rolling 24h、无午夜 reset、active/unresolved 计入、released/settled 排除；OutboxService 仍按 tenant_id 查重；MeterTelemetryService 以 Redis/分钟采样为主；Session/OCPP stop 没有 D-204 retry/state worker；BE-211 capacity 仅 local SQLite/fake；Provider Sandbox/Webhook 未闭环。
REPEATED_ANALYSIS: 无；已复用已读取的权威文档和 QA 证据，没有第三轮自我修正或无限扩展研究。
SCOPE_DRIFT: 无；仅写入架构门禁、提案 ADR 和索引性状态记录。
BLOCKER_CLASS: 产品窗口 blocker 已解决；剩余为 contract-refresh、实现、QA/E2E、容量和人工发布 gates。
MINIMUM_NEXT_ACTION: 完成 v2 contract refresh；之后才允许 BE-205 实现。
ORIGINAL_SCOPE_PRESERVED: yes.
NO_HIDDEN_GOVERNANCE_CONFLICT: yes; product approval passed, but no technical or production authorization was inferred.
GATE_JUSTIFICATION: architecture-approved target; BLOCKER-D204-001 is resolved, while implementation/QA gates and required evidence remain listed in §13.
NEXT_ALLOWED_ACTION: contract owner performs the proposed v2 refresh; no business implementation or production enablement is authorized by this review.
```

## 16. 统一交接

```text
STATUS: done
GATE_STATUS: architecture-approved-target

CHANGED_FILES:
- docs/changes/CHG-20260812-002/D204-B_ARCHITECTURE_GATE.md
- docs/features/PAY-MP-002/ARCHITECTURE_REVIEW.md
- docs/features/PAY-MP-002/STATUS.md
- docs/architecture/adr/ADR-006-pay-mp-002-d204-risk-budget-and-stop-runtime.md

COMMANDS_RUN:
- 完整读取 AGENTS.md、agent-skills/architecture-agent/SKILL.md、agent-skills/RUNTIME_POLICY.md
- 读取产品/技术架构、changelog、边界、QA strategy、ADR-001～005、Change、PRODUCT_APPROVAL、PRD、DECISIONS、contracts/API、backend REQUIREMENTS/TASKS/ARCHITECTURE_REVIEW/TECH_DESIGN、QA/E2E/release evidence
- 只读核验当前工作树、D-204 相关代码、Outbox、OCPP StopTransaction、MeterValues 和 BE-211 capacity evidence

TEST_RESULTS:
- 未运行或修改业务测试；本任务为架构审查
- 复用已有独立 QA/E2E 证据；D-204 专项证据未形成，且 local capacity 明确 `production_capacity_claim=false`

CONTRACT_CHANGES:
- 未修改 PAY-MP-002-v1；记录 v2/vendor media-type refresh 提案、公共状态/错误/事件/兼容性要求
- 未修改数据库、迁移、业务代码、部署或生产配置

ARCHITECTURE_COMPLIANCE:
- C3；保持 ADR-002/003/004/005 的 PostgreSQL authority、Redis 非账务 authority、OCPP owner、Hosted boundary、tenant/RBAC、Decimal/UTC、Outbox 和 fail-closed 约束
- 当前目标架构 gate 为 `architecture-approved`；不是 implementation-ready 或 production-approved

RISKS:
- BLOCKER-D204-001 已解决：UTC rolling 24h、无午夜 reset、active/unresolved 计入、released/settled 排除
- D-204 contract/runtime/QA/E2E/capacity/Provider-unknown evidence 未闭合，均为后续 implementation/QA/release gates
- `PAYMENT_RAILS_ENABLED` 必须保持 false；生产 NO-GO
```
