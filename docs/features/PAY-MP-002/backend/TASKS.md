---
id: PAY-MP-002-BE-TASKS
change_id: CHG-20260812-002
feature_id: PAY-MP-002
status: be-211-qa-closed-awaiting-release-gates
implementation_authorization: phased-non-d204-only
contract_status: frozen
contract_version: PAY-MP-002-v2
compatible_contracts: P001-default, PAY-MP-002-v1
owner: backend-agent
---

# PAY-MP-002 后端任务拆分与门禁

本文件记录已冻结的后端任务顺序及逐任务交接。BE-201～BE-211 的最新独立 backend QA EOF handoff 已关闭对应本地/测试 gate；既有 QA failed 历史/verdict 保留。Live Provider、生产容量、完整 E2E、人工发布和 D-204/BE-205 仍是独立门禁。实现 Agent 与 backend-scope qa-agent 不得兼任。

## 1. 总体顺序

```text
AR-201 contract candidate + design rereview
  -> BE-201 typed schema / immutable facts
  -> BE-202 RecoveryAttempt + PaymentAllocation
  -> BE-203 FinancialEligibility / D1
  -> BE-204 Provider-neutral orchestration / P001 compatibility
  -> BE-206 history and safe projections
  -> BE-207 refund / chargeback / dual control
  -> BE-208 three-way reconciliation
  -> BE-209 SupportCase / RBAC / approvals
  -> BE-210 two-axis rail control
  -> BE-211 migration / compatibility / load / handoff
  -> independent backend QA -> frontend QA -> E2E -> human release gates
```

BE-205（D-204 risk runtime）现在拥有产品批准的 D-204-B 输入，但不在既有实现链中；必须先完成独立架构审核和契约更新，不能被前置、旁路或用默认值替代。

## 2. 任务明细

### BE-201 — Typed schema 与不可变财务事实

- **状态：** `fix-003-qa-004-fixed-awaiting-final-independent-re-qa`（2026-08-13；重大修正预算 `2/2` 已耗尽）。
- **Owner：** backend implementation owner；Billing/Charging/Identity/Operations 作为 domain reviewers。
- **依赖：** architecture-agent 复审；不修改 Invoice 的业务含义。
- **交付：** recovery_attempts、payment_allocations、refund/chargeback/reconciliation/rail/support typed facts 的 additive migration；字段、FK、状态 CHECK、Decimal、UTC、索引、schema_version、audit reference、tenant/resource ownership；Outbox 按 `scope_type/scope_ref` 单表 additive 方案放宽 tenant nullable、建立 CHECK 和新唯一键。
- **必须证明：** Invoice/PricingSnapshot/Session 原始事实不可变；P001 PaymentOrder metadata 只作兼容摘要；历史缺失 facts 标为 legacy/unknown，不回填猜测值。
- **负例：** 同 Invoice 两个 committed allocation、跨 tenant allocation、负金额、错误 currency、孤儿 attempt、删除租户导致财务事实消失；platform Outbox 伪造 tenant、tenant/ref 不一致、scope 内重复 idempotency。
- **禁止：** 本任务创建 D-204 risk ledger 或改写现有业务数据。
- **实现证据：** `app/database/models.py`、`alembic/versions/012_pay_mp_002_be201_typed_facts.py`、`tests/test_pay_mp_002_be201_schema.py`。新增 13 张 typed tables；Outbox 采用单表 tenant/platform scope；迁移为 additive，downgrade 只回退应用版本标记并保留财务事实。
- **验证证据：** `PaymentAllocation(id,tenant_id)` 现为复合 owner target；`ReconciliationItem(payment_allocation_id,tenant_id)` 通过 DB FK 绑定同租户，同时保留 allocation 单列 FK，使 platform-scope `tenant_id=NULL` 可合法引用任一真实 allocation。`BE-201-FIX-003` 为 SupportCase 的 `invoice_id`、`session_id`、`refund_case_id`、`chargeback_case_id`、`rail_control_id` 全部建立 `(resource_id,tenant_id)` 复合 owner FK，并保持 NULL linked resource 合法；tenant SupportCase 不可链接 tenant_id=NULL 的 platform/provider rail。SupportCaseEvent 继续由 `(support_case_id,tenant_id)` 复合 FK 约束。`BE201-QA-004` 修复把 migration 重排为：P001 Invoice/Session owner keys → 非 Support BE-201 targets → 五类 target keys → SupportCase owner key → SupportCase/Event → ownership validation；所有步骤按 table/constraint existence 幂等。真实 pre-BE-201 011 shape 已证明首次 012、唯一 head、repeat no-op、non-destructive downgrade/re-upgrade、old-column Outbox insert 和 partial-012 repair 均通过。PostgreSQL 15 ownership、QA-001/002 和五类 dirty-link fail-fast/原子性继续通过。本轮实现者验证不替代 final fresh independent re-QA。

### BE-202 — RecoveryAttempt / PaymentAllocation 与补缴幂等

- **Owner：** Payment/Recovery service。
- **依赖：** BE-201；P001 Hosted Checkout/Wallet/Provider adapter。
- **交付：** wallet/new_card/saved_card 共用状态机；服务端按 Invoice 读取全额 outstanding；checkout `purpose=unpaid_charge` 产生 typed attempt；唯一赢家、duplicate approved、provider unknown、safe retry、跨设备恢复；domain→public 映射严格使用 `PAY-MP-002-v1`。
- **幂等：** app_user+idempotency key+fingerprint；provider operation key；同一 Invoice 的 allocation partial unique winner；重复响应返回原 attempt，不重新调用 Provider。
- **事务：** wallet 在锁定 AppUser/Invoice 下原子扣款+allocation；卡 Provider call 使用 outbox/lease，回写时重新锁 attempt/Invoice；不在长事务持有 Provider HTTP。
- **验收：** D1 只有 allocation committed 后才可 recheck；原 Invoice、用量、价格快照和历史 payment 不改写；迟到非赢家为 `manual_review/duplicate_approval/allocation=null`，相同 fact 不重复退款、case 或 Outbox。
- **P0 修复交接（2026-08-13）：** `PaymentReconciliationService.start_payment_order()` 在 wallet top-up 与 charging/unpaid recovery 两条 Provider 创建路径中，先持久化 `processing` 和 `provider_operation_key` 并结束短事务，再以提交前捕获的不可变标量执行 Provider I/O；Provider 返回后交给现有 `reconcile()` 开启新短事务回写。新增 fake Provider 事务边界断言，确认调用瞬间 `Session.in_transaction()` 为 false；P001 兼容、未知/可重试和同一 operation key 保持。

### BE-203 — FinancialEligibility 与 D1 re-block

- **Owner：** FinancialEligibility service；Charging 只消费决定。
- **依赖：** BE-201/202；现有 `/charging/start` 和 OCPP owner。
- **交付：** 唯一 FinancialEligibility evaluator 只输出财务 `eligible|blocked|recheck_required|unknown`、safe reason、decision version、source watermark；覆盖 open Invoice、pending/unknown attempt、refund/chargeback/reversal、funds unknown、reconciliation mismatch。另建 `ChargingAdmissionPreflight`，用 QR 服务端解析资源和 provider/tenant/site scope 后组合 `paid_admission` rail。
- **事务/事件：** allocation/refund/chargeback/reconciliation state change 触发 `financial.eligibility.recheck_requested`；evaluator 可重放；未知 fail closed。
- **禁止：** 用 AppUser flag、Redis、history projection、单 webhook 或 provider approved 直接解锁；禁止把 `rail_closed` 写入 FinancialEligibility；不在此任务增加风险 budget。

### BE-204 — Provider-neutral orchestration 与 P001 兼容

