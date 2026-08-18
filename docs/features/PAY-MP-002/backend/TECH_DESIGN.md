---
id: PAY-MP-002-BE-TECH-DESIGN
change_id: CHG-20260812-002
feature_id: PAY-MP-002
status: architecture-approved
contract_status: frozen
contract_version: PAY-MP-002-v2
compatible_contracts: P001-default, PAY-MP-002-v1
architecture_review: approved
implementation_authorization: phased-non-d204-only
owner: backend-agent
---

# PAY-MP-002 后端技术设计

## 1. 目标、门禁和不变边界

本设计把 ADR-005/ADR-006 accepted target 转换为可实现的后端方案。CF-201～CF-206 与 D-204-B v2 contract refresh 已冻结；`PAY-MP-002-v1` 作为兼容基线保留，BE-205 可按 `implementation-ready-for-BE205` 进入实现。该授权不包括部署、生产配置、QA 放行或真实资金。

产品已批准 D-201、D-202、D-203 Option 1、D-205-A、D-206-B、D-207-B、D-208-B、D-209-B 和 D-210-B。PAY-MP-001 的 A1/B1/C1/D1、Hosted Secure Fields、Invoice/Pricing/Charging/OCPP owner 保持不变。金额使用 Decimal/数据库 NUMERIC，时间保存 UTC，Provider payload 不泄漏为核心域模型。

D-204 runtime 仍未实现；本文件仅引用已冻结的 v2 contract，不授权本轮实现：

- D-204 的 COP、kWh、duration、unknown buffer、停止条件和 SLA 已在 v2 contract 固化为 approved projection inputs；实现仍必须使用服务端 pinned policy，不接受客户端覆盖；
- 不实现 risk ledger、reserve/consume/release、MeterValues 风险计数、RemoteStop threshold 或 hard-stop worker；
- BE-205 只保留为 blocked 设计输入；
- 真实资金发布和所有风险默认参数继续 no-go。

## 2. 后端模块与调用链

```text
App/Admin API
  -> Auth/Tenant/RBAC command scope
  -> Recovery / Refund / Reconciliation / Rail / Support service
  -> Billing/Charging read contracts + Payment Provider-neutral orchestration
  -> PostgreSQL typed facts + AuditLog + Outbox
  -> Provider adapter / wallet service / OCPP command owner
```

模块职责：

- `api/v1/app` / `api/v1/admin`：认证 audience、输入校验、HTTP/契约映射和安全错误；不负责跨域事务。
- `services/recovery`：RecoveryAttempt、PaymentAllocation、补缴目标和状态机；不重写 Invoice。
- `services/financial_eligibility`：唯一 D1 evaluator；只读取权威 facts，输出版本化决定。
- `services/refunds`：RefundCase、RefundApproval、RefundAttempt；Provider 调用通过 adapter；退款不等于 chargeback。
- `services/reconciliation`：canonical provider/EsLatin/funds facts、逐笔匹配、批次、差异和例外。
- `services/runtime_rails`：paid admission/payment creation 双轴和作用域；关闭不影响收敛流。
- `services/support`：SupportCase/CaseEvent/SLA/通知；不写 Payment、Invoice 或 D1。
- `payment_providers`：只实现 canonical capability 和 Provider reference；Mercado Pago/Wompi 等差异留在 adapter。
- `outbox_service`/workers：可靠副作用、lease/retry/DLQ/replay；不是最终财务事实。

## 3. Typed RecoveryAttempt 与 PaymentAllocation（AR-202）

### 3.1 权威数据模型候选

后续 migration 需新增以下 typed facts；本轮不创建表。

`RecoveryAttempt`：

| 字段 | 约束/语义 |
|---|---|
| `id`, `attempt_number` | UUID；同一 Invoice 内单调、唯一 |
| `app_user_id`, `invoice_id`, `session_id`, `tenant_id` | 服务端关联；AppUser 可跨运营租户，但 Invoice/Session/tenant 必须相互一致 |
| `method` | `wallet`、`new_card`、`saved_card`；不存 PAN/CVV/token |
| `provider`、`provider_account_ref` | canonical/provider-neutral 引用快照；当前 C1 可为 platform account ref |
| `target_amount`, `allocated_amount`, `currency` | 服务端从 Invoice 读取；COP Decimal；创建后不可由客户端修改 |
| `idempotency_key`, `request_fingerprint` | `(app_user_id, idempotency_key)` 唯一；同 key 不同 fingerprint 返回 conflict |
| `status`, `failure_code`, `unknown_reason` | 见状态机；只存安全 canonical code |
| `provider_operation_key`, `provider_payment_ref` | 每次外部副作用独立唯一 key/reference；不存完整 payload |
| `expires_at`, `created_at`, `updated_at`, `completed_at` | UTC；过期由 service/worker 收敛，不以客户端时间判断 |

