---
id: PAY-MP-002
change_id: CHG-20260812-002
status: architecture-approved
contract: frozen
contract_version: PAY-MP-002-v2
negotiation_media_type: application/vnd.eslatin.pay-mp-002.v2+json
compatible_contracts: P001-default, PAY-MP-002-v1
backend_review: cf-201-cf-205-closed
frontend_review: cf-206-closed
architecture_review: approved
freeze_owner: architecture-agent
implementation_authorization: be205-contract-frozen-only
frozen_at_utc: 2026-08-15
---

# PAY-MP-002 共享 API/状态契约

## 1. 契约状态

本文件保留 backend-agent/frontend-agent 已关闭的 CF-201～CF-206 作为 `PAY-MP-002-v1` 兼容基线，并新增经 architecture-agent 批准的 D-204-B `PAY-MP-002-v2` contract refresh。v2 仅 additive 增加 RiskSession/RiskStop/ProviderResolution 安全投影、risk decision/status/errors 和内部 risk event schema；v1 与 P001 默认 API 继续兼容。

冻结只表示 API/状态/错误/事件边界已确定，不表示业务代码已经实现、QA/E2E 已通过或生产可发布。当前 gate 为 `contract-frozen / implementation-ready-for-BE205`；生产仍 `no-go`。

本契约覆盖已批准的 D-201/D-202/D-203/D-204-B/D-205-A/D-206-B/D-207-B/D-208-B/D-209-B/D-210-B。D-204 的风险 authority、账本事实和内部 worker 仍不在本次实现范围；本文件只冻结其对外安全投影、自动命令交接和内部事件 schema。

## 2. 全局约束

- Base path：`/api/v1`；JSON 使用 UTF-8。
- `PAY-MP-002-v1` 投影中的金额和 kWh 使用 decimal string；禁止二进制浮点参与计算或 round-trip。P001 `/app/transactions` 的历史 number 字段按 §5.7/§9 原样保持。
- 时间均为 ISO-8601 UTC；展示层自行 locale 化。
- opaque ID 不携带 tenant/provider 语义。
- tenant/platform scope、RBAC、资源 ownership、双控和 `allowed_actions` 均由服务端裁决；客户端 header/query/menu 不是授权依据。
- 所有写操作必须携带 `Idempotency-Key`；需要并发保护的写操作同时携带 body `expected_version`。
- 公共响应不返回 raw Provider payload、secret、access token、PAN、CVV、证件号或完整 Hosted URL token 日志。
- 未知 enum 必须允许客户端安全显示 `unknown`；服务端不得把 Provider-specific 状态直接加入公共 enum。
- v2 D-204 risk decision 必须由服务端基于 pinned policy version、当前 authority 和服务端解析的 user/site/platform scope 生成；客户端不得提交或覆盖 tenant、scope、amount、policy version、meter result、stop result 或 Provider result。
- v2 D-204 的 site/platform aggregate window 固定为同一 UTC timestamp rolling 24-hour window；无 calendar-midnight reset；active reservations 与 unresolved exposure 计入；released/settled exposure 排除。

### 2.1 Cursor page

```json
{
  "items": [],
  "page": {
    "next_cursor": "opaque-or-null",
    "has_more": false
  }
}
```

- `limit` 范围 `1..100`，默认由 endpoint 定义。
- 排序必须稳定并在 endpoint 下明确；cursor 与 filter/scope 绑定。
- cursor 无效或过期返回 `409 CURSOR_INVALID`，客户端不得静默回第一页。
- `total` 只有在服务端可提供准确快照时才可作为 optional 字段；前端不得依赖 total 完成业务流程。

### 2.2 Canonical error

```json
{
  "error": {
    "code": "RESOURCE_VERSION_CONFLICT",
    "message": "safe localized-or-localizable message",
    "reference": "opaque-support-reference",
    "retryable": false,
    "retry_after_seconds": null,
    "current_version": 7
  }
}
```

`message` 不包含 Provider 原始信息；客户端以 `code` 映射 es-CO 文案，未知 code 使用安全兜底并显示 `reference`。

### 2.3 通用投影

```json
{
  "allowed_actions": ["view", "refresh"],
  "version": 7,
  "created_at": "2026-08-13T12:00:00Z",
  "updated_at": "2026-08-13T12:05:00Z"
}
```

`allowed_actions` 只改善 UX；服务端仍对每次请求重新授权。

## 3. Canonical 状态

### 3.1 RecoveryAttempt

`created | processing | action_required | approved | allocated | declined | failed | cancelled | expired | manual_review | unknown`

`approved` 仅表示 Payment/Provider 阶段已确认，不表示 Invoice 已分配或 D1 已解除。

### 3.2 PaymentAllocation

`pending | confirmed | reversed | failed | unknown`

### 3.3 FinancialEligibility

`eligible | blocked | evaluating | unknown`

阻断 reason code：

`open_invoice | recovery_processing | recovery_unknown | refund_or_chargeback | funds_unknown | reconciliation_mismatch`

这些只表达财务事实。Runtime rail 是独立运营控制，不能写入 FinancialEligibility reason code；两者只在 charging preflight 组合。不公开 D-204 阈值或风险参数。

### 3.4 RefundCase

`submitted | under_review | approved | provider_processing | partially_refunded | refunded | rejected | manual_review | unknown`

### 3.5 ChargebackCase

`received | under_review | hold | representment | won | lost | reversed | unknown`

### 3.6 Reconciliation

- Run：`created | running | completed | completed_with_exceptions | failed | unknown`
- Item/Exception：`matched | pending | mismatch | manual_review | temporarily_accepted | closed | unknown`

### 3.7 Approval

`not_required | pending | approved | rejected | expired | unknown`

### 3.8 RuntimeRailControl

- axis：`paid_admission | payment_creation`
- status：`open | closed | unknown`

### 3.9 SupportCase

`open | acknowledged | in_progress | waiting_user | resolved | closed | unknown`

### 3.10 Domain → public 固定映射（CF-201）

服务端先把 Provider 状态正规化为 domain state，再执行下表映射；不得把 Provider-specific 字符串直接返回。未列出的 domain state 一律投影为对应资源的 `unknown`，附 `reason_code=unrecognized_domain_state`，写安全日志/审计并保持 fail closed。

| 资源 | Domain state | Public state |
|---|---|---|
| RecoveryAttempt | `created` | `created` |
| RecoveryAttempt | `processing` | `processing` |
| RecoveryAttempt | `action_required` | `action_required` |
| RecoveryAttempt | `provider_approved` | `approved` |
| RecoveryAttempt | `allocated` | `allocated` |
| RecoveryAttempt | `declined` | `declined` |
| RecoveryAttempt | `failed` | `failed` |
| RecoveryAttempt | `cancelled` | `cancelled` |
| RecoveryAttempt | `expired` | `expired` |
| RecoveryAttempt | `duplicate_approved` | `manual_review` |
| RecoveryAttempt | `unknown` | `unknown` |
| PaymentAllocation | `pending` | `pending` |
| PaymentAllocation | `committed` | `confirmed` |
| PaymentAllocation | `reversed` | `reversed` |
| PaymentAllocation | `failed` | `failed` |
| PaymentAllocation | `needs_review` | `unknown` |
| FinancialEligibility | `eligible` | `eligible` |
| FinancialEligibility | `blocked` | `blocked` |
| FinancialEligibility | `recheck_required` | `evaluating` |
| FinancialEligibility | `unknown` | `unknown` |

