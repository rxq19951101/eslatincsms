---
id: PAY-MP-002
change_id: CHG-20260812-002
status: fe-201-qa-closed-awaiting-e2e-release-gates
owner: frontend-agent
contract_status: frozen
contract_version: PAY-MP-002-v2
compatible_contracts: P001-default, PAY-MP-002-v1
frontend_contract_sync: cf-206-closed-d204-v2
implementation_authorization: be205-contract-frozen-only
---

# PAY-MP-002 前端任务拆分

## 1. 执行门禁

本文件保留原始前端任务拆分和历史门禁说明；FE-201 已完成实现并通过 final independent frontend QA。FE-202 及后续完整 App/Admin 运营旅程仍需按原依赖和独立 QA 门禁推进。

2026-08-15 在外部 Provider HTTP 500 暂不处理的范围内，FE-202 已完成 App 列表/详情首个切片，FE-203 已接入 admission preflight，FE-204 已完成 App 历史列表/详情首个切片，FE-205 已完成 SupportCase 列表/详情和上下文创建首个切片：`UnpaidBillsScreen` 使用 typed Invoice cursor 列表并可进入详情，通过 `available_methods` 进入钱包/新卡/已保存卡补缴；银行卡补缴复用 checkout coordinator 保存会话引用，充电结束的 unpaid 结果提供未结账单入口，Checkout 完成后回到未结账单列表；开始充电前读取服务端 financial eligibility/scoped rail，且仍由服务端 start 再次裁决；ChargingHistory 列表和详情显式使用 P002 vendor `Accept`，展示服务端 payment/invoice/data_quality/timeline 投影，同时保留 P001 adapter 兼容；Account 增加支持案件入口，展示服务端 SupportCase 状态、SLA、安全 timeline 和关联退款引用；账单/历史详情仅在服务端 `allowed_actions` 含 `contact_support` 时，使用已授权 invoice/session context 创建 SupportCase。该切片不替代 FE-202/FE-203 的 D1 重新评估、恢复状态恢复、RefundCase 运营流程和完整独立 QA。

CF-206 已完成；本任务集现引用冻结的 `PAY-MP-002-v2`，并保留 P001 default 与 `PAY-MP-002-v1` compatibility；不得引入第二套状态、版本协商、permission、HTTP/body、错误码、stable sort 或 CSV 生命周期。

D-204 v2 safe projection、状态/错误映射和客户端 authority prohibition 已冻结；本任务集仍不得实现 risk runtime、硬停止 command、migration 或真实资金开关。

## 2. 依赖顺序

```text
architecture rereview
→ contract freeze
→ backend typed resources/adapters
→ FE-201 shared frontend foundation
→ FE-202/203 App unpaid recovery
→ FE-204/205 App history/refund/support
→ FE-206 Admin foundation
→ FE-207/208/209/210 Admin operations
→ FE-211 frontend QA handoff
```

前后端不得各自改变 resource/status/error/approval contract。后端未提供 authoritative projection 时，前端任务必须停在 adapter 边界，不以 mock 或本地计算补齐业务事实。

## 3. 任务列表

### FE-201：前端契约 Adapter、状态与 i18n 基线

**范围：App + Admin，各自实现，不共享运行时 store。**

- 为 `PAY-MP-002-v1` cursor page、canonical errors、unknown enum、Decimal string、UTC、safe refs 建立 typed adapter。
- 固定 CF-201 映射：`provider_approved→approved`、`committed→confirmed`、`needs_review→unknown`、`recheck_required→evaluating`；迟到非赢家为 `manual_review/duplicate_approval/allocation=null`。
- transactions P002 adapter 只发送 `Accept: application/vnd.eslatin.pay-mp-002.v1+json`；P001 adapter 保持 bare array/offset/number-null，不按 query/字段猜版本。
- App/Admin 都保留 `code/reference/retryable/retry_after_seconds` 并映射 es-CO/en/zh。
- 定义 loading/empty/processing/action-required/unknown/error/recovery 组件状态约束。
- 增加敏感字段和 URL allowlist 测试基线。
- 不实现 D1、金额、tenant/RBAC、rail 或审批计算。

**依赖：** frozen API；后端 shared DTO 示例。

**完成证据：** P001/P002 media-type golden tests、CF-201 mapping/duplicate approval tests、406/400/Vary、未知状态 fail-closed、失败不变 empty、金额不转 float、es-CO key 完整。

### FE-202：App 欠费列表与详情