`PaymentAllocation`：

| 字段 | 约束/语义 |
|---|---|
| `id`, `invoice_id`, `recovery_attempt_id` | typed 关联；attempt 必须属于同一 AppUser/tenant/Invoice |
| `amount`, `currency` | 只能等于本次分配目标；P002 只批准按账单全额补缴，不实现部分补缴 |
| `method`, `provider`, `payment_order_id`, `wallet_transaction_id` | 非敏感来源引用；钱包与卡都进入相同 allocation 模型 |
| `status` | `pending`、`committed`、`reversed`、`needs_review` |
| `winner_version`, `committed_at`, `reversal_reason` | 唯一赢家和后续 reversal 的审计事实 |

数据库唯一性候选：

- `RecoveryAttempt(app_user_id, idempotency_key)`；
- `RecoveryAttempt(invoice_id, attempt_number)`；
- `RecoveryAttempt(provider, provider_operation_key)`；
- `PaymentAllocation(recovery_attempt_id)`；
- 部分唯一索引 `PaymentAllocation(invoice_id) WHERE status='committed'`；
- `PaymentAllocation(invoice_id, status='pending')` 的并发策略由 service 锁和短期 lease 控制，不能靠客户端。

### 3.2 Recovery 状态机

```text
RecoveryAttempt:
created
  -> processing -> action_required -> processing
  -> provider_approved -> allocated
  -> declined | failed | expired | unknown
provider_approved -> duplicate_approved (已有 committed winner)

PaymentAllocation:
pending -> committed
committed -> reversed | needs_review
```

`provider_approved` 不是 D1 解锁；只有在同一 reconciliation transaction 中完成唯一 `committed` allocation、足额金额/币种校验和 Invoice ownership 校验后，attempt 才进入 `allocated`。任何 provider timeout、Webhook 乱序、资金未知、金额不匹配或 reconciliation mismatch 都进入 `unknown`/`needs_review`，不创建 committed allocation。

钱包路径在一次 PostgreSQL transaction 内锁 `AppUser`、Invoice 和候选 allocation，确认余额后写 wallet transaction、allocation 和 attempt；余额不足不产生负余额。卡路径的 Provider HTTP 调用在数据库锁外执行，依靠独立 provider operation key；回写时重新锁 attempt/Invoice，重复批准只产生 `duplicate_approved` 异常和可重放退款/人工队列。

### 3.3 公共投影与迟到重复批准（CF-201）

公共 adapter 只执行 `contracts/API.md` §3.10 的固定映射：`provider_approved→approved`、`committed→confirmed`、`needs_review→unknown`、`recheck_required→evaluating`。未知 domain state 统一映射 `unknown` 并审计，不能把 Provider 状态透传给 App/Admin。

当 Invoice 已有 `committed` winner 后收到另一 attempt 的批准：锁 Invoice/attempt，保留 winner/confirmed allocation，只把迟到 attempt 写为 `duplicate_approved`；不创建第二条 Allocation。公共投影固定为 `manual_review + reason_code=duplicate_approval + allocation=null`，建立唯一 reconciliation/refund/support work item 和 D1 recheck Outbox。相同 Provider fact 由 source reference/hash 唯一键重放为同一结果，不重复退款或通知。

## 4. FinancialEligibility / D1（AR-203）

### 4.1 唯一 evaluator

实现 `FinancialEligibilityEvaluator.evaluate(app_user_id, operation='paid_charging_admission')`，由 `/api/v1/app/charging/start` 和恢复完成后的 recheck 共同调用。它只裁决平台级财务资格，不读取 runtime rail；不得读取 `AppUser.has_unpaid_charges`、Redis/UI 或前端结果作为最终事实。

