# PAY-MP-002 C3 最终代码架构审核

## 1. Verdict

**Verdict: `approved`**

产品门禁已经通过：D-201、D-202、D-203、D-205-A、D-206-B、D-207-B、D-208-B、D-209-B 和 D-210-B 均有明确的 Product Owner 批准记录。D-204 曾移入 TODO；本次复审已按窗口方案 A 重开，详见第 11 节。

本次没有发现需要 Product Owner 再次选择的产品问题。CF-201～CF-206 已形成唯一、前后端一致且可实施的 `PAY-MP-002-v1`，共享契约可以冻结。

目标架构在 ADR-005 中接受。本次第二次且最后一次限定复审确认：状态映射、P001/P002 media-type 兼容、FinancialEligibility/scoped rail preflight、platform Outbox scope、Admin permission/HTTP/sort/error/CSV 以及前后端统一版本均已闭合。非 D-204 分批任务进入 `architecture-approved / implementation-ready`。这只授权按依赖顺序实施，不表示代码已实现、QA 已通过或生产 GO。D-204-B 目标架构现为 `architecture-approved`，但仍单独阻塞实现、契约、QA/E2E、容量和生产门禁：

- BE-205 风险预算账本、计数器、阈值判断和运行时 worker；
- v2 contract refresh 及其前后端兼容性证据；
- 任何真实资金 R2/R3/R4 发布。

## 2. 审核范围与证据

本审核读取了根治理规则、architecture-agent 技能、产品/技术架构及 changelog、后端/前端边界、QA 策略、ADR-001～ADR-005、CHG-20260812-002、PAY-MP-001/PAY-MP-002 产品、契约、设计、任务和状态文档，并检查了当前工作树、相关 Git diff 和实际代码。

重点代码证据包括：

- 数据与账务：`csms/app/database/models.py`、`billing_service.py`、`pricing_service.py`；
- 支付：`payment_checkout/service.py`、`payment_reconciliation.py`、`payment_refunds.py`、Provider adapter/merchant context；
- App/Admin API：wallet、charging、payment checkout、payment methods、payments、admin payments、transactions；
- OCPP：session service、message handler、meter telemetry、outbox 和 control API；
- 权限/租户/配置：auth、permissions、tenant middleware、role/config service；
- App/Admin：欠费页、充电历史、支付状态、支付订单与设置页面。

本次只进行了静态架构与语法核验，没有修改或执行任何业务数据、数据库、迁移、部署或生产配置。

### 2.1 SELF_CHECK（Mandatory Self-Correction Loop）

- **原始任务：** 在第二次且最后一次重大自我修正后，只复审 CF-201～CF-206 修订及直接代码证据，并裁决 `PAY-MP-002-v1` 是否可冻结。
- **当前活动：** 已逐项核对六项 closure、前后端版本引用和 P001/Outbox/Charging 直接代码边界，准备同步最终架构门禁。
- **直接推进性：** 是；所有读取和裁决都直接服务于 contract freeze，没有重做全量搜索。
- **新证据/状态：** CF-201～CF-205 后端候选已唯一化，CF-206 前端无分叉消费；现有 P001 `/app/transactions` 仍为 bare array/offset/number-null，现有 Outbox 仍为 tenant-only，现有 Charging 仍为旧 D1，证明冻结内容是兼容、additive 的待实现目标而非伪称现状。
- **是否重复读取：** 否；只重载明确要求的治理文件，并复用上一轮 review manifest 后定向读取修订片段。
- **是否扩 scope：** 否。未修改 backend/frontend 专用设计、业务代码、数据库、迁移、部署或生产配置。
- **障碍分类：** 六项 freeze blocker 已关闭；D-204 是已隔离 TODO，不属于本次批准范围。
- **最小下一动作：** 冻结 `PAY-MP-002-v1`，把非 D-204 分批任务标记为 implementation-ready，并停止架构搜索。
- **重大 self-correction 次数：** 2/2（本任务最终一次；不生成第三轮）。
- **Completion criterion：** 原始范围已保留；无 unresolved scope drift、重复分析循环或隐藏治理冲突；六项 closure 均有唯一契约和直接证据；剩余 blocker 仅为已记录的实现/QA/生产门禁及 D-204；当前 `approved` gate 有证据支持；下一允许动作是按 frozen contract 分批实现。

## 3. 当前代码事实与裁决