- 将 `UnpaidBillsScreen` 从旧数组/session API 切换到 Invoice cursor resource。
- 新增 `UnpaidBillDetail` typed route 和页面。
- 显示只读 Invoice/charging/pricing/amount/timeline/available methods/allowed actions。
- 在 D1 阻断、PaymentHub/Account 增加欠费和支持入口。
- 覆盖 refresh/load-more/cursor-invalid/offline/error/empty/legacy/unknown。

**依赖：** FE-201；后端 unpaid list/detail。

**禁止：** 客户端提交 amount/currency/tenant/merchant、静默合并账单、从空列表推断 eligible。

### FE-203：App Recovery 与 D1 重新评估

- 新增 RecoveryAttempt 创建/查询 adapter 与 `RecoveryStatus` route/page。
- 在既有 checkout coordinator 中持久化非敏感 attempt/invoice 关联和 in-flight GET dedupe。
- 支持 wallet/new-card/saved-card + Hosted CVV；执行 typed next action 和 URL allowlist。
- 对重复点击、网络 unknown、应用重启、前后台切换、外部回跳、checkout 过期进行恢复。
- allocation confirmed 后刷新 FinancialEligibility；该结果只表达财务资格，不包含 rail。
- 用户返回充电时用 `qr_token + settlement_method` 调 `/app/charging/preflight`，只消费服务端解析的资源和 scoped rail；预检不是 capability token。
- 最终 `/charging/start` 由服务端重新执行 FinancialEligibility + scoped rail 组合 preflight；前端不发送 tenant/site/provider/scope，也不凭 cached eligible 启动。
- `PaymentResult` 保持 P001 路径兼容，unpaid purpose 不把 approved 当结清。

**依赖：** FE-202；后端 RecoveryAttempt/Allocation/Eligibility；P001 checkout contract。

### FE-204：App 基础历史与支付事实投影

- 在现有 transactions 路径建立显式双 projection adapter：P001 默认 array/offset/旧类型不变，P002 vendor Accept 才使用 cursor/decimal-string；不建立第二套 charging-history API。
- 展示 Payment/Recovery/Refund/Chargeback/Support 非敏感 timeline 和 `data_quality`。
- 显式区分 approved、allocated、refunded、disputed、unknown。
- 保持既有 ChargingHistory 路由兼容和 P001 回归。

**依赖：** FE-201；后端 history projection。

**非目标：** PDF、下载、邮件、DIAN 收据/发票。

### FE-205：App 结构化支持与退款状态

- 新增 SupportCase 列表/详情及上下文创建入口。
- `refund_request` 只创建支持诉求；关联 RefundCase 后展示服务端状态、SLA 和 allowed actions。
- 支持 invoice/session/recovery/payment/refund 的单一受权引用；不允许任意 tenant/provider reference。
- 自由文本提示不得输入 PAN/CVV/密码/证件。

**依赖：** FE-201/204；后端 SupportCase/Refund projection。

### FE-206：Admin Provider-neutral 运营壳与 RBAC

- 建立退款、拒付、对账、支持、rail、审计的导航/路由/adapter 壳。
- 只使用 contract 固定 permissions：`payment.read`, `refund.request`, `refund.approve`, `chargeback.read`, `reconciliation.read`, `reconciliation.resolve`, `reconciliation.exception.request`, `reconciliation.exception.approve`, `support.manage`, `rail.read`, `rail.close`, `rail.reopen.request`, `rail.reopen.approve`, `audit.read`，并结合 resource `allowed_actions`；移除新能力对 `is_super_admin` 的硬编码依赖。
- 按 §6 矩阵固定 endpoint 成功 HTTP/body 与 stable sort；统一 URL filters、cursor pages、scope banner、version、safe timeline 和 canonical error UX。
- tenant context 切换时隔离 cache；服务端仍是 tenant/RBAC authority。
- 不读取 raw Outbox，不为 platform scope 构造 dummy/selected tenant；`platform:eslatin` 可无 tenant。

**依赖：** FE-201；后端 Admin read projections。

### FE-207：Admin 退款双控

- RefundCase 列表/详情/创建 request。
- 不同授权 actor 的 approve/reject decision UI；same-actor 不在前端推导，由服务端 `allowed_actions`/403/409 决定。
- 提交 `expected_version` 和 idempotency key；处理 pending/expired/conflict/provider-processing/unknown/partial/refunded/rejected。
- 展示 initiator/approver/reason/audit refs，不显示 raw Provider payload。

**依赖：** FE-206；后端 RefundCase/Approval。

### FE-208：Admin 三方对账与 CSV 导出