RefundCase、ChargebackCase、Reconciliation、Approval、RuntimeRailControl 和 SupportCase 的 domain/public enum 同名映射；缺失或未来新增状态按上述 `unknown` 规则处理。

迟到重复批准的公共投影固定如下：

- 已提交的赢家 attempt 继续为 `allocated`，其 allocation 继续为 `confirmed`，Invoice 只结清一次；
- 迟到获批的非赢家 attempt 为 `manual_review`，`reason_code=duplicate_approval`，`allocation=null`，不得伪造第二条 Allocation；
- 同一 Provider event 重放返回同一 attempt/case，不重复创建退款、支持案件、对账差异或 Outbox 事件；
- duplicate funds 建立 reconciliation mismatch/人工退款事实，FinancialEligibility 重新计算且在资金事实收敛前保持 `blocked` 或 `evaluating`，客户端不得从 `approved` 推断已结清。

## 4. 共用安全投影

### 4.1 ActorRef

```json
{"id":"opaque-actor-id","display_name":"safe-name","role_label":"finance"}
```

### 4.2 ApprovalProjection

```json
{
  "status": "pending",
  "initiator": {"id":"opaque","display_name":"safe-name","role_label":"operations"},
  "approver": null,
  "requested_at": "2026-08-13T12:00:00Z",
  "decided_at": null,
  "expires_at": "2026-08-14T12:00:00Z",
  "version": 1
}
```

### 4.3 SafeTimelineEvent

```json
{
  "event_id": "opaque",
  "type": "recovery.processing",
  "status": "processing",
  "occurred_at": "2026-08-13T12:00:00Z",
  "actor": null,
  "reason_code": null,
  "reference": "safe-reference"
}
```

事件只用于展示，不可作为客户端状态机 authority。

## 5. App API

### 5.1 欠费列表

`GET /api/v1/app/unpaid-charges?cursor=<opaque>&limit=<1..100>`

稳定排序：`updated_at DESC, invoice_id DESC`。

```json
{
  "items": [
    {
      "invoice_id": "uuid",
      "invoice_reference": "safe-reference",
      "session_id": "uuid",
      "site": {"id":"uuid","name":"safe-name"},
      "charge_point_reference": "safe-reference",
      "connector_id": 1,
      "started_at": "2026-08-13T12:00:00Z",
      "ended_at": "2026-08-13T12:30:00Z",
      "energy_kwh": "6.800",
      "original_amount": "18760.00",
      "allocated_amount": "0.00",
      "refunded_amount": "0.00",
      "outstanding_amount": "18760.00",
      "currency": "COP",
      "blocking_reason": "open_invoice",
      "recovery_status": null,
      "active_recovery_attempt_id": null,
      "d1_status": "blocked",
      "allowed_actions": ["view", "start_recovery", "contact_support"],
      "updated_at": "2026-08-13T12:31:00Z"
    }
  ],
  "page": {"next_cursor": null, "has_more": false}
}
```

空列表只有在成功响应 `items=[]` 时成立。`recovery_status`/active ID 可以为空，不得为从未发生的账单伪造 `created`。

### 5.2 欠费详情

`GET /api/v1/app/unpaid-charges/{invoice_id}`

返回：

- 上述账单摘要；
- 不可变 ChargingSession/PricingSnapshot 安全摘要；
- `available_methods[]`：`wallet | new_card | saved_card`、`enabled`、safe `disabled_reason_code`、可选 saved method ref；
- `active_recovery_attempt` 简要投影；
- Payment/Allocation/Refund/Chargeback `timeline[]`；
- 当前 `financial_eligibility`；
- `support_case_refs[]`、`allowed_actions`、version/timestamps。

amount、currency、tenant、merchant、Invoice target 和最终状态全部只读。

### 5.3 创建补缴尝试

`POST /api/v1/app/unpaid-charges/{invoice_id}/recovery-attempts`

Headers：`Idempotency-Key: <opaque>`

```json
{
  "method": "wallet",
  "saved_payment_method_id": null
}
```

请求不接受 amount、currency、tenant、merchant、provider、Invoice 列表或客户端状态。`saved_card` 必须属于当前用户并继续通过 Hosted CVV。

响应：`201` 首次创建，幂等重放返回同一 canonical result。

```json
{
  "attempt_id": "uuid",
  "invoice_id": "uuid",
  "target_amount": "18760.00",
  "currency": "COP",
  "method": "saved_card",
  "status": "action_required",
  "payment_order_id": "uuid-or-null",
  "allocation": {
    "status": "pending",
    "amount": "0.00",
    "confirmed_at": null
  },
  "financial_eligibility": {
    "status": "blocked",
    "reason_codes": ["recovery_processing"],
    "evaluated_at": "2026-08-13T12:35:00Z",
    "version": 3
  },
  "next_action": {
    "type": "open_checkout",
    "checkout_session_id": "opaque",
    "url": "same-origin-or-allowlisted-url",
    "expires_at": "2026-08-13T12:50:00Z",
    "poll_after_seconds": null
  },
  "support_reference": "safe-reference",
  "allowed_actions": ["refresh", "open_checkout", "contact_support"],
  "version": 1,
  "created_at": "2026-08-13T12:35:00Z",
  "updated_at": "2026-08-13T12:35:00Z"
}
```

`next_action.type`：`none | poll | open_checkout | open_provider_url | contact_support`。URL 只能来自既有 same-origin/Provider allowlist。

### 5.4 查询补缴尝试

`GET /api/v1/app/recovery-attempts/{attempt_id}`

返回 5.3 的 canonical attempt，并可增加 safe timeline。`approved` 不能替代 `allocation.status=confirmed` 和 FinancialEligibility recheck。

### 5.5 Checkout additive 关联

既有 P001 Checkout Session 路径和字段保持。对于 `purpose=unpaid_charge`，GET response additive 增加：

```json
{
  "purpose": "unpaid_charge",
  "recovery_attempt_id": "uuid",
  "invoice_id": "uuid"
}
```

字段只在对应 purpose 出现。客户端可据此在 Deep Link、重启或换设备后恢复 RecoveryAttempt；不得从 checkout status 推导 allocation/D1。

### 5.6 FinancialEligibility

`GET /api/v1/app/financial-eligibility?operation=paid_charging_admission`

```json
{
  "operation": "paid_charging_admission",
  "status": "blocked",
  "reason_codes": ["open_invoice"],
  "blocking_resources": [
    {"type":"invoice","id":"uuid","reference":"safe-reference"}
  ],
  "allowed_actions": ["view_unpaid_charges", "contact_support"],
  "evaluated_at": "2026-08-13T12:36:00Z",
  "version": 9
}
```

该 endpoint 只返回平台级财务资格，不读取也不返回 runtime rail，`reason_codes` 中禁止 `rail_closed`。不返回 D-204 风险参数。App 可在 recovery 收敛后刷新该事实，但不能据此单独判断某个充电资源可启动。