| 边界 | 当前实际代码 | 架构裁决 |
|---|---|---|
| Billing authority | `Invoice.session_id` 唯一，金额来自服务端 PricingSnapshot；Billing 对 Session/Invoice 加锁。 | Owner 正确，继续作为原始应收权威；P002 不得改写用量、价格快照或原账单。 |
| 钱包补缴 | `pay_unpaid_charge` 按 Invoice 金额加锁扣款并写 Payment/ledger。相同幂等请求在部分异常状态下不能稳定重放既有结果。 | 可复用结算内核；必须置于 typed RecoveryAttempt/Allocation 下并修正重放语义。 |
| 卡补缴 | Checkout 已支持 `UNPAID_CHARGE`、新卡/保存卡候选和服务端金额；Invoice/tenant/session/attempt 关联主要位于 `PaymentOrder.metadata`。 | Hosted/Provider 边界可复用；metadata 不能成为 P002 财务 owner，必须增加 typed relation/facts。 |
| Provider | 有 create/status/refund adapter、merchant context 和 credential resolver；核心仍含 MP/Wompi 分支及 provider-specific ID。 | 允许 Mercado Pago 作为当前 adapter；P002 orchestration、状态与操作不能硬编码 Provider，未来 Provider 扩展不得重写 Billing/D1。 |
| Reconciliation | MP 可主动查询并收敛单笔 PaymentOrder；Webhook 有基础去重。重复 approved/退款摘要主要写 metadata。 | 不满足 D-207-B 的三方批次、差异、例外、截止时间、重放和资金事实，必须独立建模。 |
| Refund/chargeback | Provider 累计退款事实有查询与幂等保护；Admin superadmin 可直接调用退款；本地摘要在 metadata；无 Chargeback typed facts。 | 不满足 D-206-B 双人控制、结构化状态和重新阻断。直接退款 endpoint 不能作为 P002 最终流程。 |
| D1 | `/charging/start` 从 PostgreSQL 跨租户检查 pending Invoice/completed-unpaid Session。 | 保留 P001 基线；必须集中为 FinancialEligibility evaluator，并纳入退款、拒付、late reversal、unknown 和对账差异。 |
| History | App 已有基础 Charging history/detail、Invoice number/amount/status；欠费页存在但入口仍按旧范围隐藏。 | D-205-A 可基于查询投影实现，不强制新 read-model；必须补充 Payment/Refund/Dispute 安全状态与支持入口，不能生成未批准收据。 |
| Support | 只有简单 `SupportMessage` 的 message/reply/pending/replied。 | 不足以承载 D-206-B/D-209-B 的上下文工单、分类、SLA、责任人、状态和关联事实。 |
| Admin/RBAC | 支付列表、对账和退款目前为 platform superadmin-only；无 refund/reconciliation/rail 细粒度权限和审批意图。 | superadmin-only 是安全基线，不是目标。资源租户范围和平台级动作必须显式分权。 |
| Rail control | 后端/前端只有部署环境总门禁；没有平台/Provider/tenant/site 范围、版本、关闭/恢复审批或健康清单。 | 不满足 D-208-B。必须新增服务端权威的 paid-admission 与 payment-creation 双轴 control。 |
| OCPP | Charging/OCPP 拥有 RemoteStart/Stop、Start/StopTransaction、MeterValues；RemoteStop accepted 不等于已停止。 | Owner 正确。已批准范围不得让 Payment 直接控制 socket；D-204 未批准前不得实现风险 stop runtime。 |
| Events/idempotency | OCPP/Session 已有 Outbox 和去重；支付链以同步事务、Webhook 记录和 Provider 幂等为主。 | 跨 Payment/Billing/D1/Operations 的异步副作用必须复用受控 Outbox/worker，不能以 UI、Redis 或日志代替事实。 |

## 4. 接受的目标架构

### 4.1 Domain owner

- **Billing**：Invoice、PricingSnapshot、原始应收、最终金额；原账单不可由恢复、退款或客服修改。
- **Payment Recovery**：RecoveryAttempt、支付方式选择、客户端幂等、PaymentOrder/Wallet 关联和 attempt 状态。
- **Payment Allocation/Reconciliation**：Provider payment/refund/chargeback/资金/对账事实与 Invoice allocation；只有足额且已收敛的 allocation 可参与 D1。
- **Financial Eligibility**：以 PostgreSQL 权威事实计算 `eligible / blocked / recheck_required / unknown`；Charging 只执行该决定。
- **Charging/OCPP**：Session、MeterValues、RemoteStart/Stop、Start/StopTransaction；支付域不能改写设备事实或持有 socket。
- **Operations**：退款审批、对账例外、rail control、支持工单和审计；AuditLog 记录证据但不替代业务状态。
- **App/Admin projections**：只展示服务端事实，可重建且不得拥有结算、D1、租户或权限判断。

