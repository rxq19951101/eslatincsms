---
id: PAY-MP-002-BE-ARCHITECTURE
change_id: CHG-20260812-002
feature_id: PAY-MP-002
status: architecture-approved
verdict: approved
contract_status: frozen
contract_version: PAY-MP-002-v2
compatible_contracts: P001-default, PAY-MP-002-v1
implementation_authorization: be205-contract-frozen-only
owner: backend-agent
---

# PAY-MP-002 后端架构审核（修订输入）

## 1. 裁决与范围

当前 C3 代码架构 verdict 已由 architecture-agent 限定复审为 `approved`；
ADR-005 为 `accepted-target / implementation-changes-required / production-no-go`。
CF-201～CF-206 已关闭并统一冻结为 `PAY-MP-002-v1`。非 D-204 范围获得
`phased-non-d204-only` 实施授权；这不代表 QA 通过或生产 GO。

没有新的产品 blocker：D-201、D-202、D-203 Option 1、D-205-A、D-206-B、
D-207-B、D-208-B、D-209-B 和 D-210-B 已有可核验的 Product Owner 批准。
D-204 目标架构与 v2 contract 已批准/冻结；runtime、独立 QA/E2E、容量和真实资金仍严格阻塞
BE-205、任何风险默认参数和真实资金发布。

本文件只审查后端边界、事实所有权、状态机、数据/API/事件契约、事务、租户/RBAC、
写入压力、兼容/回滚以及 QA/E2E 接口。未修改业务代码、数据库、迁移、前端、部署或生产配置。

## 2. 当前代码基线与架构偏差

只读核验的关键事实如下：

| 区域 | 当前代码事实 | P002 偏差 |
|---|---|---|
| Invoice/Billing | `Invoice` 按 session 唯一，金额由 Billing 生成；钱包/卡/免费分支已存在 | 没有 typed recovery attempt/allocation，无法表达同一 Invoice 的多次尝试与唯一赢家 |
| Payment | `PaymentOrder` 的 tenant、Invoice、Session 和 provider hints 部分在可变 `metadata`；`Payment` 没有 operation/allocation 唯一键 | metadata 不能作为资金、D1 或 attempt authority |
| D1 | `/charging/start` 的 `_has_global_unpaid_charging_bill` 只查 pending Invoice 与 completed/unpaid Session | 不识别 refund、chargeback、late reversal、funds unknown 或 reconciliation mismatch，且不是集中 evaluator |
| Refund | `PaymentRefundService` 在 PaymentOrder 行锁下反查 Provider，并将摘要写入 `metadata.refund_summary` | 没有结构化退款申请/审批/attempt；当前 Admin 可由单一 superadmin 直接触发 |
| Webhook/reconciliation | Provider Webhook 记录后主动反查并共享 reconcile；尚无三方批次/差异/临时例外事实 | 无 EsLatin/Provider/实际资金三方权威模型、lease/replay/DLQ |
| RBAC/tenant | Admin payment API 为 `is_super_admin`；`PaymentOrder` 无直接 `tenant_id` | 不满足 D-206-B/D-207-B/D-208-B 的资源作用域和职责分离 |
| Support | 只有 `SupportMessage` 文本和 replied 状态 | 无非敏感上下文关联、SLA、责任人、CaseEvent 或紧急支持状态 |
| Runtime rail | `PAYMENT_RAILS_ENABLED` 是部署环境总开关 | 不是双轴、可作用域、版本化 runtime control；不能由前端或普通配置替代 |
| OCPP | Charging/OCPP 拥有 Start/Stop/MeterValues/RemoteStart/Stop 和 Outbox | 保持 owner；D-204 前不得增加 risk counter、RemoteStop 阈值或 hard-stop worker |
| App history | `/api/v1/app/transactions` 当前为 bare array、offset/limit，`energy_kwh/duration_minutes` 为 number/null | P001 必须原样保持；P002 只经 vendor `Accept` 获得 cursor/decimal-string |
| Outbox | `outbox_events.tenant_id NOT NULL`，唯一键 `(tenant_id,idempotency_key)` | platform/cross-tenant event 无合法 scope；需单表 additive scope，禁止伪造 tenant |