- **Owner：** Payment orchestration/provider adapter boundary。
- **依赖：** BE-201/202；ADR-004；当前 Mercado Pago adapter。
- **交付：** canonical create/query/refund/dispute/funds interfaces；Provider-specific id、错误、3DS、raw response 留在 adapter；P001 A1/B1/C1、saved-card CVV、Webhook 主动反查保持；`/app/transactions` 只以 vendor `Accept` 暴露 P002。
- **验收：** fake Provider 可覆盖 processing/action_required/approved/declined/unknown/late reversal/refund/chargeback；核心不要求 Provider-specific 字段；P001 继续 bare array/offset/旧 number 类型，P002 才是 cursor/decimal-string，且不存在第二协商机制。
- **非范围：** authorize/capture/void、预授权、分账、费用、第二 Provider 生产接入。方案 2 研究若重新启动需独立产品/架构门禁。

### BE-205 — D-204-B 风险预算/硬停止（contract-frozen / implementation-ready-for-BE205）

- **状态：** `contract-frozen / implementation-ready-for-BE205`；实现、QA/E2E、容量和生产仍为后续门禁。
- **产品输入：** 单会话 200,000 COP / 100 kWh / 180 分钟（先到者触发）；用户未结敞口 250,000 COP；站点周期敞口 1,000,000 COP；平台总敞口 5,000,000 COP；MeterValues 120 秒降级、300 秒自动停止；离线/unknown 额外敞口 15,000 COP 或 5 分钟；Provider unknown 自动核查 24 小时且不重复扣款；RemoteStop 10 秒内发起、最多自动重试 3 次；StopTransaction 目标 5 分钟；15 分钟自动恢复核查、24 小时最终处理。
- **当前阻塞条件：** 完成风险账本/计数器/版本化策略 runtime、OCPP/Outbox 交接、独立 backend QA、frontend QA、E2E、容量和发布门禁。产品与契约批准不等于实现或生产批准。
- **当前允许：** 按冻结 `PAY-MP-002-v2` 进入 BE-205 实现计划；本文件不实现业务逻辑。
- **明确禁止：** risk ledger、reserve/consume/release、MeterValues risk counter、RemoteStop threshold、hard-stop worker、生产止损开关。

### BE-206 — 基础历史与支付/退款/拒付安全投影

- **Owner：** Billing/Payment read projection service。
- **依赖：** BE-201/202/203；D-205-A。
- **交付：** App 基础历史/详情、Invoice/Session/Payment/Allocation/Refund/Chargeback 安全状态和非敏感 reference；不生成 PDF/下载/邮件收据/DIAN 发票。
- **验收：** started 不等于 paid；processing/unpaid/refunded/disputed/unknown 有清晰状态；投影可由 authority 重建，不能成为 D1 authority；AppUser/tenant 过滤和分页稳定。

### BE-207 — RefundCase / ChargebackCase / 双人退款

- **Owner：** Payment/Operations；Finance reviewer。
- **依赖：** BE-201/204/206；D-206-B。
- **交付：** RefundCase、RefundApproval、RefundAttempt、ChargebackCase；一人发起、不同人批准；全额/部分累计不超过实付；Provider confirmed fact 才更新完成状态；退款与拒付分离。
- **幂等/审计：** case request fingerprint、approval version、provider operation key、unknown/manual review 可重放；记录 actor/tenant/scope/reason/before-after/result。
- **验收：** 重复点击、Provider timeout、金额不匹配、钱包余额不足、late chargeback 和重复 webhook 均不假成功、不重复退款、不错误解锁。

### BE-208 — 持续逐笔 + Bogotá 日批次三方对账

- **Owner：** Reconciliation/Finance operations。
- **依赖：** BE-201/204/207；资金事实输入边界。
- **交付：** ReconciliationRun/Item/Exception；EsLatin、Provider、actual funds 三方关联；金额/币种/merchant/tenant/fee/refund/hold/release 差异；cursor/watermark、bounded replay、截止和 owner。
- **双控：** 仅 timing/fee/funds-release timing 可由 finance 与 platform 不同人员批准最长 24 小时临时例外；下一工作日 Bogotá 12:00 前关闭前一营业日；到期自动重开阻断，不自动放行。
- **容量：** 分批读取/写入、source dedupe、payload hash/conflict、lease/retry/DLQ；不把批量全表扫描或无界 JSON payload 写入生产路径。

### BE-209 — SupportCase、RBAC、租户和审批意图

- **Owner：** Operations/Support + Identity/Tenant。
- **依赖：** BE-201/203/207/208；D-209-B。
- **交付：** 非敏感上下文 SupportCase/CaseEvent、SLA、责任人、邮件 Outbox、营业时段紧急支持状态；实现 `contracts/API.md` §6 固定 permission、resource/platform scope、HTTP/body/sort 和 CSV lifecycle；审批 intent 不能直接改终态。
- **验收：** App 只能看自己的 reference；Admin tenant 从可信关联推导；跨租户访问不泄露存在性；support 不能改 Invoice/Payment/D1；通知可重试且不含 PAN/CVV/token/证件。

### BE-210 — 双轴 runtime rail control

- **Owner：** Operations/Platform control service。
- **依赖：** BE-203/204/209；D-208-B。
- **交付：** `paid_admission`/`payment_creation`，platform/provider/tenant/site scope，version、reason、incident、close/reopen、health check、audit；一人 close、不同人批准 reopen、不自动恢复。
- **规则：** 关闭只阻止新的适用入口；Webhook、query、refund、chargeback、reconciliation、history、support、StopTransaction 继续收敛；不因 payment close 自动 RemoteStop 活跃会话。
- **验收：** overlap scope fail closed；网络 unknown 不误报 close/reopen；普通 tenant 不能操作 platform rail；不会以 `PAYMENT_RAILS_ENABLED` 环境变量冒充 runtime control。

### BE-211 — 迁移、兼容、脏数据、写入压力和 QA handoff

- **Owner：** backend/architecture/qa reviewers。
- **依赖：** BE-201～210（BE-205 除外，风险 runtime 仍 blocked）。
- **交付：** expand/validate/cutover/rollback 计划；空库/已有库/混合版本矩阵；legacy/unknown 处理；索引/锁/连接池/queue lag/Provider burst/MeterValues fallback 的测量计划；P001/P002 media-type golden responses、Outbox scope constraints、Admin endpoint/CSV lifecycle contract tests；backend QA report 输入和 E2E fixture contract。
- **验收：** migration 可重复、checksum、无 drop；回滚只关闭新入口并 D1 fail closed；数据库能发现重复 allocation、孤儿、跨 tenant、非法状态、负钱包；未知状态不判 pass。

## 3. 实现阶段文件 ownership 规则

BE-201 本轮 ownership 已收敛并交还；后续实现必须按领域拆分 ownership，至少隔离：

- API/契约映射；
- Recovery/Eligibility；
- Refund/Chargeback；
- Reconciliation；
- Rail/Support/RBAC；
- migration/schema；
- backend tests。

不得让两个 Agent 同时编辑共享模型、Provider protocol、shared API 或 migration；跨层顺序为 schema → contract → backend → frontend → QA。

## 4. QA/E2E 和发布门禁

每个 BE 任务完成后交给独立 `qa-agent`（backend scope），必须有精确命令、数据库/Redis/Provider fixture、测试结果、未测面和架构合规结论。Backend QA 通过后才能进入 frontend QA；两者通过后由 e2e-agent 验证完整用户旅程。

R0～R4 不是 backend 自动晋级：每一级都要独立 QA/E2E、对账/运营证据和 Product Owner 明确晋级；D-204 未批准前真实资金始终 no-go。D-210 的 R2/R3 样本限制不属于风险预算，不得拿来填 BE-205。

## 5. 当前交接

STATUS: done-awaiting-final-independent-backend-re-qa

CHANGED_FILES:
- csms/app/database/models.py
- csms/alembic/versions/012_pay_mp_002_be201_typed_facts.py
- csms/tests/test_pay_mp_002_be201_schema.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