输入是 PostgreSQL 的可查询 facts：

- 当前用户所有 operator tenant 下的 open Invoice 和 session payment facts；
- RecoveryAttempt/PaymentAllocation 的 processing、unknown、allocated、reversed 状态；
- Payment/Provider late reversal、refund/chargeback/dispute、funds hold/release unknown；
- reconciliation mismatch、unmatched/expired exception；
- 已确认的账户财务状态。资源身份和 rail scope 不属于 evaluator 输入。

输出固定为：

| 输出 | 语义 |
|---|---|
| `eligible` | 无财务 blocking fact；不代表某个资源的 rail 可用 |
| `blocked` | 有明确阻断事实；返回安全 reason code 和 audit reference |
| `recheck_required` | 异步事实正在收敛，必须先刷新/反查；仍不能启动 |
| `unknown` | 权威事实不可证明，fail closed；进入 outbox/reconciliation |

可持久化 `FinancialEligibilityDecision` 快照用于审计/诊断，但它是可重建投影，不取代 Invoice/Allocation/Refund/Chargeback/Reconciliation authority。每次返回含 `decision_version`, `evaluated_at`, `blocking_fact_refs`（非敏感引用）和 `source_watermark`。

### 4.2 Scoped rail 与 charging preflight（CF-203）

`ChargingAdmissionPreflight.evaluate(app_user_id, qr_token, settlement_method)` 是组合服务，不是 FinancialEligibility 的别名：

1. 通过现有 QR authority 解析并校验 `operator_tenant_id/charge_point_id/site_id/connector_id`，读取 commissioned/asset/pricing；客户端不得提供 tenant/site/provider/scope；
2. 调用 FinancialEligibility evaluator 获得独立的 `eligible|blocked|recheck_required|unknown`；
3. 收费场景从 pricing/merchant context 推导 provider，再读取适用 platform/provider/tenant/site `paid_admission` controls；免费场景 rail 为 `not_applicable`；
4. 仅 `financial=eligible` 且 rail=`open|not_applicable` 返回 allowed；closed/unknown 均 fail closed。

`POST /app/charging/preflight` 用于 UX，但不签发能力 token。实际 `/app/charging/start` 在 claim PaymentIntent 或发出 RemoteStart 前必须重新执行同一组合逻辑；随后才执行 settlement/payment-intent 校验。FinancialEligibility reason code 不得出现 `rail_closed`，rail 错误固定为 `RAIL_CLOSED` 或 `RAIL_STATE_UNKNOWN`。

### 4.3 重新阻断规则

`allocated` 后才允许 evaluator 解除对应 Invoice 的阻断；同时必须聚合用户其他 Invoice。任何后续 `reversed`、chargeback hold/loss、late reversal、资金 unknown 或阻断级 reconciliation mismatch 都写入新 blocking fact，并通过 Outbox 触发 evaluator recheck。客户端刷新、回跳、单个 Webhook 或历史投影不能解锁或重新解锁。

## 5. Refund / Chargeback 双控（AR-204）

### 5.1 事实分离

- `RefundCase`：用户/运营提出的结构化退款问题，关联 Invoice/Payment/PaymentAllocation，不改原始金额；状态 `submitted`, `under_review`, `approved`, `provider_processing`, `partially_refunded`, `refunded`, `rejected`, `manual_review`。
- `RefundApproval`：精确 target amount、current version、initiator、approver、reason、decision、expires_at、audit reference；`initiator_id != approver_id`，同一身份不能绕过。
- `RefundAttempt`：每次 Provider operation 的独立 idempotency key、canonical status、Provider ref、requested/confirmed amount、unknown/error reason；不使用 metadata summary 作为 authority。
- `ChargebackCase`：独立记录 dispute/hold/representment/lost/won/reversed 等 Provider-neutral 状态、截止日、资金影响和证据 reference；拒付不能映射为退款。

全额/部分退款的请求金额由服务端读取实付与累计已退 facts；`requested_amount <= paid_amount - confirmed_refunded_amount`，累计不超过实付。Provider unknown 不更新为完成；只有 Provider confirmed fact 才可提交资金/Invoice 投影变化。钱包充值退款继续先锁余额，余额不足进入人工状态，不创建负余额。