- ReconciliationRun 列表/详情、Item/Exception 分页与 source watermarks。
- Exception resolution intent；不直接设置 matched。
- 临时例外 create request + different-actor decision，显示服务端 `expires_at`。
- CSV 创建只接受 `202 ReconciliationExportProjection`；轮询 `queued→generating→ready→downloaded`，处理 failed/expired，并且仅 ready 使用固定同源 path 一次下载。
- 显式处理 `EXPORT_NOT_READY/EXPORT_FAILED/EXPORT_CONSUMED/EXPORT_EXPIRED`、权限/scope、content-type/filename 与 audit reference。

**依赖：** FE-206；后端 recon run/item/exception/approval/export。

### FE-209：Admin 拒付、支持与审计

- ChargebackCase 列表/详情、deadline/hold/result/unknown 投影。
- SupportCase 列表/详情/安全事件追加；事件不直接改账务终态。
- AuditEvent 分页筛选；敏感字段和 raw Provider payload 永不渲染。
- 所有资源覆盖 permission denied、not found、unknown、stale version 和 tenant 切换。

**依赖：** FE-206；后端 chargeback/support/audit resources。

### FE-210：Admin 双轴运行时 rail

- 展示 `paid_admission` 与 `payment_creation` 的 scoped controls、version、reason、incident、actor 和状态。
- close 单人受限操作；reopen 为 request + different-actor decision。
- health-check failed/unknown 时保持 closed；无自动恢复或前端定时切换。
- 清晰说明不停止 Webhook/query/refund/chargeback/reconciliation/history/support/进行中 OCPP 会话。

**依赖：** FE-206；后端 RuntimeRailControl/Approval。

### FE-211：前端回归、可访问性与 QA 交接

- App：欠费/恢复/历史/退款/支持完整状态矩阵、deeplink、重启、offline、重复点击。
- Admin：退款/例外/rail 三类双控、RBAC、tenant/cache、CSV、审计。
- 运行 App/Admin build、typecheck、unit/integration tests 和相邻 P001 回归。
- es-CO 主语言、320px App、Admin 桌面/最小宽度、键盘/focus/live-region/screen-reader 验证。
- 输出独立 qa-agent 所需 fixtures、账户/权限矩阵、模拟状态和已知风险；实现 Agent 不自验收。

**依赖：** FE-201～210 完成；backend QA 提供稳定联调环境。

## 4. 共享验收条件

所有实现任务必须同时满足：

1. App/Admin 不采集或持久化 PAN、CVV、证件或 Provider token；Hosted boundary 不回退。
2. D1、金额、rail、审批、tenant/RBAC 都来自服务端裁决；UI 隐藏不是授权。
3. processing/unknown/error 不显示成功，不自动重复 POST。
4. P001 checkout/payment method/direct charge/history 的 array/offset/type 兼容回归通过；P002 只有 vendor Accept 才启用。
5. D-205-A 不出现用户收据文件、PDF、邮件或 DIAN 功能。
6. D-204 不出现默认阈值、风险字段或风险 UI。
7. 前端 QA 通过后才进入 e2e-agent；真实资金仍受 D-204 和生产门禁阻断。
8. FinancialEligibility 与 rail 分离，QR resource context 和 `/charging/start` 重算均由服务端完成。
9. Admin permission/HTTP/body/stable sort/errors/CSV lifecycle 与 `PAY-MP-002-v1` 完全一致；platform scope 无伪 tenant 假设。

## 5. 架构复审输入

architecture-agent 需确认：

- checkout 与 recovery 的 additive association；
- transactions 的 vendor `Accept` 双 projection 与 P001 原样兼容；
- FinancialEligibility 财务 authority、scoped rail 分层、QR context 和 start 重算；
- 三类双控资源的 create/decision 语义；
- Admin 固定 permission/HTTP/body/stable sort/error 和 CSV 生命周期；
- platform Outbox scope 不向前端引入伪 tenant；
- support/refund link、allowed actions 和 safe errors。

共享契约已由 architecture-agent 冻结为 v2；frontend-agent 可按 v2 准备 BE-205 相关 adapter，但仍需独立 frontend QA、E2E 和生产门禁，不得自行实现后端风险 authority。

## D-204-B v2 contract refresh handoff

- App/Admin 只消费 RiskSession/RiskStop/ProviderResolution safe projections、risk decision/status/errors 和 `allowed_actions`。
- tenant、scope、amount、policy version、attempts、timeout、stop result、Provider status 和 raw Provider payload 不得进入客户端请求。
- 本次仅同步契约引用；未实现 endpoint、业务逻辑、迁移、部署或生产配置。