充电资源预检使用唯一入口：

`POST /api/v1/app/charging/preflight`

```json
{"qr_token":"opaque-qr-token","settlement_method":"wallet"}
```

服务端必须从 `qr_token` 解析 `operator_tenant_id/charge_point_id/site_id/connector_id`，再从定价和 merchant context 推导是否收费及 Provider；请求不得接受客户端传入 tenant/site/provider/scope。成功返回 `200`：

```json
{
  "resource": {
    "charge_point_id": "uuid",
    "site_id": "uuid",
    "connector_id": 1,
    "pricing_mode": "paid"
  },
  "financial_eligibility": {
    "status": "eligible",
    "reason_codes": [],
    "evaluated_at": "2026-08-13T12:36:00Z",
    "version": 9
  },
  "rail_eligibility": {
    "axis": "paid_admission",
    "status": "open",
    "matched_scope_refs": ["platform:eslatin","site:uuid"],
    "evaluated_at": "2026-08-13T12:36:00Z",
    "version": 4
  },
  "decision": "allowed",
  "allowed_actions": ["start_charging"]
}
```

`rail_eligibility.status` 为 `open | closed | unknown | not_applicable`；`not_applicable` 只用于服务端确认的免费充电。总决定仅当 FinancialEligibility=`eligible` 且 rail=`open|not_applicable` 时为 `allowed`，其余均为 `blocked`。预检结果是短时 UX 投影，不是能力 token。

`POST /api/v1/app/charging/start` 必须在同一请求中重新执行以下组合 preflight，不能信任之前的 preflight response：解析并校验 QR/connector/asset/commissioning/pricing → 计算平台级 FinancialEligibility → 对收费场景按服务端解析出的 platform/provider/tenant/site scopes 读取 `paid_admission` rail → 校验 settlement/payment intent → 才允许 claim intent 和发送 RemoteStart。任一适用 scope 为 `closed` 或 `unknown` 均 fail closed；FinancialEligibility 不得吸收 rail 状态。

### 5.7 现有历史路径的显式版本协商（CF-202）

只使用 HTTP `Accept` media type 协商，不提供 query/body/header 的第二种版本机制：

- 未提供 `Accept`，或 `Accept: application/json` / `*/*`：严格执行 P001；
- `Accept: application/vnd.eslatin.pay-mp-002.v1+json`：执行 `PAY-MP-002-v1`；响应 `Content-Type` 使用同一 media type，并返回 `Vary: Accept`；
- 其他 EsLatin vendor media type：`406 CONTRACT_VERSION_UNSUPPORTED`；
- `cursor`、`offset` 或字段存在与否都不能隐式切换契约版本。

P001 列表保持当前实际行为，不做 additive shape/type 修改：

`GET /api/v1/app/transactions?status=&limit=<1..200>&offset=<0..>`

- `200 application/json`，body 是 bare JSON array；
- 排序保持当前 `start_time DESC`；
- 字段保持 `id, transaction_id, charge_point_id, ocpp_identity, evse_id, start_time, end_time, status, energy_kwh, duration_minutes, site_name, site_address`；
- `energy_kwh`、`duration_minutes` 保持 JSON number/null，其他既有字段类型保持不变；
- 无 vendor `Accept` 时即使出现 `cursor` 也不切换到 P002，仍按 P001 offset 语义响应。

P002 列表只接受：

`GET /api/v1/app/transactions?cursor=<opaque>&limit=<1..100>`

- `200 application/vnd.eslatin.pay-mp-002.v1+json`，body 为 §2.1 cursor envelope；
- 稳定排序固定为 `start_time DESC, session_id DESC`；
- `energy_kwh`、所有金额为 decimal string/null；
- vendor `Accept` 请求携带 `offset` 返回 `400 PAGINATION_MODE_INVALID`，不能同时支持两套分页。

`GET /api/v1/app/transactions/{session_id}` 同样按 `Accept` 协商：P001 继续返回当前详情字段和类型；P002 返回已存在字段的 decimal-string 投影，并 additive 返回：

- ChargingSession/Invoice/PricingSnapshot 基础摘要；
- Payment/Recovery/Allocation/Refund/Chargeback 安全状态与 timeline；
- `data_quality: current | legacy | unknown`；
- `support_case_refs[]`、`allowed_actions`。

旧记录缺事实时返回 `legacy/unknown`，不得猜测 paid。D-205-A 不返回 PDF/download/email/DIAN receipt URL/channel。P001/P002 共享同一底层 authority，但 projection adapter 独立；服务端测试必须对两个 media type 做 golden response。

### 5.8 支持案件

- `GET /api/v1/app/support-cases?status=&cursor=&limit=`
- `POST /api/v1/app/support-cases`
- `GET /api/v1/app/support-cases/{case_id}`

创建请求：

```json
{
  "category": "payment_recovery | refund_request | chargeback_question | charging_issue | other",
  "context": {"resource_type":"invoice","resource_id":"uuid"},
  "description": "user text"
}
```

每次只允许一个由服务端校验 ownership 的 context resource。响应/详情含 `case_id/reference/status/sla_target_at/timeline/linked_refund_case/allowed_actions/version/timestamps`。不允许用自由 Provider/tenant reference 绕过 ownership。

用户退款诉求创建 SupportCase；实际 RefundCase 由授权运营流程创建并关联，App 只读其安全状态。

## 6. Admin API

所有 JSON endpoint 使用 `PAY-MP-002-v1`，所有列表使用 §2.1 cursor envelope。权限名称固定为：

`payment.read`, `refund.request`, `refund.approve`, `chargeback.read`,
`reconciliation.read`, `reconciliation.resolve`, `reconciliation.exception.request`,
`reconciliation.exception.approve`, `support.manage`, `rail.read`, `rail.close`,
`rail.reopen.request`, `rail.reopen.approve`, `audit.read`。

服务端按该精确 permission string 和当前 membership/resource scope 授权；superadmin 的 `*` 仅表示满足这些 permission，不是新的 endpoint 权限名。前端只消费 `/admin/auth/me/permissions` 和服务端 `allowed_actions`，不得用 `is_super_admin` 推断操作权。跨租户资源按 `404 RESOURCE_NOT_FOUND` 隐藏存在性；已认证但缺 permission 固定为 `403 PERMISSION_DENIED`。

`PAY-MP-002-v1` projection 字段固定如下；未列字段不得临时加入响应，任何增删/改型都必须更新契约版本并重新前后端同步：