这些偏差证明需要 additive P002 子域，而不是继续扩展 JSON、Redis 或单一 Admin endpoint。

## 3. 目标 owner 与依赖方向

| 事实 | 后端 owner | 允许的依赖 |
|---|---|---|
| Invoice、PricingSnapshot、Session 用量和原始应收 | Billing / Charging | Payment 只读引用；不得改写金额含义 |
| RecoveryAttempt、PaymentAllocation、Provider reconciliation | Payment/Recovery/Reconciliation | Billing contract、Provider adapter、Wallet service |
| FinancialEligibility/D1 | Payment/Billing evaluator；Charging 只执行结果 | Invoice、Allocation、Refund、Chargeback、Funds/Reconciliation facts |
| RefundCase/RefundAttempt、ChargebackCase | Payment/Operations | Provider adapter、Audit、Support reference |
| 三方对账 run/item/exception | Reconciliation/Finance operations | canonical Provider facts、Billing/Payment、资金导入边界 |
| Runtime rail control | Operations/Platform control | Identity/RBAC、Audit、Charging admission/payment creation preflight |
| SupportCase/CaseEvent | Operations/Support | 非敏感财务/充电 reference；不能写财务状态 |
| Admin 用户、成员、角色、租户授权 | Identity/Tenant | 所有 Admin service/API |
| OCPP socket、Start/Stop/MeterValues | OCPP/Charging | 只消费服务端 preflight/Outbox contract |

依赖方向固定为：

```text
Identity/Tenant -> scoped command authorization
Billing/Charging -> immutable Invoice/Session facts
Provider adapter -> canonical provider facts
Payment/Recovery/Reconciliation -> Allocation/Refund/Chargeback/Funds facts
FinancialEligibility -> Charging admission result
Operations -> Support/Rail/Approval intents
Outbox -> async side effects and replay
```

Payment 不调用 OCPP transport，不直接修改 Session/MeterValues；OCPP handler 不调用 Provider；Support 不改财务事实；前端只消费候选共享契约。

## 4. AR-201～AR-210 关闭矩阵

| 编号 | 后端设计结论 | 证据位置/实施门禁 |
|---|---|---|
| AR-201 | backend/frontend 共同使用本文和 frozen `contracts/API.md` 的 canonical facts；CF-206 已完成同版本同步 | `TECH_DESIGN.md` §2、`contracts/API.md` §1/§8 |
| AR-202 | RecoveryAttempt 与 PaymentAllocation 为 typed authority；钱包、新卡、保存卡共用状态机；metadata 仅兼容摘要 | `TECH_DESIGN.md` §3 |
| AR-203 | 唯一 FinancialEligibility evaluator；D1 依据持久 facts，支持 re-block；不得依赖 App flag/Redis/UI | `TECH_DESIGN.md` §4 |
| AR-204 | RefundCase/Approval/Attempt 与 ChargebackCase 分离；退款发起人与批准人不同；累计退款不超过实付 | `TECH_DESIGN.md` §5、`TASKS.md` BE-207 |
| AR-205 | 持续逐笔匹配 + Bogotá 营业日三方批次；差异、截止、24h 临时例外和双人批准均为 typed facts | `TECH_DESIGN.md` §6、`TASKS.md` BE-208 |
| AR-206 | `paid_admission` 与 `payment_creation` 双轴、按平台/provider/tenant/site 作用域；close 一人，reopen 不同人员批准，不自动恢复 | `TECH_DESIGN.md` §7、`TASKS.md` BE-210 |
| AR-207 | SupportCase/CaseEvent 只携带非敏感 reference，含责任人/SLA/邮件/紧急支持状态 | `TECH_DESIGN.md` §8、`TASKS.md` BE-209 |
| AR-208 | P002 orchestration 使用 Provider-neutral capabilities；Mercado Pago 只在 adapter，P001 A1/B1/C1 保持 | `TECH_DESIGN.md` §9 |
| AR-209 | 所有新增 schema additive、版本化、可校验、可回滚；无业务历史导入；旧数据保持 legacy/unknown | `TECH_DESIGN.md` §10 |
| AR-210 | backend QA、frontend QA、E2E 和 R0～R4 发布证据均有接口；D-204 前 BE-205/真实资金仍 blocked | `TECH_DESIGN.md` §13、`TASKS.md` §4 |