### 4.2 最小事实集合

实现可以合并物理表，但必须保留以下独立 typed 语义、状态机、唯一键和审计，不得只放在 JSON/Redis：

1. `RecoveryAttempt` 与 `PaymentAllocation`：绑定 AppUser、Invoice、tenant、server amount/currency、method、idempotency、PaymentOrder/Wallet 和最终赢家。
2. `RefundCase/RefundAttempt/ApprovalIntent`：用户问题/退款请求、发起人、不同批准人、金额、Provider 操作、累计退款和结果。
3. `Chargeback/DisputeObservation`：拒付、资金扣回/恢复、状态来源和 D1 影响。
4. `ReconciliationRun/Item/Exception`：EsLatin、Provider、实际资金三方匹配，批次截止、差异、24 小时例外和双人批准。
5. `RailControl/ApprovalIntent`：paid charging admission 与 payment creation 两轴，平台/Provider/tenant/site scope、版本、原因、关闭者、不同恢复批准人和检查结果。
6. `SupportCase/CaseEvent`：上下文引用、类别、状态、SLA、责任人和通知结果；不得包含 PAN、CVV、证件号、card token 或密钥。

D-205-A 的基础历史优先使用权威表的查询投影；只有性能/查询复杂度证明确有需要时再建立可重建 read model。

### 4.3 状态与幂等不变量

- 客户端金额、tenant、merchant 和最终状态不可信；金额均为 Decimal/COP，时间持久化为 UTC。
- 相同用户、相同 idempotency key、相同目标返回同一业务结果；相同 key 不同目标/金额拒绝。
- 同一 Invoice 可以有多次 attempt，但只能有一个最终足额结算 allocation。迟到或并发第二个 approved 必须进入 duplicate/manual-review/refund-required。
- Provider `approved`、回跳成功、Webhook processed、Redis 状态或页面展示均不能直接解锁 D1。
- `processing/action_required/unknown/mismatch/refund pending/chargeback` 默认 fail closed。
- 所有支付、退款、拒付、对账、审批和 rail-control 状态迁移必须有版本检查、幂等和不可覆盖的审计关联。

### 4.4 D1 与重新阻断

唯一服务端 evaluator 必须基于用户全部 blocking financial facts 计算资格：

```text
eligible only if every blocking Invoice has a final full allocation
  and amount/currency/merchant/tenant ownership match
  and no payment/refund/chargeback/reversal/reconciliation unknown or mismatch exists.
```

退款、拒付、Provider late reversal、资金状态 unknown 或对账差异必须可重新阻断。App 只能根据服务端响应展示原因和入口；Charging `/start` 仍是执行充电准入的唯一服务端门禁。

### 4.5 Provider 与 OCPP 边界

- 保持 ADR-004 Hosted Secure Fields，卡和证件敏感数据不进入 App、普通 API、数据库、日志或支持工单。
- Provider-specific API/ID 只能存在于 adapter 和 provider reference 层；Recovery、Refund、Reconciliation、D1 和 Admin 契约使用 canonical 语义。
- PAY-MP-002 当前继续采用 D-203 方案 1：StopTransaction/最终 MeterValues → 准确 Invoice → 支付/恢复，不引入 authorize/capture/void。
- 方案 2 仅为未来候选；不得从当前 `approved` 状态推断 authorization。
- D-204 目标架构虽已批准，但在 v2 contract、BE-205 和独立 QA/E2E 门禁完成前，任何 risk reservation、MeterValues 风险计数、RemoteStop 阈值或 hard-stop worker 都不得进入运行时。

## 5. 批准的实施约束