COMMANDS_RUN:
- 容器内 PostgreSQL 门禁开启：`pytest -q tests/test_pay_mp_002_be201_schema.py tests/test_database_models.py tests/test_database_queries.py tests/test_cleanup_sim_e2e.py`
- 独立 PostgreSQL schema 还原真实 pre-BE-201 revision 011（typed tables=0、FIX-003 keys=0、legacy Outbox shape），执行 011→012/repeat/downgrade/re-upgrade/old-column insert
- 模拟 partial 012 缺失 rail target key/FK，连续执行 migration body 两次并核对约束唯一
- PostgreSQL 15 empty chain、FIX-003 ownership、QA-001/002、五类 dirty-link fail-fast/原子性回归

TEST_RESULTS:
- PostgreSQL schema/migration 专项 `12 passed in 5.60s`
- 直接相邻完整回归 `32 passed in 12.58s`，无 skip
- 真实 P001 011→012 成功且 `alembic_version` 唯一为 012 head；repeat no-op；downgrade 保留 typed tables；re-upgrade 成功；旧列 Outbox insert 自动补 tenant scope
- partial 012 连续修复后 `uq_runtime_rail_control_id_tenant` 与 `fk_support_case_rail_owner` 各且仅一个；FIX-003 五类 owner/Event、QA-001/002、五类 dirty migration 全部保持通过

CONTRACT_CHANGES:
- 无 frozen API contract 变更；仅增加 BE-201 数据库 tenant ownership constraints
- 未建立 BE-202 服务写入、事件 worker 或运行时 API

ARCHITECTURE_COMPLIANCE:
- C3；BE-201 遵守 ADR-005、tenant/resource ownership、Decimal/UTC、audit/schema version、additive migration/rollback
- D-204、BE-205、默认风险参数和真实资金发布保持 blocked

RISKS:
- QA 报告/verdict 保留 `failed-be202-provider-call-inside-active-db-transaction` 历史；本次修复后须由独立 qa-agent fresh backend re-QA 才能关闭 BE-202 gate
- BE-203/BE-204、D-204/BE-205、跨模块 QA/E2E 和生产放行均未执行；生产仍 NO-GO

## BE-202 P0 Provider transaction-boundary handoff

```text
STATUS: done-awaiting-independent-backend-re-qa
TASK: PAY-MP-002 / BE-202 / BE202-QA-001

CHANGED_FILES:
- csms/app/services/payment_reconciliation.py
- csms/tests/test_recovery_service_be202.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

COMMANDS_RUN:
- 重载 AGENTS.md、RUNTIME_POLICY、backend skill、PAY-MP-002 frozen contract、BE-202 design/tasks、QA §47-55 与当前 diff；执行 startup/final SELF_CHECK
- Docker BE-202 direct tests 与 Provider transaction-boundary fake tests
- P001 checkout/reconciliation、payment/refund/provider/method regression
- Python compileall 与 git diff --check

TEST_RESULTS:
- BE-202 direct + boundary tests: `7 passed, 4 warnings`
- P001 checkout/reconciliation and related payment regression: `92 passed`
- Provider call boundary: wallet top-up 与 unpaid recovery charging 两条路径均断言 `Session.in_transaction() is False`
- provider operation key persisted and reused as `payment-order:<payment_order_id>`
- compileall: passed；git diff --check: passed

CONTRACT_CHANGES:
- none; frozen PAY-MP-002-v1 与 P001 response/API semantics unchanged

ARCHITECTURE_COMPLIANCE:
- Provider I/O moved outside active SQLAlchemy transaction；Provider return uses existing reconcile() short transaction
- Unknown/retryable and P001 compatibility paths retained；no BE-203/BE-204/D-204 expansion

RISKS:
- Independent backend re-QA remains required; QA report failed history is preserved
- BE-203/BE-204, D-204/BE-205, E2E and production release remain blocked/no-go
```

## BE-202 BE202-QA-002 修复交接

```text
STATUS: done-awaiting-independent-backend-re-qa
OWNER: backend-agent-carver
SCOPE: backend
TASK: PAY-MP-002 / BE-202 / BE202-QA-002

CHANGED_FILES:
- csms/app/services/payment_reconciliation.py
- csms/tests/test_recovery_service_be202.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md (BE-202 implementation handoff only)

COMMANDS_RUN:
- 重载 AGENTS.md、RUNTIME_POLICY、backend skill、技术架构、后端边界、ADR-005、PAY-MP-002-v1、BE-202 docs、QA §56-64 与当前 diff；执行 startup/final SELF_CHECK
- Docker BE-202 direct regression
- P001 checkout/reconciliation 与 payment/refund/wallet/merchant/charging regression
- compileall 与 git diff --check

TEST_RESULTS:
- BE-202 direct regression: `8 passed, 4 warnings`
- BE-202 + 相关支付/checkout/reconciliation regression: `100 passed, 4 warnings`
- retryable ProviderError 后 RecoveryAttempt=`unknown`、PaymentOrder=`processing`、allocation count=`0`
- provider operation key 保持 `payment-order:<payment_order_id>`；第二次 retry 不重复调用 Provider，仍返回 processing

CONTRACT_CHANGES:
- none; frozen PAY-MP-002-v1、P001 API、migration、models unchanged

ARCHITECTURE_COMPLIANCE:
- retryable exception 使用已加载 PaymentOrder 写回状态与 metadata；RecoveryService.mark_unknown 保持不变
- 未修改业务 Order；未进入 BE-203/BE-204/D-204

RISKS:
- 需要 fresh independent backend re-QA 后才能关闭 BE-202 gate
- QA 报告失败历史保留；未执行真实支付、生产数据库或生产配置
```

## BE-203 implementation handoff

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: backend
TASK: PAY-MP-002 / BE-203

CHANGED_FILES:
- csms/app/services/financial_eligibility.py
- csms/app/services/recovery_service.py
- csms/app/api/v1/app/financial_eligibility.py
- csms/app/api/v1/app/charging.py
- csms/app/api/v1/app/recovery.py
- csms/app/api/v1/__init__.py
- csms/tests/test_financial_eligibility_be203.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

COMMANDS_RUN:
- startup SELF_CHECK；重载治理、RUNTIME_POLICY、backend skill、TECH_ARCHITECTURE、BACKEND_BOUNDARIES、ADR-005、PAY-MP-002-v1、BE-203 docs 与最新 QA handoff
- `python3 -m pytest -q tests/test_financial_eligibility_be203.py`
- `python3 -m pytest -q tests/test_financial_eligibility_be203.py tests/test_pay_mp_002_be201_schema.py tests/test_recovery_service_be202.py tests/test_checkout_session_api.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py tests/test_payment_methods.py tests/test_payment_method_codec.py tests/test_phase4_payment_reliability.py tests/test_payment_merchant_context.py tests/test_charging_payment_intent.py tests/test_checkout_session_store.py tests/test_p0_app_regressions.py`
- Python `compile()` checks for all BE-203 implementation/direct-test files
- `git diff --check` and untracked BE-203 file diff checks

TEST_RESULTS:
- BE-203 direct: `3 passed`
- related backend/schema/payment/charging regression: `136 passed, 5 skipped, 5 warnings`
- compile checks: passed
- diff checks: passed

CONTRACT_CHANGES:
- none; frozen `PAY-MP-002-v1` unchanged
- added `/api/v1/app/financial-eligibility` and `/api/v1/app/charging/preflight` using frozen states/reasons; no new public enum/error semantics
- no database migration or production configuration change