### 5.2 双控事务

1. initiator 创建或复用 `RefundCase`，服务端从资源 owner 推导 tenant，保存 request fingerprint 和审计；不直接调用 Provider。
2. approver 读取 versioned case，确认金额/原因/范围，使用一次性 approval intent；必须不同身份且拥有相应 resource/platform scope。
3. worker 获得 `RefundAttempt` lease 后调用 Provider adapter；Provider response 不直接改变 Invoice/D1。
4. active query/replay 确认累计退款事实后，在短事务内提交 RefundAttempt、RefundCase、Invoice/Payment projection 和 Outbox；失败/unknown 保留可重放状态。

## 6. 三方对账（AR-205）

### 6.1 Typed facts

- `ReconciliationRun`：`business_date_bogota`, `run_type=continuous|daily`, `status`, `cutoff_at`, `closed_at`, `source_watermarks`, `version`。
- `ReconciliationItem`：EsLatin reference（Invoice/Payment/Allocation/Refund/Chargeback）、Provider reference、actual funds reference、amount/currency/merchant/tenant/fee/refund/hold/release 状态和 `match_status`。
- `ReconciliationException`：差异类别、差异金额、owner、severity、due_at、escalation、resolution、temporary_exception_until、finance_approver、platform_approver。

匹配状态候选：`matched`, `pending`, `mismatch`, `manual_review`, `closed`。金额、币种、merchant、tenant、duplicate、unmatched funds 和 provider/payment reference mismatch 是阻断级；仅 timing/fee/funds-release timing 可进入最长 24 小时临时例外，必须 finance 与 platform 两个不同授权主体批准并有到期时间。Bogotá 前一营业日的 run 由下一工作日 12:00 前关闭；工作日历由 Operations/Finance 提供，不由代码默认猜测。

### 6.2 写入与重放

Provider webhook、主动查询和资金文件先转为 canonical facts，再按 source/reference/hash 去重，写入 item/exception/outbox。重复同一 source fact 返回原结果；同 reference 不同金额/币种/merchant 的 payload 永远创建 conflict，不覆盖旧事实。批次按 cursor/watermark 分段，支持 bounded replay；replay 不重新发起支付/退款，只重新计算 matching。

## 7. 双轴 Runtime Rail Control（AR-206）

`RuntimeRailControl` 只表达运营关闭，不表达 D-204 风险：

| 字段 | 语义 |
|---|---|
| `axis` | `paid_admission` 或 `payment_creation` |
| `scope_type/scope_ref` | `platform`, `provider`, `tenant`, `site`；scope 由服务端解析 |
| `state/version` | `open`, `closed`; 每次写入 optimistic version |
| `reason`, `incident_ref`, `effective_at`, `expires_at` | 必填的操作上下文；不使用隐含默认期限 |
| `closed_by`, `closed_at`, `reopened_by`, `approved_by` | close 单人；reopen 必须不同人批准 |
| `health_check_ref`, `audit_ref` | 恢复前可验证健康检查与审计证据 |

规则：

- `paid_admission` 关闭阻止新的收费 RemoteStart preflight；`payment_creation` 关闭阻止新的 Provider payment/recovery creation。已创建的 PaymentOrder/RecoveryAttempt 不被删除。
- Webhook、主动查询、退款、拒付、对账、历史、支持和 StopTransaction 继续收敛；payment rail close 不自动 RemoteStop 活跃会话。
- close 失败/网络 unknown 不视为已关闭；reopen 失败/unknown 不视为已恢复；不自动 reopen。
- 作用域重叠按最具体匹配；任一适用 scope closed 即 fail closed。provider 由服务端 PaymentOrder/merchant context 推导，不能由客户端传入。

## 8. 结构化 Support（AR-207）

`SupportCase` 取代 P002 对 `SupportMessage` 的新依赖，旧消息只作兼容历史：