| Projection | 精确字段 |
|---|---|
| `RefundCaseProjection` | `case_id,target{resource_type,resource_id},requested_amount,approved_amount,confirmed_refunded_amount,currency,status,approval,provider_reference,timeline,audit_references,allowed_actions,version,created_at,updated_at` |
| `ChargebackCaseProjection` | `case_id,payment_reference,invoice_reference,amount,currency,status,deadline_at,funds_state,timeline,allowed_actions,version,created_at,updated_at` |
| `ReconciliationRunProjection` | `run_id,business_date,run_type,status,cutoff_at,closed_at,source_watermarks,summary,allowed_actions,version,created_at,updated_at` |
| `ReconciliationItemProjection` | `item_id,run_id,eslatin_reference,provider_reference,funds_reference,amount,currency,match_status,reason_codes,allowed_actions,version,created_at,updated_at` |
| `ReconciliationExceptionProjection` | `exception_id,item_id,status,category,difference_amount,currency,severity,owner,due_at,temporary_acceptance_until,allowed_actions,version,created_at,updated_at` |
| `ResolutionIntentProjection` | `intent_id,exception_id,resolution_code,reason,status,initiator,allowed_actions,version,created_at,updated_at` |
| `TemporaryAcceptanceRequestProjection` | `request_id,exception_id,status,reason,initiator,approver,expires_at,decided_at,allowed_actions,version,created_at,updated_at` |
| `ReconciliationExportProjection` | `export_id,status,download_path,expires_at,audit_reference,version,created_at,updated_at` |
| `RuntimeRailControlProjection` | `control_id,axis,scope{type,ref},status,reason,incident_reference,effective_at,closed_by,reopened_by,health_check_reference,allowed_actions,version,created_at,updated_at` |
| `RailReopenRequestProjection` | `request_id,control_id,status,reason,initiator,approver,health_check_reference,control_status,expires_at,decided_at,allowed_actions,version,created_at,updated_at` |
| `SupportCaseProjection` | `case_id,reference,status,category,linked_resources,sla_target_at,assignee,timeline,allowed_actions,version,created_at,updated_at` |
| `SupportCaseEventProjection` | `event_id,case_id,event_type,note_visibility,status,actor,occurred_at,case_version` |
| `AuditEventProjection` | `event_id,actor,resource{type,id},action,result,scope{type,ref},reason_code,safe_metadata,occurred_at` |

所有 amount/kWh 字段是 decimal string/null，时间是 UTC string/null，ID/reference 是 opaque string，`version/case_version` 是正整数，集合字段是 JSON array/object。`safe_metadata` 禁止 secrets、证件、PAN/CVV 和 raw Provider payload。

### 6.0 Endpoint/HTTP/permission/稳定排序矩阵（CF-205）

| Endpoint | Permission | 成功响应 | 稳定排序/说明 |
|---|---|---|---|
| `GET /admin/refund-cases` | `payment.read` | `200 CursorPage<RefundCaseProjection>` | `updated_at DESC, case_id DESC` |
| `POST /admin/refund-cases` | `refund.request` | `201 RefundCaseProjection` | `Idempotency-Key` 必填 |
| `GET /admin/refund-cases/{case_id}` | `payment.read` | `200 RefundCaseProjection` | resource scope |
| `POST /admin/refund-cases/{case_id}/decisions` | `refund.approve` | `200 RefundCaseProjection` | `Idempotency-Key` + `expected_version`；不同 actor |
| `GET /admin/chargeback-cases` | `chargeback.read` | `200 CursorPage<ChargebackCaseProjection>` | `deadline_at ASC NULLS LAST, case_id ASC` |
| `GET /admin/chargeback-cases/{case_id}` | `chargeback.read` | `200 ChargebackCaseProjection` | resource scope |
| `GET /admin/reconciliation/runs` | `reconciliation.read` | `200 CursorPage<ReconciliationRunProjection>` | `business_date DESC, run_id DESC` |
| `GET /admin/reconciliation/runs/{run_id}` | `reconciliation.read` | `200 ReconciliationRunProjection` | platform/authorized tenant scope |
| `GET /admin/reconciliation/runs/{run_id}/items` | `reconciliation.read` | `200 CursorPage<ReconciliationItemProjection>` | `created_at ASC, item_id ASC` |
| `GET /admin/reconciliation/exceptions` | `reconciliation.read` | `200 CursorPage<ReconciliationExceptionProjection>` | `due_at ASC NULLS LAST, exception_id ASC` |
| `GET /admin/reconciliation/exceptions/{exception_id}` | `reconciliation.read` | `200 ReconciliationExceptionProjection` | resource scope |
| `POST /admin/reconciliation/exceptions/{exception_id}/resolution-intents` | `reconciliation.resolve` | `201 ResolutionIntentProjection` | `Idempotency-Key` + `expected_version` |
| `POST /admin/reconciliation/exceptions/{exception_id}/temporary-acceptance-requests` | `reconciliation.exception.request` | `201 TemporaryAcceptanceRequestProjection` | `Idempotency-Key` + `expected_version` |
| `POST /admin/reconciliation/temporary-acceptance-requests/{request_id}/decisions` | `reconciliation.exception.approve` | `200 TemporaryAcceptanceRequestProjection` | `Idempotency-Key` + `expected_version`；不同 platform actor |
| `POST /admin/reconciliation/exports` | `reconciliation.read` | `202 ReconciliationExportProjection` | 创建唯一异步 export resource |
| `GET /admin/reconciliation/exports/{export_id}` | `reconciliation.read` | `200 ReconciliationExportProjection` | resource scope |
| `GET /admin/reconciliation/exports/{export_id}/download` | `reconciliation.read` | `200 text/csv` | 仅 `ready` 可成功一次；成功后原子转 `downloaded` |
| `GET /admin/runtime-rails` | `rail.read` | `200 CursorPage<RuntimeRailControlProjection>` | `updated_at DESC, control_id DESC` |
| `POST /admin/runtime-rails/close-requests` | `rail.close` | `201 RuntimeRailControlProjection` | close 单人立即生效；`Idempotency-Key` + `expected_version` |
| `POST /admin/runtime-rails/{control_id}/reopen-requests` | `rail.reopen.request` | `201 RailReopenRequestProjection` | `Idempotency-Key` + `expected_version` |
| `POST /admin/runtime-rail-reopen-requests/{request_id}/decisions` | `rail.reopen.approve` | `200 RailReopenRequestProjection` | 不同 actor；projection 含最终 control status |
| `GET /admin/support-cases` | `support.manage` | `200 CursorPage<SupportCaseProjection>` | `sla_target_at ASC NULLS LAST, case_id ASC` |
| `GET /admin/support-cases/{case_id}` | `support.manage` | `200 SupportCaseProjection` | resource scope |
| `POST /admin/support-cases/{case_id}/events` | `support.manage` | `201 SupportCaseEventProjection` | `Idempotency-Key` + `expected_version` |
| `GET /admin/audit-events` | `audit.read` | `200 CursorPage<AuditEventProjection>` | `occurred_at DESC, event_id DESC` |

上表 Base path 均为 `/api/v1`。所有 GET detail 不可见返回 `404`；所有 version 冲突返回 `409 RESOURCE_VERSION_CONFLICT`；所有 idempotency fingerprint 冲突返回 `409 IDEMPOTENCY_CONFLICT`；请求 schema 错误固定 `422 REQUEST_INVALID`。不得为同一 endpoint 保留第二种成功 body 或 HTTP 状态。

### 6.1 RefundCase

- `GET /api/v1/admin/refund-cases?status=&tenant_scope=&cursor=&limit=`
- `POST /api/v1/admin/refund-cases`
- `GET /api/v1/admin/refund-cases/{case_id}`
- `POST /api/v1/admin/refund-cases/{case_id}/decisions`