| ID | 必须修改 | 验收约束 |
|---|---|---|
| AR-201 | 刷新 backend/frontend 架构审核、技术设计和 TASKS，并冻结共享契约 | 删除“D-205～D-210 未批准”的过期前提；合同必须覆盖状态、错误、权限、幂等、分页和兼容，不得由前后端各自发明。 |
| AR-202 | 建立 typed RecoveryAttempt/Allocation | 不再从 `PaymentOrder.metadata` 推导 Invoice owner、attempt identity 或 D1；钱包与卡共享恢复状态机。 |
| AR-203 | 集中 FinancialEligibility/D1 evaluator | `/charging/start` 调用同一 evaluator；退款、拒付、late reversal、unknown、对账差异可重放地 re-block。 |
| AR-204 | 建立 D-206-B refund/dispute workflow | 退款发起人与批准人不同；全额/部分退款累计不超实付；Provider 调用不能由单一 Admin 直接完成。 |
| AR-205 | 建立 D-207-B reconciliation domain | 逐笔持续匹配 + Bogotá 营业日批次；三方事实、差异、截止、24h 例外、双人批准和批量写入预算可查询。 |
| AR-206 | 建立 D-208-B runtime rail control | paid admission/payment creation 双轴，作用域、版本、关闭、不同人员恢复、健康清单和审计明确；关闭不停止 Webhook/查询/退款/对账/历史/支持，也不自动强停活跃会话。 |
| AR-207 | 建立 D-209-B contextual support | 工单从 D1/账单/支付/退款/充电带入非敏感引用，支持 SLA/责任人/邮件通知/实时紧急渠道状态。 |
| AR-208 | Provider-neutral 化 P002 orchestration | Mercado Pago 保持 adapter；新 Provider 不要求改 Invoice、D1、Recovery、Refund、Reconciliation 或 UI 核心状态机。 |
| AR-209 | 完成 additive schema/compatibility/rollback 设计 | 即使无历史业务导入，也必须有版本化 schema migration；不伪造历史 refund/chargeback/risk facts。回滚关闭新入口、保留财务事实、D1 fail closed。 |
| AR-210 | 完成 QA/E2E/发布门禁 | 覆盖重复/乱序、并发、跨租户、双控、三方对账、rail close/reopen、OCPP 收敛；R0～R4 每级单独验收和人工晋级。 |

### 5.1 本次复审裁决矩阵

| ID | 设计复审结果 | 最终 gate |
|---|---|---|
| AR-201 | 前后端统一引用 `PAY-MP-002-v1`，共享契约覆盖状态、错误、权限、幂等、分页和兼容 | `architecture-approved / implementation-not-started` |
| AR-202 | typed RecoveryAttempt/Allocation、唯一赢家、钱包/卡统一模型可行 | `architecture-approved / implementation-not-started` |
| AR-203 | evaluator/re-block 与 scoped rail 已分层；preflight 由服务端解析资源，`/charging/start` 重算 | `architecture-approved / implementation-not-started` |
| AR-204 | Refund/Approval/Attempt 与 Chargeback 分离、不同人员审批可行 | `architecture-approved / implementation-not-started` |
| AR-205 | 连续匹配、Bogotá 日批次、typed exception 与临时例外可行 | `architecture-approved / implementation-not-started` |
| AR-206 | 双轴、作用域、单人 close/不同人员 reopen 的模型及 platform Outbox 交接已闭合 | `architecture-approved / implementation-not-started` |
| AR-207 | SupportCase/CaseEvent 非敏感上下文边界可行 | `architecture-approved / implementation-not-started` |
| AR-208 | Provider-neutral owner 与 domain/public 状态映射已冻结 | `architecture-approved / implementation-not-started` |
| AR-209 | additive/rollback、P001/P002 media-type compatibility 与单表 Outbox scope 已冻结 | `architecture-approved / implementation-not-started` |
| AR-210 | QA/E2E/R0～R4 门禁已建模且 D-204 隔离正确 | `architecture-approved / implementation-not-started` |

### 5.2 CF-201～CF-206 关闭证据

1. **CF-201 — closed：** §3.10 冻结 `provider_approved→approved`、`committed→confirmed`、`needs_review→unknown`、`recheck_required→evaluating`，并定义 unknown fallback 与迟到重复批准 `manual_review/duplicate_approval/allocation=null`。
2. **CF-202 — closed：** 唯一协商机制是 `Accept: application/vnd.eslatin.pay-mp-002.v1+json`；默认 P001 保持 bare array、offset/limit 和 number/null，P002 才使用 cursor/decimal string，并固定 406/400/Vary 行为。
3. **CF-203 — closed：** FinancialEligibility 只表达平台级财务资格；`/charging/preflight` 由 QR 解析资源/scopes 并组合 rail；`/charging/start` 重新执行组合 preflight，客户端结果不是 capability token。
4. **CF-204 — closed：** 单表 additive Outbox 固定 `scope_type/scope_ref`、nullable tenant、DB CHECK 和 scope 唯一键；platform 使用 `tenant_id=NULL, scope_ref=platform:eslatin`，禁止 dummy tenant。
5. **CF-205 — closed：** §6/§7 冻结 permission strings、Projection 字段、endpoint HTTP/body、stable sort、canonical errors 和唯一 CSV 生命周期/一次性下载。
6. **CF-206 — closed：** backend/frontend 均只引用 `PAY-MP-002-v1`；backend 文档中的 `pending-frontend-sync` 是复审前交接快照，不构成第二套版本或语义，当前有效状态以 frozen contract、总 review 和 `STATUS.md` 为准。