### 4.1 CF-201～CF-206 收敛状态

| Finding | 唯一后端候选 | 状态/证据 |
|---|---|---|
| CF-201 | 固定 `provider_approved→approved`、`committed→confirmed`、`needs_review→unknown`、`recheck_required→evaluating`；迟到非赢家固定 `manual_review/duplicate_approval/allocation=null` | closed-by-backend；API §3.10 |
| CF-202 | 唯一协商机制为 `Accept: application/vnd.eslatin.pay-mp-002.v1+json`；无 vendor media type 始终 P001 array/offset/旧类型 | closed-by-backend；API §5.7 |
| CF-203 | FinancialEligibility 只含财务事实；QR 解析资源后由 ChargingAdmissionPreflight 组合 scoped rail；`/charging/start` 重算 | closed-by-backend；API §5.6、TECH §4 |
| CF-204 | 现有 Outbox 单表新增 `scope_type/scope_ref`，tenant_id nullable + CHECK；platform tenant_id=NULL，禁止 dummy tenant | closed-by-backend；API §8、TECH §10.2 |
| CF-205 | permission、每个 endpoint 成功 HTTP/body、stable sort、单一错误码与 CSV `queued→generating→ready→downloaded` 生命周期固定 | closed-by-backend；API §6/§7 |
| CF-206 | frontend 已同步并引用 v1 compatibility 与 v2 contract，architecture-agent 限定复审已批准 | closed；frozen contract / architecture-approved |

## 5. 关键架构决定

1. **Invoice 不可变，Allocation 才是结算赢家。** Recovery 只能引用 Invoice 的服务端金额，不能更新用量、价格快照或原 Payment。每个 Invoice 允许多个 sequential attempts，但最多一个足额 `committed` allocation。
2. **Provider approval 不等于本地结清。** Provider `approved` 先进入 typed attempt/provider fact；只有金额、币种、merchant、tenant、Invoice ownership 和全额 allocation 在同一短事务中通过，才可让 evaluator 重新计算 D1。
3. **D1 只由 evaluator 计算。** `/charging/start` 在发出 RemoteStart 前调用 evaluator；`eligible` 不是可永久缓存的属性。退款、拒付、late reversal、Provider unknown、资金 unknown、reconciliation mismatch 都能产生新的 blocking fact。
4. **副作用使用 Outbox。** Provider webhook/查询、邮件、支持通知、对账导入和 rail health check 的异步动作都有 owner、唯一键、lease、retry、dead-letter、replay 和审计；Redis/UI/单次 Webhook 不能成为财务 authority。
5. **不引入 D-204 runtime。** 当前不创建 risk policy 默认值、risk ledger、reserve/consume/release、MeterValues 风险计数、RemoteStop threshold 或 hard-stop worker。BE-205 只保留为 blocked design input。
6. **兼容靠显式 media type。** 同一路径的 P001 默认响应保持原 array/offset/旧类型；只有 `PAY-MP-002-v1` vendor `Accept` 获得 cursor/decimal-string。禁止按 query/字段猜版本。
7. **FinancialEligibility 与 rail 分层。** D1 evaluator 不读取 rail；Charging 用服务端 QR/asset/pricing/merchant context 组合 paid-admission rail，并在 start 请求内重算。
8. **Platform Outbox 不借 tenant。** platform event 使用 `tenant_id=NULL + scope_ref=platform:eslatin`，tenant event 的 scope_ref 与真实 tenant_id 受 DB CHECK 约束。

## 6. 迁移、兼容与回滚裁决