- 关联 `app_user_id`、推导 `tenant_id`、`invoice_ref`, `session_ref`, `payment_ref`, `refund_case_ref`, `chargeback_case_ref` 和 `rail_incident_ref`；均为非敏感 reference。
- `category`：`unpaid`, `payment_failed`, `duplicate_charge`, `refund_delayed`, `chargeback`, `cannot_stop`, `amount_mismatch`, `other`；`status`：`open`, `acknowledged`, `in_progress`, `waiting_user`, `resolved`, `closed`。
- `CaseEvent` append-only 记录状态、责任人、内部/用户可见标记、reason、audit reference 和时间；客服不能改写 Invoice/Payment/D1。
- 记录首次人工响应目标 1 工作日、决定目标 3 工作日的 SLA 目标/实际时间；营业时段紧急支持为单独 capability/status，不凭空声称 24/7。
- 邮件通知由 Outbox 发送，失败可重试；通知只携带非敏感 case reference 和安全链接。

## 9. Provider-neutral orchestration（AR-208）

核心只依赖以下 canonical capability：

```text
create_recovery_payment(command, merchant_context, idempotency_key)
query_payment(provider_ref, merchant_context)
create_refund(command, merchant_context, idempotency_key)
query_refund_facts(provider_ref, merchant_context)
ingest_dispute_fact(canonical_fact)
ingest_funds_fact(canonical_fact)
```

`command` 只含 amount/currency/merchant snapshot/purpose/non-sensitive references；Provider adapter 自己处理 SDK 字段、credential、3DS/next action 和 raw payload 清洗。核心状态只使用 `processing`, `action_required`, `provider_approved`, `allocated`, `declined`, `unknown`, `refunded`, `disputed`, `mismatch` 等 canonical facts。

当前实现继续使用 Mercado Pago automatic Payments/Hosted boundary；不在 P002 引入 authorize/capture/void、分账、费用或新 Provider。任何未来 Provider 不应要求修改 Invoice、FinancialEligibility、Recovery、Refund、Reconciliation 或 UI 核心状态机。

## 10. Schema、兼容、事件和回滚（AR-209）

### 10.1 Additive schema 候选

新增 typed tables：`recovery_attempts`, `payment_allocations`, `financial_eligibility_decisions`（可重建快照）、`refund_cases`, `refund_approvals`, `refund_attempts`, `chargeback_cases`, `reconciliation_runs`, `reconciliation_items`, `reconciliation_exceptions`, `runtime_rail_controls`, `support_cases`, `support_case_events`。必要时增设 `provider_facts`/`funds_facts` canonical source tables；不得把完整 Provider payload 直接放入公共事实。

所有表至少有 UUID、tenant/resource ownership、schema_version、created/updated UTC、状态约束和审计 reference。金额为 NUMERIC/Decimal；唯一键、外键、partial unique indexes 和 status CHECK 必须在 migration 中显式建立。

### 10.2 Event/Outbox 候选

```text
recovery.attempt.created / state_changed
payment.allocation.committed / reversed
financial.eligibility.recheck_requested / evaluated
refund.case.submitted / approved / state_changed
chargeback.fact.received / state_changed
reconciliation.item.matched / exception_opened / exception_closed
rail.control.closed / reopen_requested / reopened
support.case.created / state_changed / notification_requested
```

当前 `OutboxEvent.tenant_id` 是 `NOT NULL`，唯一键是 `(tenant_id,idempotency_key)`；这不能承载 platform rail、跨租户 D1 和平台 reconciliation。P002 固定采用同表 additive scope，不建立平行 outbox：

- 新增 `scope_type tenant|platform NOT NULL` 与 `scope_ref NOT NULL`；tenant ref 为 `tenant:<uuid>`，platform ref 只能为 `platform:eslatin`；
- 将 `tenant_id` 放宽 nullable 并保留 FK；DB CHECK 要求 tenant scope 的 ref 与 tenant_id 严格一致，platform scope 的 tenant_id 必须 NULL；
- 现有行确定性回填 tenant scope；唯一键切换为 `(scope_type,scope_ref,idempotency_key)`；
- 禁止 all-zero UUID、系统租户或借用任一真实 tenant；worker 用 scope_type/ref 取 lease、重放和统计。

事件 payload 只含 canonical IDs、真实业务 resource refs、amount/currency（必要时）、status/version、reason code 和 audit reference。Outbox delivery scope 与业务资源 scope 分开验证；unique key 为 aggregate+event version 或明确 operation key；worker 具有 lease、attempt count、bounded retry、dead-letter、replay 和指标。

### 10.3 混合版本与 rollback