### 5.3 完成标准证据

- `contracts/API.md` 已冻结为唯一 `PAY-MP-002-v1`；不存在候选 permission、HTTP 二选一或 CSV “A 或 B”语义。
- 对现有 `/transactions` 的 P001 array/offset 客户端与 P002 cursor 客户端分别有契约测试计划，且字段类型不发生静默破坏。
- domain→public 状态映射表覆盖 Recovery、Allocation、Eligibility、Refund、Reconciliation、Approval、Rail、Support 的 unknown/迟到/冲突路径。
- scoped rail 的 resource 解析和 platform/tenant Outbox 数据约束可由 migration/服务测试验证。
- backend/frontend 文档引用同一 `PAY-MP-002-v1`；没有任何获授权实现任务包含 D-204、BE-205、风险默认值、风险 UI/runtime 或真实资金发布。

## 6. 租户、RBAC 与审计

- AppUser 的 D1 是平台级跨运营租户资格；Admin 读取和动作必须从 Invoice/Session/Payment/站点资源推导 tenant scope。
- 普通 tenant Admin 不得查看或操作其他租户，不得使用客户端 `tenant_id` 扩权。
- 权限固定为 `payment.read`、`refund.request`、`refund.approve`、`chargeback.read`、`reconciliation.read`、`reconciliation.resolve`、`reconciliation.exception.request`、`reconciliation.exception.approve`、`support.manage`、`rail.read`、`rail.close`、`rail.reopen.request`、`rail.reopen.approve`、`audit.read`，并由服务端裁决 platform/tenant/resource scope。
- D-206-B 退款：initiator != approver。D-207-B 临时例外：finance initiator 与 platform approver 分离。D-208-B：一人可关闭，恢复必须由不同人员批准；不要误扩展成“关闭也必须双人”。
- 审批意图必须绑定目标、金额/范围、状态版本、原因、幂等键、过期时间和一次性消费；AuditLog 不能替代该业务事实。

## 7. 兼容与回滚

- PAY-MP-001 A1/B1/C1/D1、Hosted boundary、既有 Invoice/Payment/PaymentOrder/Webhook/OCPP 事实保持可读写。
- P002 使用 additive schema 和版本化状态；无历史数据不等于可以跳过 schema version。无需导入或伪造历史业务事实。
- P001 metadata 可继续作为兼容摘要，但新增 P002 写入必须以 typed facts 为权威；过渡读路径必须有明确截止和一致性校验。
- 回滚只关闭 P002 新入口和控制范围，保留 Invoice、Payment、Refund、Webhook、Support、Audit 与 OCPP 事实；未确认状态保持 D1 blocked。
- 不删除新财务事实、不反向修改 Invoice、不自动退款、不自动 reopen、不静默切换 Provider 或风险方案。

## 8. D-204 实现隔离门禁

D-204-B 目标架构已批准，但也不能被技术默认值补齐。以下实现内容保持 TODO/blocked，直到契约、实现与 QA 门禁完成：

- 单 Session、用户/日、tenant/site/日、平台/日 COP 暴露；
- Wh、时长、MeterValues lag、设备离线、Provider unknown、退款/拒付 buffer；
- 触发阈值、停止余量、RemoteStop → StopTransaction/最终 MeterValues SLA；
- risk policy version、reserve/consume/release/unresolved 和事故 runbook；
- BE-205、FE 风险文案以及任何真实资金发布。

架构与实现不得创建“临时默认参数”，也不得把 D-210 的 R2/R3 样本上限当成 D-204 风险参数。

## 9. 下一门禁

1. `PAY-MP-002-v1` 已冻结；已批准且非 D-204 的分批任务可按数据/共享契约 → 后端 → 前端顺序实施。
2. 每批实现后必须由独立 qa-agent 验收，相关批次通过后再进入 E2E；本架构批准不等于代码或 QA 完成。
3. 当前 runtime 仍是 PAY-MP-001；不得把目标文档描述为已实现能力。
4. D-204 目标架构已批准；BE-205、风险参数/UI/runtime 和真实资金发布仍保持 blocked，直到 contract refresh、实现、独立 QA/E2E、容量和人工发布门禁完成；`PAYMENT_RAILS_ENABLED` 保持关闭门禁。