- 后续实现必须新增独立、版本化的 typed tables/indexes/constraints；不把 `PaymentOrder.metadata` 自动 backfill 成事实，不伪造历史 refund/chargeback/funds/reconciliation/risk facts。
- 展开阶段先建表/索引和双读能力，再以 feature gate 暴露 P002 API；切换阶段由新 service 写 typed facts，并保留 P001 读路径；校验阶段检查 tenant、金额、唯一性、孤儿和状态迁移。
- 空库必须执行仓库认可的显式 migration chain；不能依赖启动 `create_all`。既有库无业务导入要求，但必须有 schema version、checksum、容量/锁评估和混合版本兼容。
- 回滚只关闭 P002 新入口、Recovery/Refund/Recon/Rail/Support 写入口和扩展控制范围；保留已产生的 Invoice/Payment/typed facts、Webhook、OCPP、Audit 和 Outbox，不 drop、不反向改写、不自动退款、不自动 reopen。无法确认的资金/回缴状态继续 `unknown`，D1 fail closed。

## 7. 当前批准门禁

- `contracts/API.md` 已冻结为 `PAY-MP-002-v1`；实现不得自行改变状态、错误、权限、分页、HTTP 或事件语义。
- CF-201～CF-206 已关闭，architecture-agent 已批准非 D-204 分批实施；每批仍需独立 QA，跨模块完成后仍需 E2E 和人工审查。
- `PAYMENT_RAILS_ENABLED=false` 的既有生产门禁保持不变；本轮没有读取/修改生产值。
- 未发现需要人工产品选择的纯技术缺口；若产品未来要求部分补缴、收据文件、Provider authorization/capture 或 D-204 风险参数，必须另行产品/架构门禁。

## 8. Completion SELF_CHECK

- 原始范围已保留：只关闭 CF-201～CF-205，并为 CF-206 固定统一版本；未进入实现或扩展研究。
- 当前活动直接形成架构复审输入；五个授权文件之外无写入。
- 无未解决 scope drift、重复分析循环或隐藏治理冲突；重大自我纠正次数为 0。
- 不需要新的产品选择；CF-206 与 architecture-agent 限定复审已完成，D-204/BE-205 和真实资金发布仍是明确 blocker。
- `DOC_CONSISTENCY_OK` 已同步 architecture-approved、frozen contract 和 phased non-D204 授权事实；未改变既有架构内容。

## 9. 统一交接

STATUS: done-architecture-approved

CHANGED_FILES:
- docs/features/PAY-MP-002/backend/ARCHITECTURE_REVIEW.md

COMMANDS_RUN:
- 重新加载 AGENTS.md、RUNTIME_POLICY、backend-agent skill 和权威文档；执行 startup SELF_CHECK
- 只读核验 CF-201～CF-205、P001 transactions、Outbox model/service、RBAC 和当前五个授权文档

TEST_RESULTS:
- 本文件仅同步既有 architecture-agent gate；不构成 QA 或生产通过

CONTRACT_CHANGES:
- v2 contract refresh 已冻结；`PAY-MP-002-v1` 作为兼容基线保留

ARCHITECTURE_COMPLIANCE:
- C3；保持 ADR-005 target、P001 Invoice/Hosted/OCPP owner、Decimal/UTC、tenant/RBAC、Outbox 和 production-no-go
- AR-201～AR-210 均有后端设计映射；D-204 隔离，BE-205/默认风险参数/真实资金继续 blocked

RISKS:
- BE-201 独立 QA 失败项修复后仍需 fresh independent re-QA；BE-202 及后续未实施
- D-204 v2 contract 已冻结；BE-205 runtime、独立 QA/E2E、容量和真实资金发布仍 blocked；生产 NO-GO

## D-204-B v2 contract refresh handoff

- `contracts/API.md` 现为 `PAY-MP-002-v2 / frozen`；P001 默认 API 与 `PAY-MP-002-v1` 保持兼容，v1 不承载 D-204 字段。
- 本后端文档同步引用 RiskSession/RiskStop/ProviderResolution safe projections、server-only risk decision/status/errors、UTC rolling 24h window、expected_version/idempotency 和 `risk-event.v2` internal event envelope。
- BE-205 当前状态为 `implementation-ready-for-BE205`，但本次仅完成契约刷新；不得在本交接中实现 endpoint、migration、worker、OCPP command 或生产配置。