创建：

```json
{
  "target": {"resource_type":"payment_allocation","resource_id":"uuid"},
  "requested_amount": "10000.00",
  "currency": "COP",
  "reason_code": "customer_request",
  "reason": "safe operator note"
}
```

服务端重新计算可退金额/币种/merchant/scope。创建 request 不直接宣称 Provider refund 完成。

Decision：

```json
{
  "decision": "approve",
  "expected_version": 3,
  "reason": "reviewed evidence"
}
```

`decision=approve|reject`。服务端要求不同授权 actor、相同 scope、未过期和版本匹配。详情返回金额分解、canonical status、approval projection、safe Provider reference、timeline、allowed actions 和 audit refs。

### 6.2 ChargebackCase

- `GET /api/v1/admin/chargeback-cases?status=&deadline_from=&deadline_to=&cursor=&limit=`
- `GET /api/v1/admin/chargeback-cases/{case_id}`

返回 canonical dispute/hold/funds state、amount/currency/deadline、关联 Invoice/Payment/Refund 安全引用、timeline、allowed actions。无 raw Provider evidence/payload。

### 6.3 Reconciliation

- `GET /api/v1/admin/reconciliation/runs?business_date=&status=&cursor=&limit=`
- `GET /api/v1/admin/reconciliation/runs/{run_id}`
- `GET /api/v1/admin/reconciliation/runs/{run_id}/items?status=&cursor=&limit=`
- `GET /api/v1/admin/reconciliation/exceptions?status=&cursor=&limit=`
- `GET /api/v1/admin/reconciliation/exceptions/{exception_id}`
- `POST /api/v1/admin/reconciliation/exceptions/{exception_id}/resolution-intents`
- `POST /api/v1/admin/reconciliation/exceptions/{exception_id}/temporary-acceptance-requests`
- `POST /api/v1/admin/reconciliation/temporary-acceptance-requests/{request_id}/decisions`

Resolution intent request 固定为 `{"resolution_code":"...","reason":"...","expected_version":3}`，不能直接把事实改为 matched。

Temporary acceptance request 固定为 `{"reason":"...","expected_version":3}`；decision request 固定为 `{"decision":"approve|reject","reason":"...","expected_version":1}`。临时例外仅覆盖产品批准的 timing/fee/funds-release timing 范围；finance 发起，另一个 platform actor 决定，最长 24 小时由服务端生成 `expires_at`。不合格差异返回 `EXCEPTION_NOT_ELIGIBLE`。

#### 对账 CSV

`POST /api/v1/admin/reconciliation/exports`

```json
{
  "run_id": "uuid",
  "filters": {"status":["mismatch","manual_review"]},
  "format": "csv"
}
```

`POST` 固定返回 `202`：

```json
{
  "export_id": "uuid",
  "status": "queued",
  "download_path": null,
  "expires_at": "2026-08-13T13:00:00Z",
  "audit_reference": "safe-reference",
  "version": 1,
  "created_at": "2026-08-13T12:00:00Z",
  "updated_at": "2026-08-13T12:00:00Z"
}
```

唯一生命周期为 `queued -> generating -> ready -> downloaded`，失败为 `failed`，到期为 `expired`。只有 `ready` 投影提供固定同源 `download_path=/api/v1/admin/reconciliation/exports/{export_id}/download`；不签发第二种 URL/reference。下载 endpoint 在权限/scope 校验和审计写入成功后以单事务 claim，一次返回 `200 text/csv` 并转为 `downloaded`。非终态下载返回 `409 EXPORT_NOT_READY`，`failed` 返回 `409 EXPORT_FAILED`，已下载返回 `410 EXPORT_CONSUMED`，过期返回 `410 EXPORT_EXPIRED`。服务端执行脱敏、最大行数和文件 expiry；该 CSV 是运营对账导出，不是 D-205-A 用户收据。

### 6.4 Runtime rails

- `GET /api/v1/admin/runtime-rails?axis=&scope_type=&scope_id=&cursor=&limit=`
- `POST /api/v1/admin/runtime-rails/close-requests`
- `POST /api/v1/admin/runtime-rails/{control_id}/reopen-requests`
- `POST /api/v1/admin/runtime-rail-reopen-requests/{request_id}/decisions`

Close request body 固定为 `{"axis":"paid_admission|payment_creation","scope":{"type":"platform|provider|tenant|site","ref":"server-resolvable-reference"},"reason":"...","incident_reference":"...","expected_version":0}`；经权限校验后可以单人立即形成 closed control。

Reopen request 固定为 `{"reason":"...","health_check_reference":"...","expected_version":3}`；decision request 固定为 `{"decision":"approve|reject","reason":"...","expected_version":1}`。Reopen 必须由不同授权 actor approve/reject；服务端健康检查 failed/unknown 不得变为 open。

关闭 `paid_admission` 或 `payment_creation` 不停止 Webhook、active query、refund、chargeback、reconciliation、history、support、StopTransaction，也不自动 RemoteStop 活跃会话。

### 6.5 Support

- `GET /api/v1/admin/support-cases?status=&category=&tenant_scope=&cursor=&limit=`
- `GET /api/v1/admin/support-cases/{case_id}`
- `POST /api/v1/admin/support-cases/{case_id}/events`

事件请求固定为 `{"event_type":"acknowledge|assign|request_user_input|resolve|close|add_note","note":"...","note_visibility":"internal|user","expected_version":3}`；事件只能推进 SupportCase 允许的协作状态，不直接更改 Payment/Refund/D1/Reconciliation 终态。详情含关联资源安全投影、SLA、timeline 和 allowed actions。

### 6.6 Audit

`GET /api/v1/admin/audit-events?actor=&resource_type=&resource_id=&action=&result=&from=&to=&cursor=&limit=`

返回 scope 内脱敏事件；不包含 raw Provider payload、token、PAN/CVV、证件或 secret。

## 7. Canonical 错误码