迁移采用 expand → dual-read/validate → new-write → cutover → contract exposure；旧 P001 endpoint 保持兼容读取。P001 的 `PaymentOrder.metadata` 只保留兼容摘要，不能由新代码继续写 P002 authority。回滚仅关闭 P002 write/read exposure 和 rail scope，保留财务事实，未知状态 D1 fail closed。

`/api/v1/app/transactions` 继续只通过 `Accept: application/vnd.eslatin.pay-mp-002.v1+json` 协商既有 P002 projection；无 header、`application/json` 或 `*/*` 始终走当前 P001 bare array + offset/limit + number/null 类型。D-204 safe projections 只通过 `Accept: application/vnd.eslatin.pay-mp-002.v2+json`，响应设置 `Vary: Accept`；禁止 query/body/另一 header 作为第二版本机制。三个 projection adapter 对同一 authority 分别做 golden response 测试。

## 11. 事务、唯一性、幂等、租户/RBAC

### 11.1 事务边界

- 创建 recovery attempt：校验当前用户/Invoice ownership、锁 Invoice 读取当前 outstanding、校验 rails/available methods、写 attempt+audit+outbox；不调用 Provider。
- Wallet allocation：同一短事务锁 AppUser、Invoice 和 allocation winner；余额、wallet transaction、allocation、attempt 和 D1 recheck event 原子提交。
- Card allocation：Provider call 由 worker lease 独立执行；回写时锁 attempt/Invoice，校验 provider fact、merchant/tenant/amount/currency 和当前 winner，再提交 allocation。
- Refund/rail/approval：状态 version 乐观并发检查；审批和执行不共享长事务；Provider call 不持有业务行锁。
- Reconciliation：source fact 去重、item 更新、exception 开闭和 release of temporary exception 在一个短批次事务内完成；daily close 只在所有 item/exception 条件满足时允许。

### 11.2 租户和 RBAC

- AppUser 是平台身份；App 读取/写入必须按 `app_user_id` + Invoice/Session owner 过滤，不能接受客户端 tenant/merchant/amount/status。
- Admin 的 tenant 从 Invoice → Session/Site/ChargePoint 或 PaymentAllocation 可信关联推导；跨租户平台操作必须是显式 platform scope，并有审计。`X-Tenant-Id` 仅是选择上下文，不是授权事实。
- Admin 权限名固定为：`payment.read`, `refund.request`, `refund.approve`, `chargeback.read`, `reconciliation.read`, `reconciliation.resolve`, `reconciliation.exception.request`, `reconciliation.exception.approve`, `support.manage`, `rail.read`, `rail.close`, `rail.reopen.request`, `rail.reopen.approve`, `audit.read`。每个 endpoint 的唯一 permission/HTTP/body/sort 见 `contracts/API.md` §6；不得由实现自行改名或选择替代状态码。
- refund approve、reconciliation temporary exception approve、rail reopen 必须 initiator != approver；平台/finance/tenant scope 由后端校验，隐藏 UI 不构成安全边界。

## 12. 写入压力、队列和数据库健康

- Recovery/Refund/Rail/Support 是低频业务 facts；每个业务操作最多写入 authority、audit 和必要 outbox，不在请求链写 Provider 原始 payload。
- Webhook/Provider query/资金文件采用 bounded queue + lease + retry/DLQ；同一 source reference 去重，避免重复主动查询放大。
- Reconciliation daily run 使用 cursor/watermark 分批；索引覆盖 `business_date`, `status`, `tenant_id`, `provider`, `reference`，避免全表锁和一次性内存加载。
- `/charging/start` 的 D1 evaluator 只执行受索引覆盖的 existence/aggregate 查询；不对每个 session 产生 N+1 查询，不读取 Redis 作为 authority。FinancialEligibility 快照/通知异步化。
- 不新增 Heartbeat/MeterValues 永久逐条写入；遵守 ADR-003 的实时快照+受控采样。Redis 丢失只触发重建/重查，不改写已结清事实。
- 实现 QA 必须测量并记录 lock wait、DB pool、queue lag、retry/DLQ、Webhook burst、daily batch throughput、索引命中和 Redis fallback；本设计不承诺未经压测的 TPS/p95，也不把 D-210 样本量当成容量或风险预算。