ARCHITECTURE_COMPLIANCE:
- FinancialEligibility is the only platform-level evaluator; canonical domain states are `eligible|blocked|recheck_required|unknown`, with public `recheck_required -> evaluating`
- source watermark and decision version are evaluator outputs; reason codes remain financial-only and never contain `rail_closed`
- `/charging/start` re-runs `ChargingAdmissionPreflight`; QR/resource/provider/scope are server-derived; applicable closed/unknown `paid_admission` rail fails closed
- allocation, recovery unknown/duplicate and related typed fact hooks enqueue idempotent `financial.eligibility.recheck_requested`
- no AppUser flag/Redis/history projection/provider-approved shortcut; no D-204 risk budget/default threshold/hard-stop runtime

RISKS:
- independent BE-203 backend QA remains required; QA report was not modified or self-approved
- full cross-module E2E, human review, D-204/BE-205 and production gates remain separate; production remains NO-GO
```

## BE-203 BE203-QA-001 最小修复交接

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: backend
TASK: PAY-MP-002 / BE-203 / BE203-QA-001

CHANGED_FILES:
- csms/app/services/payment_refunds.py
- csms/app/services/payment_reconciliation.py
- csms/tests/test_payment_refunds_be7.py
- csms/tests/test_payment_reconciliation_be6.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

COMMANDS_RUN:
- 重载治理、RUNTIME_POLICY、backend-agent skill、TECH_ARCHITECTURE、BACKEND_BOUNDARIES、ADR-005、BE-203 文档与 QA §74-82；执行 startup SELF_CHECK
- `python3 -m pytest -q tests/test_financial_eligibility_be203.py tests/test_recovery_service_be202.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py`
- `python3 -m pytest -q tests/test_recovery_service_be202.py tests/test_checkout_session_api.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py tests/test_payment_methods.py tests/test_payment_method_codec.py tests/test_phase4_payment_reliability.py tests/test_payment_merchant_context.py tests/test_charging_payment_intent.py tests/test_checkout_session_store.py`
- Python `compile()` checks for BE-203/BE-202/recovery/refund/reconciliation implementation and direct-test files
- `git diff --check`

TEST_RESULTS:
- focused BE-203/BE-202/BE-6/BE-7 regression: `28 passed, 5 warnings in 4.69s`
- related payment/checkout regression: `112 passed, 5 warnings in 9.67s`
- compile: `passed`; git diff check: `passed`
- refund mutation: each confirmed cumulative refund change enqueues one tenant-scoped event; distinct refund idempotency operations produce distinct event keys
- non-Recovery PaymentReconciliation mutation: enqueues the same existing helper/event; Recovery branch remains owned by RecoveryService to avoid duplicate hooks

CONTRACT_CHANGES:
- none; no API, database, migration, public event schema, frontend, production configuration or PAYMENT_RAILS_ENABLED change

ARCHITECTURE_COMPLIANCE:
- reused `enqueue_financial_eligibility_recheck`; no parallel event mechanism
- tenant scope is derived from Invoice, original wallet ledger, or server-created compatibility metadata; no client tenant is accepted
- `rail_closed` remains outside FinancialEligibility; no D-204 risk budget/hard-stop runtime
- ChargebackCase has no current mutation owner, and typed three-party reconciliation facts have no current writer; neither was invented or expanded
- BE-204/BE-206/D-204 remain out of scope; fresh independent BE-203 QA is still required

RISKS:
- current independent QA verdict in §74-82 remains failed until a new independent backend QA verifies the mutation-to-recheck paths
- no real Provider, production database, production configuration or real payment used
```

## BE-203 BE203-REQA-001 相邻回归修复交接

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: backend tests/fixtures only
TASK: PAY-MP-002 / BE-203 / BE203-REQA-001

CHANGED_FILES:
- csms/tests/test_ocpp_message_handler.py
- docs/features/PAY-MP-002/backend/TASKS.md

PRESERVED_RELEVANT_EXISTING_CHANGES:
- csms/tests/conftest.py (`sample_commercial_charge_point` fixture; no new edit)

COMMANDS_RUN:
- startup SELF_CHECK；重载治理、RUNTIME_POLICY、backend-agent skill、BE-203 QA §83-91、当前 diff、OCPP handler 与测试 fixtures
- `python3 -m pytest -q tests/test_ocpp_message_handler.py::TestOCPPMessageHandler::test_handle_start_transaction tests/test_ocpp_message_handler.py::TestOCPPMessageHandler::test_handle_start_transaction_rejects_uncommissioned_charger`
- `python3 -m pytest -q tests/test_financial_eligibility_be203.py tests/test_recovery_service_be202.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py tests/test_charging_payment_intent.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_merchant_context.py tests/test_payment_method_codec.py tests/test_payment_methods.py tests/test_billing_service_be5.py tests/test_phase4_payment_reliability.py tests/test_p0_app_regressions.py tests/test_user_charging_flow.py tests/test_api_ocpp_control.py tests/test_ocpp_device_security.py tests/test_ocpp_message_handler.py`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin_compile_cache python3 -m compileall -q -f app tests`
- `git diff --check`

TEST_RESULTS:
- focused StartTransaction success/rejection tests: `2 passed`
- BE-203/OCPP/backend bounded regression: `193 passed, 5 warnings`
- compile: passed with the task-local pycache prefix; initial default-prefix run was blocked by the host's protected Python cache path
- git diff check: passed

CONTRACT_CHANGES:
- none; no production code, API, database, migration, model, frontend, production configuration or QA report changed

ARCHITECTURE_COMPLIANCE:
- successful StartTransaction now uses the existing commissioned charger with a valid paid tariff fixture and asserts `Accepted`
- default draft charger remains covered by an OCPP `Rejected` assertion, `CHARGER_NOT_COMMISSIONED` log assertion, and no-session side-effect assertion
- no D-204 or BE-204 scope expansion

RISKS:
- fresh independent backend QA must re-run BE-203 gate; this implementation handoff does not self-approve QA
- production remains NO-GO; no real payment or production database was used
```

## BE-204 implementation handoff

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: PAY-MP-002 / BE-204 backend implementation and direct tests

CHANGED_FILES:
- csms/app/services/payment_providers/base.py
- csms/app/services/payment_providers/mercadopago_provider.py
- csms/app/services/payment_reconciliation.py
- csms/app/services/payment_refunds.py
- csms/app/api/v1/app/payments.py
- csms/app/api/v1/app/transactions.py
- csms/tests/test_payment_provider_capabilities_be204.py

COMMANDS_RUN:
- Docker build for the current csms image
- `docker compose run --rm --no-deps --entrypoint python csms -m pytest -q tests/test_payment_provider_capabilities_be204.py`
- `docker compose run --rm --no-deps --entrypoint python csms -m pytest -q tests/test_checkout_session_api.py::test_direct_checkout_confirm_creates_versioned_payment_intent_order`
- scoped payment/checkout/reconciliation/refund/transactions/P001 regression suite
- source `py_compile` with task-local `PYTHONPYCACHEPREFIX`
- `git diff --check`

TEST_RESULTS:
- BE-204 direct capability tests: `11 passed`
- direct checkout compatibility regression: `3 passed`
- scoped regression: `101 passed, 4 warnings`
- compile: passed; diff check: passed

CONTRACT_CHANGES:
- none; PAY-MP-002-v1 and P001 semantics remain frozen

ARCHITECTURE_COMPLIANCE:
- canonical create/query/refund/dispute/funds capability types are provider-neutral
- Mercado Pago IDs, errors, 3DS/action details and raw response remain adapter-side
- P001 recovery, saved-card CVV, active webhook re-query and frozen P002 Accept negotiation are preserved
- no migration, frontend, production config/database, second Provider, BE-206 or D-204 work