| Code | HTTP | retryable | 客户端语义 |
|---|---:|---:|---|
| `REQUEST_INVALID` | 422 | false | 修正请求字段；不重放原请求。 |
| `CONTRACT_VERSION_UNSUPPORTED` | 406 | false | 客户端改用已支持的 media type。 |
| `PAGINATION_MODE_INVALID` | 400 | false | P002 cursor 请求不得携带 offset。 |
| `CURSOR_INVALID` | 409 | false | 提示刷新列表；不静默换页。 |
| `RESOURCE_NOT_FOUND` | 404 | false | 不泄露跨租户资源存在性。 |
| `PERMISSION_DENIED` | 403 | false | 刷新权限/返回安全页面。 |
| `RESOURCE_VERSION_CONFLICT` | 409 | false | GET 最新版本再由用户确认。 |
| `IDEMPOTENCY_CONFLICT` | 409 | false | key 与 fingerprint 冲突，不自动重试。 |
| `RECOVERY_TARGET_INVALID` | 404 | false | 目标不可补缴或不可见；不泄露 ownership。 |
| `RECOVERY_NOT_ALLOWED` | 409 | false | 可见账单当前状态不允许新 attempt。 |
| `RECOVERY_CONFLICT` | 409 | false | 查询现有 active/winner attempt。 |
| `RECOVERY_UNKNOWN` | 503 | true | 保持 D1 blocked，只查询/支持。 |
| `FINANCIAL_ELIGIBILITY_BLOCKED` | 402 | false | 显示 safe reason/actions。 |
| `FINANCIAL_RECHECK_REQUIRED` | 409 | true | 等待并重新 GET。 |
| `RAIL_CLOSED` | 503 | false | 不创建支付；显示替代动作/支持。 |
| `RAIL_STATE_UNKNOWN` | 503 | true | fail closed；等待运营/健康检查收敛。 |
| `APPROVAL_REQUIRED` | 409 | false | 等待另一授权 actor。 |
| `APPROVAL_CONFLICT` | 409 | false | actor/version/scope 不满足；刷新。 |
| `APPROVAL_EXPIRED` | 409 | false | 创建新 request，不复用旧 decision。 |
| `RECONCILIATION_MISMATCH` | 409 | false | 不能直接标记成功。 |
| `EXCEPTION_NOT_ELIGIBLE` | 422 | false | 不允许临时例外。 |
| `SUPPORT_CONTEXT_INVALID` | 404 | false | 关联资源不可见/不可关联。 |
| `EXPORT_NOT_READY` | 409 | true | 继续轮询 export resource。 |
| `EXPORT_FAILED` | 409 | false | 查看安全 reference 后重新创建。 |
| `EXPORT_CONSUMED` | 410 | false | 一次性文件已成功下载。 |
| `EXPORT_EXPIRED` | 410 | false | 文件已过期，重新创建 export。 |
| `PROVIDER_UNAVAILABLE` | 503 | true | 查询/等待；不自动创建第二笔。 |

服务端可在 retryable 响应返回 `retry_after_seconds`。客户端自动重试仅限安全 GET，并必须有退避/上限；所有 POST unknown 先 GET canonical resource。

## 8. Internal Outbox event contract（CF-204）

以下不是 App/Admin HTTP，不允许前端订阅 raw event：

```text
recovery.attempt.created / state_changed
payment.allocation.committed / reversed
financial.eligibility.recheck_requested / evaluated
refund.case.submitted / decision_recorded / state_changed
chargeback.fact.received / state_changed
reconciliation.run.state_changed / exception_opened / exception_closed
rail.control.closed / reopen_requested / decision_recorded / reopened
support.case.created / state_changed / notification_requested
```

统一使用现有 `outbox_events` 表的 additive scope 方案，不建立第二张 platform outbox：

- 新增 `scope_type NOT NULL`，只允许 `tenant | platform`；
- 新增 `scope_ref NOT NULL`：tenant 为 `tenant:<uuid>`，平台固定为 `platform:eslatin`；
- 将当前 `tenant_id NOT NULL` 放宽为 nullable，但保留 FK；
- DB CHECK 固定为：tenant scope 必须 `tenant_id IS NOT NULL` 且 `scope_ref='tenant:' || tenant_id::text`；platform scope 必须 `tenant_id IS NULL` 且 `scope_ref='platform:eslatin'`；
- 唯一键替换为 `(scope_type, scope_ref, idempotency_key)`；现有行在 expand migration 中确定性回填 `scope_type=tenant` 和对应 `scope_ref`；
- 禁止用全零 UUID、系统租户或任一真实租户代替 platform scope；worker 必须同时消费两类 scope，并按 event version 防乱序。

`tenant_id/scope_type/scope_ref` 是 Outbox delivery ownership；业务 payload 中的 provider/tenant/site resource refs 仍按对应 aggregate 的真实事实记录，不能反向伪造 delivery tenant。事件至少含 `event_id/schema_version/aggregate_type/id/scope_type/scope_ref/entity_reference/status/version/occurred_at_utc/reason_code/idempotency_key` 和必要 Decimal amount/currency。禁止 raw Provider payload 和支付敏感信息。消费必须支持 unique、lease/retry/DLQ/replay。

## 9. P001 兼容策略

- 保留 P001 Checkout Session、Hosted Secure Fields、PaymentOrder status query、Webhook/active query 和支付返回路由。
- `purpose=unpaid_charge` 仅 additive 增加 recovery/invoice refs；不改变其他 purpose 的 response/terminal UX。
- 现有 `/api/v1/app/transactions` 不改变 P001 默认 shape/type；仅通过 §5.7 唯一 vendor `Accept` media type 暴露 P002 cursor/decimal-string projection，不创建并行 `/charging-history` authority。
- 旧 `/api/v1/app/wallet/unpaid-charges` 和旧 session 钱包补缴在兼容期可存在，但 P002 UI 不调用，不能作为 typed Recovery/Allocation/D1 authority。
- 旧 metadata/refund summary/SupportMessage/`AppUser.has_unpaid_charges` 仅作 legacy diagnostic；缺新事实返回 `legacy/unknown`，不得自动推断/升级。
- 新资源采用 additive schema/version 和 expand/validate/new-write/cutover；回滚只关闭新入口并保留已写事实，未知财务状态继续 fail closed。

## 10. CF-201～CF-206 closure

| Finding | 后端候选结论 | 状态 |
|---|---|---|
| CF-201 | §3.10 固定 domain→public 映射、unknown fallback 和迟到重复批准投影 | closed-and-frozen |
| CF-202 | §5.7 只使用 `Accept: application/vnd.eslatin.pay-mp-002.v1+json` 协商；P001 array/offset/旧类型不变 | closed-and-frozen |
| CF-203 | §5.6 将 FinancialEligibility 与 scoped rail 分离，并固定 QR 资源上下文和 `/charging/start` 组合 preflight | closed-and-frozen |
| CF-204 | §8 固定单表 additive `scope_type/scope_ref`、nullable tenant 和 DB CHECK；禁止伪造 tenant；前端不消费 Outbox 或假设 platform tenant | closed-and-frozen |
| CF-205 | §6/§7 固定 permission、每个 endpoint response/HTTP、稳定排序、错误码和唯一 CSV 生命周期 | closed-and-frozen |
| CF-206 | frontend 架构、技术设计和任务已引用同一 `PAY-MP-002-v1`，未改变后端唯一化语义 | closed-and-frozen |

本节记录的是 v1 closure；D-204-B v2 refresh 已在 §12 冻结。BE-205 runtime、风险 UI/runtime 和真实资金发布仍受后续实现/QA/发布门禁约束；任何后续契约语义变更都必须重新执行架构门禁。

## 11. 冻结约束

frontend-agent 已确认 CF-201～CF-205 的唯一化结果可以由 App/Admin adapter 按 `PAY-MP-002-v1` 无分叉消费，并已完成 CF-206 文档同步。没有待 Product Owner 选择的问题。

architecture-agent 已在限定复审中确认以下双方一致性，实施不得分叉：

1. Checkout additive recovery association 与后端 adapter/outbox 一致；
2. FinancialEligibility endpoint 是唯一 D1 read authority；
3. transactions additive projection 的 legacy/unknown 语义；
4. Refund/temporary exception/rail reopen 的两步 approval resource 与后端 state machine 一致；
5. CSV 导出的 scope/脱敏/审计/一次性下载边界；
6. SupportCase 与 RefundCase link、resource `allowed_actions` 均为服务端 projection；
7. permission 名、stable sort、状态映射、错误码和 CSV lifecycle 与本冻结契约完全一致。