## 10. 统一交接

```text
STATUS: done

CHANGED_FILES:
- docs/features/PAY-MP-002/ARCHITECTURE_REVIEW.md
- docs/features/PAY-MP-002/contracts/API.md
- docs/changes/CHG-20260812-002.md
- docs/architecture/adr/ADR-005-pay-mp-002-risk-recovery-operations.md
- docs/architecture/TECH_ARCHITECTURE.md
- docs/architecture/ARCHITECTURE_CHANGELOG.md
- docs/features/PAY-MP-002/STATUS.md

COMMANDS_RUN:
- 重新加载治理、architecture-agent skill、权威架构、ADR、Change、前后端设计/任务和候选契约
- 仅核验 CF-201～CF-206 修订、当前 transactions shape、Outbox tenant scope、Charging D1/rail 边界和工作树
- 执行第二次且最后一次重大 SELF_CHECK 与完成标准检查；未重做全量搜索

TEST_RESULTS:
- 复用上一轮定向回归证据：27 passed（payment reconciliation、refund、charging payment intent、payment reliability，5.24s）；本轮未重跑业务测试
- 文档门禁与一致性检查通过
- 未运行数据库集成、Provider sandbox 或 E2E；定向测试证明 P001 基线未明显破坏，不证明 P002 已实现

CONTRACT_CHANGES:
- 无运行时 API、数据库、事件或生产配置变更
- `PAY-MP-002-v1` 已冻结；仅授权已批准且非 D-204 的分批实现

ARCHITECTURE_COMPLIANCE:
- C3 target architecture verdict: approved; phased non-D-204 tasks are implementation-ready
- approved target architecture recorded in ADR-005; current runtime remains PAY-MP-001 baseline
- no unresolved Product Owner decision for D-204 window; D-204 target architecture is approved and implementation remains isolated/gated

RISKS:
- 当前 runtime 仍缺 typed recovery/refund/chargeback/reconciliation/rail/support facts；architecture-approved 不等于代码已实现
- backend/frontend QA、E2E 和人工发布审查均未通过，生产保持 NO-GO
- D-204 继续阻塞 BE-205、运行时默认值及真实资金发布，直到后续 implementation/QA/release gates 完成
- PAYMENT_RAILS_ENABLED 必须继续遵守既有关闭门禁；本审核未读取、修改或批准生产有效值
```

## 11. D-204-B 独立架构门禁（2026-08-15）

本节是对旧版“D-204 deferred-todo”隔离记录的独立复审结果；详细门禁、影响分析、目标状态机、契约刷新提案和证据矩阵见 [`D204-B_ARCHITECTURE_GATE.md`](../../changes/CHG-20260812-002/D204-B_ARCHITECTURE_GATE.md)。

- 产品批准前置门：**passed**；`PRODUCT_APPROVAL.md` 含用户原文“批准 D-204-B”。
- D-204-B 目标技术架构门禁：**`architecture-approved`**；不是 implementation-ready、QA-passed 或 production-approved。
- `BLOCKER-D204-001` 已解决：Product Owner 明确批准窗口方案 A——site/platform 同一 UTC timestamp rolling 24-hour window；无 calendar-midnight reset；active reservations 与 unresolved exposure 计入；released/settled exposure 排除。
- 剩余事项均为后续 contract-refresh、实现、QA/E2E、容量和人工发布 gates：现行 `PAY-MP-002-v1` 仍明确排除风险契约；当前代码没有 risk ledger/stop worker/provider-unknown 24h runtime；D-204 专项 PostgreSQL/Outbox/OCPP/容量/QA/E2E 证据未形成。
- 记录的目标 authority：PostgreSQL typed risk policy/ledger/reservation/stop/provider-resolution；Redis 仅缓存/协调；Charging/OCPP 仍拥有 StopTransaction/MeterValues；Risk 通过 Outbox/OCPP control 交接 RemoteStop。
- 记录的 contract refresh：提议 `PAY-MP-002-v2` 或等价新 vendor media type；未修改现行 `PAY-MP-002-v1`，不得由实现 Agent 直接加字段。
- 下一允许动作：按 ADR-006 accepted-target 结论完成 v2 contract refresh，之后才可进入 BE-205 实现与独立 QA/E2E；本次不实施。