RISKS:
- independent backend QA must verify the implementation and remains the next gate
- no real Provider, production database, production configuration or real payment was used
```

## BE-204 BE204-REQA-001 最小回归修复交接

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: backend tests/fixtures only
TASK: PAY-MP-002 / BE-204 / BE204-REQA-001

CHANGED_FILES:
- csms/tests/test_phase3_charging_domain.py
- csms/tests/test_db_write_p0.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

PRESERVED_RELEVANT_EXISTING_CHANGES:
- csms/tests/conftest.py (`sample_commercial_charge_point`; no new edit)
- csms/tests/test_ocpp_message_handler.py draft charger rejection assertion

COMMANDS_RUN:
- startup SELF_CHECK；重载治理、RUNTIME_POLICY、backend-agent skill、PAY-MP-002-v1、BE-204 QA §101-109、当前 diff、目标测试与 fixtures
- `python3 -m pytest -q tests/test_phase3_charging_domain.py::test_replayed_ocpp_messages_are_idempotent tests/test_db_write_p0.py::test_meter_values_message_commits_once`
- `python3 -m pytest -q tests/test_ocpp_message_handler.py tests/test_phase3_charging_domain.py tests/test_db_write_p0.py tests/test_meter_telemetry_service.py tests/test_user_charging_flow.py`
- `docker compose run --rm --no-deps --entrypoint python csms -m pytest -q tests/test_payment_provider_capabilities_be204.py`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin_compile_cache_be204_reqa python3 -m compileall -q -f app tests`
- `git diff --check`

TEST_RESULTS:
- target regression: `2 passed, 1 warning in 1.04s`
- required OCPP/DB-write subset: `15 passed` (`test_ocpp_message_handler.py`, `test_phase3_charging_domain.py`, `test_db_write_p0.py`)
- BE-204 direct regression in Python 3.11 Docker: `11 passed in 0.51s`
- compile: passed; `git diff --check`: passed
- extended adjacent regression: `22 passed, 1 failed, 1 warning in 3.56s`; the remaining failure is `test_meter_telemetry_service.py::test_meter_values_use_redis_and_minute_database_sample`, which still uses the draft charger and was intentionally left outside this two-test minimum fix
- both accepted-session business flows now use `sample_commercial_charge_point`, which is commissioned and has a valid paid tariff
- `sample_evse` and `sample_evse_status` fixture compatibility preserved
- existing draft charger rejection coverage remains in `test_ocpp_message_handler.py`

CONTRACT_CHANGES:
- none; no API, database, migration, model, event, frontend or production configuration change

ARCHITECTURE_COMPLIANCE:
- test-only C0 correction; SessionService commissioning/tariff checks remain unchanged
- no BE-206, D-204 or production scope entered; PAY-MP-002-v1 remains frozen

RISKS:
- independent backend QA must rerun BE-204 before the failed gate can close
- one separate telemetry regression still has the same draft-fixture incompatibility; no production behavior was changed and no scope expansion was authorized
- QA report was not modified; the independent QA agent must decide whether that adjacent failure belongs to a later bounded repair
```

## BE-204 BE204-REQA-002 telemetry 最小测试修复交接

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: backend tests/fixtures only
TASK: PAY-MP-002 / BE-204 / BE204-REQA-002

CHANGED_FILES:
- csms/tests/test_meter_telemetry_service.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

PRESERVED_RELEVANT_EXISTING_CHANGES:
- csms/tests/conftest.py (`sample_commercial_charge_point`; reused without edit)
- csms/tests/test_ocpp_message_handler.py draft charger rejection coverage
- csms/app/services/session_service.py production commissioning/tariff gates (unchanged)

COMMANDS_RUN:
- startup SELF_CHECK；重载治理、RUNTIME_POLICY、backend-agent skill、架构边界/ADR、PAY-MP-002-v1、BE-204 QA §110-118、当前 diff、telemetry 测试与 fixtures
- `python3 -m pytest -q tests/test_meter_telemetry_service.py::test_meter_values_use_redis_and_minute_database_sample`
- `python3 -m pytest -q tests/test_meter_telemetry_service.py`
- `python3 -m pytest -q tests/test_ocpp_message_handler.py tests/test_phase3_charging_domain.py tests/test_db_write_p0.py`
- `docker compose run --rm --no-deps --entrypoint python csms -m pytest -q tests/test_payment_provider_capabilities_be204.py`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin_compile_cache_be204_reqa002 python3 -m compileall -q -f app tests`
- `git diff --check`

TEST_RESULTS:
- telemetry target: `1 passed, 1 warning in 0.85s`
- telemetry file: `4 passed, 1 warning in 1.26s`
- related OCPP/DB-write regression: `15 passed, 1 warning in 2.42s`
- BE-204 direct capability regression in Python 3.11 Docker: `11 passed in 0.49s`
- compile: passed; `git diff --check`: passed
- successful telemetry StartTransaction now uses existing `sample_commercial_charge_point`, which is commissioned and has a valid paid tariff
- independent draft charger rejection remains covered by `test_handle_start_transaction_rejects_uncommissioned_charger`

CONTRACT_CHANGES:
- none; no API, database, migration, model, event, frontend, QA report or production configuration change

ARCHITECTURE_COMPLIANCE:
- test-only C0 fixture correction; SessionService production commissioning/tariff rejection gates remain unchanged
- Redis realtime/minute PostgreSQL sampling behavior is tested without changing MeterTelemetryService
- no BE-206, D-204, production or real-payment scope entered; PAY-MP-002-v1 remains frozen

RISKS:
- fresh independent backend QA must rerun BE-204; this handoff does not self-approve the gate
- no production database, production configuration, real Provider or real payment was used
```

## BE-206 implementation handoff

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: backend implementation and direct tests only
TASK: PAY-MP-002 / BE-206

CHANGED_FILES:
- csms/app/services/transaction_projection.py
- csms/app/api/v1/app/transactions.py
- csms/tests/test_pay_mp_002_be206_history.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

PRESERVED_RELEVANT_EXISTING_CHANGES:
- all pre-existing dirty worktree changes, including BE-201~204 implementation/tests and typed-fact model/migration work
- P001 `/app/transactions` bare array, offset pagination, legacy fields/types and semantics
- frozen `PAY-MP-002-v1` contract and QA report; QA report was not edited

IMPLEMENTED:
- P002 vendor Accept contract with cursor envelope, stable `start_time DESC, session_id DESC` ordering and cursor/user/status binding
- rebuildable read-only projection from ChargingSession/Invoice/PricingSnapshot/Payment/PaymentOrder and typed recovery/allocation/refund/chargeback/support facts
- decimal-string energy, duration and money values; safe status/reference/timeline fields
- explicit started/completed/cancelled session state separate from paid/processing/unpaid/refunded/disputed/unknown payment state
- AppUser ownership plus session-tenant/resource-tenant checks; provider identifiers, raw payloads, PAN/CVV, tokens and 3DS secrets are excluded

COMMANDS_RUN:
- startup SELF_CHECK；重载根 AGENTS.md、RUNTIME_POLICY、backend-agent skill、后端边界、ADR、CHANGE/feature docs、frozen contract、BE-201~204 QA handoff and current diff
- `python3 -m pytest -q tests/test_pay_mp_002_be206_history.py`
- `python3 -m pytest -q tests/test_pay_mp_002_be206_history.py tests/test_payment_provider_capabilities_be204.py tests/test_p0_app_regressions.py tests/test_user_charging_flow.py tests/test_charging_payment_intent.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_merchant_context.py tests/test_payment_method_codec.py tests/test_payment_methods.py tests/test_billing_service_be5.py tests/test_phase4_payment_reliability.py`
- `python3 -m pytest -q tests/test_pay_mp_002_be201_schema.py tests/test_financial_eligibility_be203.py tests/test_recovery_service_be202.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py tests/test_api_transactions_active.py tests/test_api_ocpp_control.py tests/test_ocpp_device_security.py tests/test_ocpp_message_handler.py tests/test_phase3_charging_domain.py tests/test_db_write_p0.py tests/test_meter_telemetry_service.py`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin_compile_cache_be206 python3 -m compileall -q -f app tests`
- `git diff --check`