backend/frontend 不得各自分叉 endpoint、状态、error 或 approval 语义。

## 12. D-204-B v2 contract refresh

### 12.1 Negotiation and compatibility

- P001 default request/response remains unchanged: no v2 vendor `Accept` continues to use the existing P001 shape, status, number/null legacy types, offset/limit and existing HTTP semantics.
- `Accept: application/vnd.eslatin.pay-mp-002.v1+json` continues to select the frozen v1 projection for the already-covered P002 resources. v1 does not expose D-204 resources or D-204 fields.
- `Accept: application/vnd.eslatin.pay-mp-002.v2+json` selects the v2 projection. `Content-Type` mirrors the selected vendor media type and responses include `Vary: Accept`.
- D-204 v2 resources require the v2 media type. Missing, unsupported or incompatible negotiation returns `406 CONTRACT_VERSION_UNSUPPORTED`; the server must not silently downgrade a D-204 request to P001 or v1.
- v2 is additive and keeps P001/v1 authority, identifiers, authentication, tenant ownership and existing non-D-204 routes. No parallel business authority is created in App or Admin.

### 12.2 D-204 policy and safe decision projection

The server pins one immutable `policy_version` to each risk session. The following approved policy facts are exposed only as safe display/projection data; clients never submit them:

```json
{
  "policy_version": "opaque-policy-version",
  "session_limits": {
    "amount_cop": "200000.00",
    "energy_kwh": "100.000",
    "duration_minutes": 180,
    "stop_rule": "first_reached"
  },
  "exposure_limits": {
    "user_open_cop": "250000.00",
    "site_window_cop": "1000000.00",
    "platform_window_cop": "5000000.00"
  },
  "meter_values": {
    "degraded_after_seconds": 120,
    "stop_after_seconds": 300
  },
  "offline_unknown_buffer": {
    "amount_cop": "15000.00",
    "duration_minutes": 5,
    "stop_rule": "first_reached"
  },
  "aggregate_window": {
    "kind": "rolling",
    "duration_hours": 24,
    "time_basis": "utc_timestamp",
    "calendar_midnight_reset": false,
    "included": ["active_reservations", "unresolved_exposure"],
    "excluded": ["released_exposure", "settled_exposure"]
  }
}
```

`risk_decision` is server-generated and has one of `allow | block | stop_required | stop_pending | unknown`. `risk_status` is one of `not_evaluated | reserved | active | degraded | stopping | stopped_pending_reconcile | released | unresolved | blocked | unknown`. `reason_codes` are canonical safe values such as `SESSION_AMOUNT_LIMIT`, `SESSION_ENERGY_LIMIT`, `SESSION_DURATION_LIMIT`, `USER_EXPOSURE_LIMIT`, `SITE_EXPOSURE_LIMIT`, `PLATFORM_EXPOSURE_LIMIT`, `METER_VALUES_DEGRADED`, `METER_VALUES_STALE`, `OFFLINE_BUFFER_LIMIT`, `RISK_STATE_UNKNOWN`, `RISK_STOP_PENDING` and `PROVIDER_UNKNOWN`.

Meter freshness is evaluated by the server using UTC timestamps: age `<120s` is `fresh`, age `>=120s` and `<300s` is `degraded`, and age `>=300s` is `stale` with a stop decision. Offline/unknown buffering stops when either `15000.00 COP` or `5 minutes` is first reached. A public projection may show `unknown`, but the server must fail closed and must not issue/allow a new paid charging admission when authoritative risk state cannot be established.

### 12.3 RiskSession projection

`GET /api/v1/app/risk-sessions/{session_id}` and the equivalent authorized Admin detail projection use v2 only. The App projection is limited to the current user’s session; Admin projection is server-filtered by authorized tenant/site/platform scope.

```json
{
  "risk_session_id": "opaque-id",
  "charging_session_id": "opaque-id",
  "status": "active",
  "decision": "allow",
  "reason_codes": [],
  "policy_version": "opaque-policy-version",
  "scope_summary": {
    "user": "included",
    "site": "included",
    "platform": "included",
    "window": "rolling_24h_utc"
  },
  "meter_freshness": "fresh",
  "reserved_cop": "12000.00",
  "consumed_cop": "4300.00",
  "unresolved_cop": "0.00",
  "next_action": "continue | refresh | stop_pending | contact_support",
  "latest_stop_id": null,
  "provider_resolution_id": null,
  "allowed_actions": ["view", "refresh"],
  "version": 4,
  "updated_at": "2026-08-15T12:00:00Z"
}
```

`reserved_cop`, `consumed_cop` and `unresolved_cop` are server projections, not client accounting inputs. Raw ledger entries, lock state, internal policy predicates, provider payloads and cross-tenant records are never returned.

### 12.4 RiskStop projection and SLA

`GET /api/v1/app/risk-stops/{stop_id}` and authorized Admin detail use v2 only. The projection is:

```json
{
  "risk_stop_id": "opaque-id",
  "risk_session_id": "opaque-id",
  "status": "queued | sending | accepted_pending_physical_stop | retry_scheduled | confirmed | physical_stop_failed | unresolved",
  "reason_code": "METER_VALUES_STALE",
  "attempts": 1,
  "max_automatic_attempts": 3,
  "first_attempt_due_at": "2026-08-15T12:00:10Z",
  "last_attempt_at": "2026-08-15T12:00:02Z",
  "stop_transaction_due_at": "2026-08-15T12:05:00Z",
  "physical_stop_confirmed": false,
  "next_action": "refresh | contact_support",
  "allowed_actions": ["view", "refresh"],
  "version": 2,
  "updated_at": "2026-08-15T12:00:02Z"
}
```

Risk control initiates the first RemoteStop within 10 seconds and automatically retries at most three times through Outbox/OCPP control. `accepted_pending_physical_stop` is not physical confirmation. A missing StopTransaction by the five-minute target becomes `physical_stop_failed`/`unresolved` and is eligible for the limited manual physical-stop path. App/Admin cannot submit attempts, timeout, stop result, or confirmation.

### 12.5 ProviderResolution projection and 24-hour convergence

`GET /api/v1/app/provider-resolutions/{resolution_id}` and authorized Admin detail use v2 only. Provider unknown is resolved by the server using the same operation key and query/webhook recheck; no second payment create is permitted.

```json
{
  "provider_resolution_id": "opaque-id",
  "risk_session_id": "opaque-id",
  "status": "not_required | pending | checking | resolved_approved | resolved_rejected | terminal_unresolved",
  "provider_reference": "opaque-reference-or-null",
  "unknown_since": "2026-08-15T12:00:00Z",
  "final_due_at": "2026-08-16T12:00:00Z",
  "duplicate_create_blocked": true,
  "next_action": "refresh | contact_support | none",
  "allowed_actions": ["view", "refresh"],
  "version": 5,
  "updated_at": "2026-08-15T12:10:00Z"
}
```