## 13. QA/E2E 接口与验收约束（AR-210）

Backend QA 必须独立覆盖：

- Recovery：同 Invoice 钱包/新卡/saved-card、并发创建、相同/冲突 idempotency、重复回跳/Webhook、provider timeout、duplicate approved、唯一 allocation、原 Invoice 不可变、D1 recheck/re-block。
- Refund/chargeback：initiator/approver 分离、全额/部分累计上限、Provider unknown/replay、钱包余额不足、chargeback 不替代 refund、late reversal 重新阻断。
- Reconciliation：三方匹配、金额/币种/merchant/tenant mismatch、重复/乱序/不同 payload、daily cutoff、24h 双人临时例外到期、bounded replay。
- Rail/Support/RBAC：双轴 scope、close/reopen 双控、不自动 reopen、不强停会话、邮件 Outbox、App/Admin audience、跨租户负例、审计和敏感日志。
- 数据完整性：migration 空库/既有库/混合版本、FK/unique/status check、孤儿/负钱包/重复 allocation、Redis 丢失、Outbox lease/DLQ。

E2E 仅在 backend/frontend QA 通过后，由 e2e-agent 从用户旅程验证：D1 阻断 → 账单 → 按账单补缴 → Hosted/wallet 恢复 → 服务端 eligibility → 重新开始；历史/退款/拒付/支持；Admin 双控/对账/rail close-reopen；Provider Webhook/主动查询和 OCPP StopTransaction 收敛。未知状态不得判 PASS。

## 14. 禁止项与实现前置条件

禁止：

- 以 `metadata`、Redis、日志、UI 或单个 Webhook 作为财务/D1 authority；
- Payment 直接修改 OCPP/ChargingSession；Support/Admin 直接改金额或终态；
- 在 `/charging/start` 内新增 D-204 风险计数/硬停止；
- 引入 Provider authorization/capture/void、C2 分账、收据文件或部分补缴而不重开产品/架构门禁；
- 把当前 superadmin-only、`PAYMENT_RAILS_ENABLED` 或旧 refund summary 描述为 P002 完成。

CF-206 同版本同步、architecture-agent 限定复审和 frozen API/event contract 已完成。后续分批实施仍必须遵守 additive migration/rollback、逐项 handoff、独立 QA 和适用 E2E 计划。`PAYMENT_RAILS_ENABLED` 继续保持 false，生产 no-go。

## 15. 统一交接

STATUS: done

CHANGED_FILES:
- docs/features/PAY-MP-002/backend/TECH_DESIGN.md

COMMANDS_RUN:
- 只读读取治理、ADR、Change、P001/P002 文档及 QA strategy
- 只读核验 `csms/app/database/models.py`、billing/session/charging/payment/refund/reconciliation/Provider/RBAC/tenant/outbox/OCPP/migrations 与当前 diff

TEST_RESULTS:
- 本文件仅同步既有 architecture-agent gate；不代表 QA 或生产通过

CONTRACT_CHANGES:
- contract 现为 `PAY-MP-002-v2 / frozen`；`PAY-MP-002-v1` 与 P001 default compatibility 保持

ARCHITECTURE_COMPLIANCE:
- C3；遵守 ADR-003/004/005、BACKEND_BOUNDARIES、P001 A1/B1/C1/D1、Decimal/UTC、tenant/RBAC、Outbox 和 production-no-go
- D-204 未扩展为风险运行时；BE-205、默认风险参数和真实资金保持 blocked

RISKS:
- BE-201 独立 QA 失败项修复后仍需 fresh independent re-QA；BE-202 及后续未实施
- Provider sandbox、数据库容量和真实资金验证未执行；不能由技术设计替代 QA/E2E 或人工放行

## D-204-B v2 contract reference

- Backend must consume the frozen v2 definitions for RiskSession/RiskStop/ProviderResolution, risk decision/status/errors, UTC rolling 24h aggregate semantics, expected_version/idempotency, and `risk-event.v2` internal events.
- Scope, tenant, amount, policy version, attempts, timeout and stop/provider results remain server-derived. Unknown authority fails closed; persisted Provider unknown is projected safely and converges for 24 hours without duplicate create.
- This document does not implement BE-205, endpoints, migrations, workers, OCPP commands or deployment configuration.