TEST_RESULTS:
- BE-206 direct/golden/security/pagination/ownership: `4 passed, 1 warning`
- first payment/charging regression set: `125 passed, 1 warning`
- schema/eligibility/recovery/reconciliation/refund/OCPP/charging regression set: `105 passed, 5 skipped, 5 warnings`
- compile: passed
- `git diff --check`: passed

CONTRACT_CHANGES:
- none; no frozen API, database, migration, model, event, frontend or production configuration change

ARCHITECTURE_COMPLIANCE:
- additive backend read projection only; no D1/FinancialEligibility authority change and no write-path/runtime rail coupling
- PAY-MP-002-v1 remains frozen; BE-207/D-204/BE-205 remain untouched
- strict AppUser/session-tenant/resource-tenant filtering and safe public projection boundary preserved

RISKS:
- independent backend QA must verify this handoff; this implementation agent does not self-approve QA
- no PDF/download/email/DIAN receipt, RefundCase/ChargebackCase dual-control workflow, reconciliation implementation, runtime rail, production DB/configuration or real payment was added
```

## BE-206 / BE206-QA-001 bounded test-evidence fix handoff

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: direct test evidence only
TASK: PAY-MP-002 / BE-206 / BE206-QA-001

CHANGED_FILES:
- csms/tests/test_pay_mp_002_be206_history.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

PRESERVED_RELEVANT_EXISTING_CHANGES:
- transaction_projection.py and all existing BE-206 implementation changes were not modified
- PAY-MP-002-v1, P001/P002 API semantics, migration, models, frontend, QA report, production configuration, BE-207 and D-204 remain untouched

FIXED:
- replaced generic numeric CVV sentinel `123` with unique non-numeric `CVV_SENTINEL_NON_REFERENCE`
- replaced whole-JSON substring matching with recursive sensitive-key and exact-sensitive-value assertions for PAN, CVV, token, raw Provider data and 3DS secret

COMMANDS_RUN:
- startup SELF_CHECK；重载治理/runtime/backend skill/架构边界/ADR-005/PAY-MP-002-v1/BE-206 docs/QA §128-136/current diff
- direct BE-206 history suite
- related P001/P002/payment/recovery/OCPP/charging regression suites
- compileall and `git diff --check`

TEST_RESULTS:
- direct: `4 passed, 1 warning in 3.35s`
- related set 1: `125 passed, 1 warning in 15.94s`
- related set 2: `105 passed, 5 skipped, 5 warnings in 20.68s`
- compileall: passed; `git diff --check`: passed

CONTRACT_CHANGES:
- none; no API, database, migration, model, event, frontend, production configuration or QA report change

ARCHITECTURE_COMPLIANCE:
- test-only C0 evidence correction; no business projection, authority, D1, payment write path or Provider boundary change
- sensitive-data assertions remain strict and distinguish exact forbidden values from legal reference/UUID substrings
- BE-207, D-204 and BE-205 remain untouched and blocked

RISKS:
- this handoff does not self-approve BE-206; fresh independent backend QA must rerun the authorized scope
- no production database, production configuration, real Provider, real payment or E2E was used
```

## BE-207 webhook chargeback-ingest blocker 修复交接

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: PAY-MP-002 / BE-207 backend implementation and direct/integration tests
TASK: PAY-MP-002 / BE-207 / Mercado Pago webhook -> ChargebackCase authority

CHANGED_FILES:
- csms/app/api/v1/app/payments.py
- csms/tests/test_payment_refunds_be207.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

PRESERVED_RELEVANT_EXISTING_CHANGES:
- existing canonical Mercado Pago signature, active-query, reconciliation and webhook idempotency path
- existing RefundCase/ChargebackCase authority, audit, tenant ownership and FinancialEligibility recheck helper
- frozen PAY-MP-002-v1, models, migration, frontend, QA report and production configuration

IMPLEMENTED:
- after verified active query/reconcile, a canonical `disputed` fact is normalized through the existing provider-neutral `ingest_dispute_fact` seam
- only normalized payment/dispute/status/amount/currency/reference fields are passed to existing `RefundCaseService.ingest_chargeback_fact`
- duplicate processed webhook returns through the existing event idempotency path; repeated chargeback fact remains authority-idempotent
- unknown/invalid webhook handling remains fail closed; refund cases are not created by chargeback facts
- raw provider payload remains excluded from the persisted webhook envelope and ChargebackCase projection

COMMANDS_RUN:
- startup SELF_CHECK；重载根 AGENTS.md、RUNTIME_POLICY、backend-agent skill、PAY-MP-002 architecture/contract/BE-207 docs、current status/tasks and current diff
- `python3 -m pytest -q tests/test_payment_refunds_be207.py`
- `python3 -m pytest -q tests/test_payment_refunds_be207.py tests/test_pay_mp_002_be201_schema.py tests/test_recovery_service_be202.py tests/test_financial_eligibility_be203.py tests/test_payment_provider_capabilities_be204.py tests/test_pay_mp_002_be206_history.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin_compile_cache_be207 python3 -m compileall -q -f app tests`
- `git diff --check`

TEST_RESULTS:
- BE-207 direct/integration: `4 passed, 1 warning`
- BE-201~206 and adjacent payment/refund regression: `54 passed, 5 skipped, 5 warnings`
- compile: passed; `git diff --check`: passed
- integration coverage includes ChargebackCase authority creation, duplicate webhook no-duplicate, raw-payload exclusion, unknown/invalid safe handling, refund/chargeback separation and tenant scope rejection

CONTRACT_CHANGES:
- none; no frozen API, database, migration, model, public event, frontend or production configuration change

ARCHITECTURE_COMPLIANCE:
- reused the existing canonical webhook ingress, active provider query, provider-neutral dispute adapter seam, ChargebackCase authority, audit and BE-203 recheck helper
- provider/payment/resource/tenant ownership remains server-derived; no client tenant or raw provider payload enters authority/projection
- no second webhook mechanism, BE-208/BE-205/D-204 work, risk runtime, real Provider or production operation

RISKS:
- independent backend QA must verify BE-207; this implementation agent does not self-approve QA
- current tests use deterministic provider doubles; live Mercado Pago, production DB/configuration, real payment and E2E remain separate gates
```

## BE-207 tariff-gate regression fixture 修复交接（backend-agent）

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: backend test fixtures only
TASK: PAY-MP-002 / BE-207 / TARIFF_NOT_CONFIGURED regression blocker

CHANGED_FILES:
- csms/tests/conftest.py
- csms/tests/test_charging_payment_intent.py
- csms/tests/test_user_charging_flow.py
- csms/tests/test_ocpp_message_handler.py
- csms/tests/test_phase3_charging_domain.py
- csms/tests/test_db_write_p0.py
- csms/tests/test_meter_telemetry_service.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

FIXED:
- successful StartTransaction/telemetry/charging regression paths use the existing `sample_commercial_charge_point` fixture
- the commercial fixture establishes commissioned state, a valid paid site tariff, and the sample tenant context so BE-207's tenant-context cleanup cannot select a nonexistent tariff
- the explicit uncommissioned/draft charger rejection test remains on `sample_charge_point` and continues to assert `CHARGER_NOT_COMMISSIONED`
- no SessionService, PricingService, migration, model, API contract, frontend, production configuration, QA report or BE-208/D-204 code was changed

COMMANDS_RUN:
- startup SELF_CHECK；重载 AGENTS.md、RUNTIME_POLICY、backend-agent skill、架构/边界、BE-207 QA §149-157、失败堆栈/fixtures、TASKS/STATUS/current diff
- `python3 -m pytest -q tests/test_charging_payment_intent.py::test_start_transaction_binds_one_intent_order_to_one_session tests/test_user_charging_flow.py::TestUserChargingFlow::test_complete_charging_flow tests/test_user_charging_flow.py::TestUserChargingFlow::test_charging_statistics tests/test_ocpp_message_handler.py::TestOCPPMessageHandler::test_handle_start_transaction tests/test_phase3_charging_domain.py::test_replayed_ocpp_messages_are_idempotent tests/test_db_write_p0.py::test_meter_values_message_commits_once tests/test_meter_telemetry_service.py::test_meter_values_use_redis_and_minute_database_sample`
- `python3 -m pytest -q tests/test_payment_refunds_be207.py`
- QA §151 bounded payment/refund/chargeback/webhook/OCPP/telemetry regression command
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin_compile_cache_be207_fixture python3 -m compileall -q -f app tests`
- `git diff --check`