At or before 24 hours the server performs bounded query/webhook rechecks. At 24 hours without a resolved Provider fact, the public terminal projection is `terminal_unresolved`, D1 remains blocked/debt-frozen, and the item enters the permitted manual queue. `terminal_unresolved` does not mean approved, rejected or settled. Raw Provider payloads, SDK errors and duplicate-create details remain adapter-internal.

### 12.6 Request authority and concurrency

- App/Admin requests must not contain `tenant_id`, `scope_type`, `scope_ref`, `amount`, `policy_version`, `attempts`, `timeout`, `stop_result`, `physical_stop_confirmed`, `provider_status` or raw Provider fields. Presence of any such client-authoritative field returns `422 CLIENT_AUTHORITY_FORBIDDEN`; the server must not ignore it and continue.
- Scope and tenant are resolved from authenticated identity, resource ownership and server-side QR/connector/asset context. Amount, energy, duration, freshness, policy version, reserve/consume/release/unresolved state and stop result are server facts.
- All mutating requests, including the existing `/charging/start` intent and any future authorized operational intent, require `Idempotency-Key`; state-changing bodies require `expected_version`. A repeated key with the same fingerprint returns the original projection; the same key with a different fingerprint returns `409 IDEMPOTENCY_CONFLICT`.
- A stale or missing `expected_version` on a versioned write returns `409 RESOURCE_VERSION_CONFLICT` or `422 EXPECTED_VERSION_REQUIRED`; clients must refresh and must not merge local state.
- Risk state transitions are server/worker commands only. The public contract exposes `allowed_actions`; it does not expose a client command to reserve, consume, release, mark unresolved, issue RemoteStop, confirm StopTransaction or resolve Provider state.

### 12.7 v2 HTTP and fail-closed errors

| HTTP | Canonical codes | Contract meaning |
|---|---|---|
| `406` | `CONTRACT_VERSION_UNSUPPORTED` | v2 is required for a D-204 resource, or the requested media type is unsupported; no downgrade to P001/v1. |
| `409` | `RESOURCE_VERSION_CONFLICT`, `IDEMPOTENCY_CONFLICT`, `RISK_BUDGET_BLOCKED`, `RISK_STOP_PENDING` | Known current state conflicts with the requested operation; no state mutation is accepted. |
| `422` | `REQUEST_INVALID`, `CLIENT_AUTHORITY_FORBIDDEN`, `EXPECTED_VERSION_REQUIRED`, `IDEMPOTENCY_KEY_REQUIRED` | Request shape or client authority is invalid; retrying unchanged input is not useful. |
| `503` | `RISK_STATE_UNKNOWN`, `RISK_DEPENDENCY_UNAVAILABLE` | The server cannot establish authoritative risk state or required Outbox/OCPP/ledger dependency; fail closed, do not admit paid charging, and return a safe retry hint. |

An authoritative domain state of `unknown` may be returned in a `200` safe projection when the server has persisted that unknown fact (for example Provider unknown); it remains non-terminal for financial purposes, blocks duplicate create, and cannot be interpreted as success. A transient inability to read or write the authority returns `503` instead. Error bodies use the existing canonical error envelope and never include raw Provider payload.

### 12.8 Internal risk event schema

All internal events use the following versioned envelope; they are not public API responses:

```json
{
  "event_id": "opaque-event-id",
  "schema_version": "risk-event.v2",
  "event_type": "risk.reservation.created",
  "aggregate": {
    "type": "RiskSession",
    "id": "opaque-id",
    "version": 7
  },
  "risk_scope": {
    "type": "user | site | platform",
    "ref": "server-derived-opaque-ref",
    "tenant_id": "server-derived-or-null"
  },
  "idempotency_key": "server-operation-key",
  "correlation_id": "opaque-id",
  "causation_id": "opaque-id-or-null",
  "occurred_at_utc": "2026-08-15T12:00:00Z",
  "status": "reserved",
  "reason_code": null,
  "policy_version": "opaque-policy-version",
  "amount_cop": "12000.00",
  "energy_kwh": "1.250",
  "data_quality": "authoritative | degraded | unknown"
}
```

Canonical event types are `risk.reservation.created`, `risk.consumed`, `risk.release_requested`, `risk.unresolved`, `risk.stop_requested`, `risk.stop_confirmed`, `risk.provider_recheck_requested`, `risk.provider_resolution.updated` and `risk.finalized`. Events are emitted through the existing Outbox handoff with scope-aware uniqueness, expected aggregate version, retry/DLQ/replay support and no raw Provider payload. `risk.finalized` is emitted only after the server has the final Invoice/payment/reconciliation facts required to release exposure; otherwise the state remains unresolved.

### 12.9 v2 closure and implementation gate

| Item | Status |
|---|---|
| D-204-B product parameters and window A | approved |
| RiskSession/RiskStop/ProviderResolution safe projections | frozen |
| Risk decision/status/errors and 406/409/422/503 semantics | frozen |
| RemoteStop attempts/timeout and Provider unknown 24h projection | frozen |
| Tenant/scope/amount/policy/stop-result client authority prohibition | frozen |
| Internal risk event envelope and canonical event types | frozen |
| P001 default compatibility | preserved |
| PAY-MP-002-v1 compatibility | preserved; D-204 fields excluded |
| BE-205 runtime, migration, QA/E2E, capacity, production | not implemented / no-go |

The v2 contract is frozen and is the single shared input for BE-205 and frontend risk adapters. This document does not authorize endpoint implementation, migration, deployment, production configuration or real payment.

## 13. 统一交接

```text
STATUS: done
GATE_STATUS: contract-frozen / implementation-ready-for-BE205

CHANGED_FILES:
- docs/features/PAY-MP-002/contracts/API.md

COMMANDS_RUN:
- architecture-agent 限定核验 CF-201～CF-206、P001 `/app/transactions`、Outbox tenant scope 与 Charging D1/rail 边界
- 刷新并冻结 PAY-MP-002-v2；同步 backend/frontend contract references、STATUS 和 architecture changelog
- 未修改业务代码、数据库、迁移、部署或生产配置

TEST_RESULTS:
- 本轮未运行业务测试；contract freeze 不构成运行时实现证据

CONTRACT_CHANGES:
- 保留 P001 默认 API 与 `PAY-MP-002-v1` 兼容边界
- 冻结 `PAY-MP-002-v2` D-204 safe projections、risk decision/status/errors、SLA、client-authority prohibition 和 internal event schema
- 状态推进为 `contract-frozen / implementation-ready-for-BE205`；本次未实现 endpoint 或业务逻辑

ARCHITECTURE_COMPLIANCE:
- Provider-neutral、Decimal/UTC、tenant/RBAC server authority、Hosted sensitive boundary、幂等和 fail-closed 保持
- v2 采用 UTC rolling 24h window；P001 默认和 v1 compatibility 保持；客户端不能提交 tenant/scope/amount/policy/stop result

RISKS:
- runtime 仍未实现这些 typed resources，不能据此宣称代码完成、QA 通过或可上线
- BE-205 runtime、migration、independent QA/E2E、capacity、人工发布和真实资金仍未放行；生产 NO-GO
```