TEST_RESULTS:
- seven failure targets: `7 passed, 1 warning in 2.10s`
- BE-207 direct refund/chargeback/webhook: `4 passed, 1 warning in 1.57s`
- combined BE-207 + charging/OCPP/telemetry fixture regression: `33 passed, 1 warning in 7.97s`
- QA §151 bounded regression: `241 passed, 5 skipped, 5 warnings in 46.44s`
- compile: passed; `git diff --check`: passed

CONTRACT_CHANGES:
- none; PAY-MP-002-v1, database/migration/model/API/event/frontend/production configuration unchanged

ARCHITECTURE_COMPLIANCE:
- test-only C0 fixture correction; production tariff availability and commissioning gates remain unchanged
- explicit no-tariff/uncommissioned negative coverage remains preserved
- no BE-208, D-204 or production scope entered

RISKS:
- awaiting independent fresh backend QA; this handoff does not self-approve BE-207
- live Provider, production DB/configuration, real payment and E2E remain separate gates
```

## BE-208 implementation handoff

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: PAY-MP-002 / BE-208 backend implementation, schema initialization and direct tests
TASK: PAY-MP-002 / BE-208 / continuous + Bogotá daily three-way reconciliation

CHANGED_FILES:
- csms/app/database/models.py
- csms/app/database/__init__.py
- csms/app/services/reconciliation.py
- csms/app/api/v1/admin/reconciliation.py
- csms/app/api/v1/__init__.py
- csms/tests/test_reconciliation_be208.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

IMPLEMENTED:
- expanded ReconciliationRun/Item/Exception with run type/cutoff/close/watermark, canonical EsLatin/Provider/funds references, merchant and Decimal money facts, fee/refund/hold/release fields, mismatch/conflict, owner/due/approval state and bounded replay/lease counters
- added ReconciliationSourceFact, ReconciliationSourceWatermark, ReconciliationWorkItem and bounded one-time ReconciliationExport models; fresh test startup creates them through existing Base.metadata.create_all
- added provider-neutral source fact ingestion with canonical-field-only validation, source/reference/fingerprint dedupe, conflict preservation, watermark advancement and no raw Provider payload acceptance
- added bounded continuous/daily matching, missing-source and amount/merchant/fee/release mismatch exceptions, bounded replay, tenant/platform scope enforcement, lease/retry/dead-letter handling and 24-hour timing/fee/funds-release temporary acceptance with distinct actors and expiry fail-closed
- exposed frozen PAY-MP-002-v1 Admin reconciliation run/item/exception/resolution/temporary-acceptance/CSV export routes with server-side permission/scope checks, cursor envelopes, idempotency and safe projections
- preserved Invoice/Payment/Allocation authority and existing Provider-neutral webhook/recheck paths; no historical import or guessed backfill

COMMANDS_RUN:
- startup SELF_CHECK after reloading AGENTS.md, RUNTIME_POLICY, backend-agent skill, architecture/boundaries, ADR-005, PAY-MP-002 docs, frozen contract and current diff
- SQLite empty-database model initialization check for all six BE-208 core tables plus export table
- `python3 -m pytest -q tests/test_reconciliation_be208.py`
- `python3 -m pytest -q tests/test_pay_mp_002_be201_schema.py tests/test_recovery_service_be202.py tests/test_financial_eligibility_be203.py tests/test_payment_provider_capabilities_be204.py tests/test_pay_mp_002_be206_history.py tests/test_payment_refunds_be207.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py`
- adjacent checkout/payment/charging/OCPP regression command covering 165 tests
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin_compile_cache_be208_final python3 -m compileall -q -f app tests`
- `git diff --check`

TEST_RESULTS:
- BE-208 direct: `7 passed, 1 warning`
- BE-201~207 focused regression: `54 passed, 5 skipped, 5 warnings`
- adjacent checkout/payment/charging/OCPP regression: `165 passed, 1 warning`
- compileall: passed
- git diff --check: passed
- first regression attempt exposed a legacy BE-203 fixture that omitted the new canonical reference; making the additive compatibility field nullable preserved that existing diagnostic path while BE-208 writes remain canonical
- no persistent/test database cleanup was required; each direct test used the existing fresh in-memory SQLite fixture

CONTRACT_CHANGES:
- no frozen PAY-MP-002-v1 state, permission, HTTP, sort, error or public event semantics changed
- additive internal Admin reconciliation resources/routes implement the existing frozen contract; no migration file was added or modified

ARCHITECTURE_COMPLIANCE:
- coupling level remains the approved BE-208 reconciliation domain; no BE-209/BE-210/D-204 implementation
- canonical source facts are bounded and Provider-neutral; raw payloads are rejected and never projected
- no historical migration/import/backfill, production database/configuration, real Provider or real payment was used
- tenant/platform scope is server-derived; no client tenant is trusted; Invoice/Payment/Allocation authority is not rewritten

RISKS:
- independent backend QA must verify BE-208; this implementation agent does not self-approve QA
- no production release: PAYMENT_RAILS_ENABLED remains unchanged and D-204/BE-205, frontend QA, E2E and human release gates remain blocked/separate
- current application startup still logs pre-existing Python 3.9 annotation failures for `app.recovery` and `admin.refunds`; the new BE-208 reconciliation router itself imports and exposes 11 frozen reconciliation routes
```

## BE-209 implementation handoff

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: PAY-MP-002 / BE-209 backend implementation and direct tests
TASK: SupportCase、RBAC、租户隔离与审批意图

CHANGED_FILES:
- csms/app/services/support_cases.py
- csms/app/api/v1/app/support.py
- csms/app/api/v1/admin/support.py
- csms/app/api/v1/__init__.py
- csms/tests/test_support_cases_be209.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

IMPLEMENTED:
- reused existing BE-201 SupportCase/CaseEvent typed tables, AuditLog and tenant-scoped Outbox; no migration or production schema change
- added App own-user context validation for invoice/session/payment/recovery/refund/chargeback references; cross-user and unavailable context return safe 404
- added Admin frozen support list/detail/event routes with exact `support.manage`, cursor/sort, tenant/platform scope and cross-tenant existence hiding
- added case lifecycle/version checks, assignment, first-response/decision SLA targets, urgent charging issue capability projection and safe user-visible timeline
- added support state/notification Outbox events with retryable handoff, idempotency fingerprint conflict detection and payloads containing only safe references
- support events only change SupportCase collaboration state; they do not mutate Invoice, Payment, D1, Reconciliation or rail authority

COMMANDS_RUN:
- startup SELF_CHECK after reloading governance, runtime policy, backend skill, architecture/boundaries, ADR-005, PAY-MP-002 frozen contract and BE-201~208 final QA evidence
- `python3 -m pytest -q tests/test_support_cases_be209.py`
- focused BE-201~208/payment/RBAC/tenant/security suite
- adjacent charging/OCPP/permission regression suite
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin_compile_cache_be209_full python3 -m compileall -q -f app tests`
- `git diff --check`

TEST_RESULTS:
- BE-209 direct: `4 passed, 1 warning`
- focused BE-201~208/payment/RBAC/tenant/security: `93 passed, 5 skipped, 5 warnings`
- adjacent charging/OCPP/permission regression: `87 passed, 1 warning`
- full app/tests compileall: passed
- `git diff --check`: passed

CONTRACT_CHANGES:
- none; PAY-MP-002-v1 permission, HTTP, body, sort, error and public event semantics remain frozen
- no migration added or modified; no production DB/configuration, real email, real payment or second Provider used

ARCHITECTURE_COMPLIANCE:
- approved BE-209 Operations/Support + Identity/Tenant domain only; existing BE-201 typed schema and Outbox reused
- server-derived App ownership and Admin tenant scope; no implicit admin permission; financial and D1 authorities remain unchanged
- BE-210, D-204/BE-205, frontend and production release untouched

RISKS:
- awaiting independent backend QA; this implementation handoff does not self-approve QA
- application startup still emits pre-existing Python 3.9 annotation errors for unrelated `app.recovery` and `admin.refunds` imports
- production DB/schema deployment, real email/Provider, frontend QA, E2E and human release gates remain separate
```

## BE-210 implementation handoff（backend-agent）

```text
STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: PAY-MP-002 / BE-210 backend implementation, local/test schema initialization and direct tests

CHANGED_FILES:
- csms/app/database/models.py
- csms/app/database/__init__.py
- csms/app/services/runtime_rail_control.py
- csms/app/api/v1/admin/runtime_rails.py
- csms/app/api/v1/__init__.py
- csms/app/services/financial_eligibility.py
- csms/app/services/recovery_service.py
- csms/app/api/v1/app/recovery.py
- csms/app/services/payment_reconciliation.py
- csms/app/services/payment_checkout/service.py
- csms/app/api/v1/app/payments.py
- csms/tests/test_runtime_rail_control_be210.py
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

IMPLEMENTED:
- frozen PAY-MP-002-v1 paid_admission/payment_creation runtime rails with platform/provider/tenant/site server-resolved scope, version checks, reason/incident/health references, audit and existing single Outbox handoff
- close, reopen request, approve/reject, no-auto-recovery and distinct-actor enforcement; unknown or failed health cannot reopen, and overlapping applicable scopes fail closed
- RuntimeRailControlService composition with FinancialEligibility/ChargingAdmissionPreflight and provider-neutral payment creation orchestration; rail_closed is not a FinancialEligibility result
- only applicable new payment/charging creation entrances are blocked; active query, webhook, refund, chargeback, reconciliation, history, support and StopTransaction paths remain convergent, with no payment-close RemoteStop
- PAYMENT_RAILS_ENABLED remains a separate deployment gate, not runtime rail state
- local/test Base.metadata schema models only; no migration, history backfill, production DB/configuration or live payment/provider operation

COMMANDS_RUN:
- startup and final Mandatory SELF_CHECK for PAY-MP-002 / BE-210 scope
- `python3 -m pytest -q tests/test_runtime_rail_control_be210.py`
- focused BE-201~209/payment/reconciliation/support regression command
- adjacent payment/charging/OCPP regression command
- final affected BE-210/payment/charging/reconciliation/support regression command
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin_compile_be210_final python3 -m compileall -q -f app tests`
- `git diff --check`

TEST_RESULTS:
- BE-210 direct: `3 passed`
- focused BE-201~209/payment/reconciliation/support: `68 passed, 5 skipped`
- adjacent payment/charging/OCPP: `174 passed`
- final affected regression: `95 passed, 5 warnings`
- targeted compileall: passed; final diff check: passed

CONTRACT_CHANGES:
- none; PAY-MP-002-v1 API, permissions, errors, HTTP status, projection and sort semantics remain frozen
- no migration file, frontend, QA report, production configuration or public event contract changed

ARCHITECTURE_COMPLIANCE:
- approved BE-210 runtime-control domain only; existing FinancialEligibility, ChargingAdmissionPreflight, provider-neutral payment orchestration, AuditLog and single Outbox boundaries remain authoritative
- tenant/site/provider/platform scope is server-resolved and permission checked; platform rail operation is not available to ordinary tenant actors
- BE-211 and D-204/BE-205 risk-budget/reserve/threshold/hard-stop scope was not implemented

RISKS:
- independent backend QA is required; this implementation handoff does not self-approve QA
- evidence is local/test-only; production DB, live Provider, real payment, deployment and E2E remain separate gates
- existing unrelated dirty worktree changes were preserved
```

## BE-211 implementation handoff（backend-agent）

STATUS: done-awaiting-independent-backend-qa
OWNER: backend-agent
SCOPE: PAY-MP-002 / BE-211 compatibility, test-data cleanup boundaries, local measurement and QA/E2E handoff

CHANGED_FILES:
- csms/tests/test_pay_mp_002_be211_compatibility.py
- csms/scripts/measure_be211_capacity.py
- docs/features/PAY-MP-002/backend/BE-211_HANDOFF.md
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md

IMPLEMENTED:
- isolated empty/current test schema Base.metadata.create_all repeatability and non-destructive startup checks
- production refusal and exact-reference allowlist checks for deterministic local/test cleanup; no tenant-wide deletion, import or guessed backfill
- bounded local SQLite measurements for indexed writes, lock wait, connection-pool checkout, queue lease/DLQ, fake Provider burst, MeterValues Redis fallback and cursor-batched reconciliation
- explicit P001/P002, OCPP/Webhook/Admin, Outbox scope, BE-201~210 regression inputs and deterministic E2E fixture contract in the handoff document

COMMANDS_RUN:
- startup SELF_CHECK after reloading governance, runtime policy, backend skill, architecture/boundaries, ADR-005, PAY-MP-002-v1 and BE-201~210 final QA evidence
- pytest direct BE-211 compatibility
- measure_be211_capacity.py --rows 200 --workers 8 --batch-size 50
- bounded BE-201~210/P001/OCPP/Webhook/Admin regression command (listed in BE-211_HANDOFF.md)
- compileall app tests scripts/measure_be211_capacity.py
- git diff --check

TEST_RESULTS:
- BE-211 direct: 4 passed in 0.35s
- bounded backend regression: 151 passed, 5 skipped, 5 warnings in 32.36s
- local measurement: production_capacity_claim=false; index observed; lock busy timeout observed; pool 4/16 bounded checkouts; 200/200 queue lease with 1 deterministic DLQ; 200/200 fake Provider burst with peak 8; Redis outage fallback should_persist=true; reconciliation 200/200 in 4 bounded batches
- compile and diff-check: passed

CONTRACT_CHANGES:
- none; PAY-MP-002-v1, P001 compatibility, OCPP/Webhook/Admin contracts and Outbox scope contract remain frozen
- no migration file, schema migration, history import, production DB/configuration, real Provider/payment, frontend or QA report changed

ARCHITECTURE_COMPLIANCE:
- local/test-only measurement and existing service/schema boundaries; Decimal/UTC, server-derived scope, immutable authority and fail-closed unknown-state constraints retained
- rollback/disable evidence remains BE-210: only new applicable entrances close; convergence paths and active OCPP facts remain untouched; no D-204/BE-205 runtime

RISKS:
- independent backend QA must review this handoff; implementation evidence does not self-approve QA
- SQLite lock/rate observations are not PostgreSQL or production capacity proof; real Redis/queue/Provider, production deployment, frontend QA and E2E remain separate
- PAYMENT_RAILS_ENABLED remains false and production remains no-go

## D-204-B v2 contract refresh handoff

- `contracts/API.md` is now `PAY-MP-002-v2 / frozen`, with P001 default and `PAY-MP-002-v1` compatibility preserved.
- BE-205 may begin implementation against the single shared v2 contract. The required projections, errors, client-authority restrictions, UTC rolling window and internal event envelope are frozen; backend-agent must not invent alternate fields or endpoints.
- This contract task did not modify runtime code, migrations, deployment, production configuration or payment rails.
