---
id: PAY-MP-002
change_id: CHG-20260812-002
status: architecture-approved
owner: frontend-agent
contract_status: frozen
contract_version: PAY-MP-002-v2
compatible_contracts: P001-default, PAY-MP-002-v1
frontend_contract_sync: cf-206-closed-d204-v2
implementation_authorization: be205-contract-frozen-only
---

# PAY-MP-002 前端技术设计

## 1. 目标与边界

本设计在不改变 PAY-MP-001 Hosted Checkout、安全 Deep Link、支付方式和充电状态 owner 的前提下，为 App 增加欠费恢复/历史/退款/支持旅程，为 Admin 增加退款双控、三方对账、运行时 rail、支持和审计工作台。

前端只消费服务端 projection 和 `allowed_actions`，不计算 D1、金额、PaymentAllocation、rail、tenant、RBAC、审批或 Provider 结果。D-204 v2 只提供 RiskSession/RiskStop/ProviderResolution safe projections、risk decision/status/errors 和安全 next action；前端不拥有风险 authority。

本设计映射冻结的 `PAY-MP-002-v2`，并保留 P001 默认与 `PAY-MP-002-v1` compatibility adapter；实现必须遵守单一 v2 contract，不得按 query/body 发明第二版本机制。

## 2. 当前基线与扩展策略

### App

- 保留 `app/src/features/payment/checkoutCoordinator.ts` 作为 Hosted checkout 的单一恢复协调器。
- 保留 `PaymentResult` 对 P001 add-payment/top-up/direct-charge 的既有语义；`unpaid_charge` 分支额外读取 RecoveryAttempt/Allocation/Eligibility，不复用“approved 即成功”的展示。
- 保留 `/api/v1/app/transactions` 与 detail 作为历史入口：默认 P001 bare array/offset/既有类型完全不变；P002 adapter 仅通过 `Accept: application/vnd.eslatin.pay-mp-002.v1+json` 获取 cursor/decimal-string 投影，避免创建第二套 charging-history API。
- 替换 `UnpaidBillsScreen` 对旧 `/wallet/unpaid-charges` 数组的依赖；旧路径只保留后端兼容，P002 页面不调用。
- App 与 Admin 不共享 store、导航或认证；仅分别实现同一 frozen contract 的 adapter。

### Admin

- 新能力不建立在当前 Provider/Wompi metadata 页面和直接 reconcile 按钮之上。
- 采用 Provider-neutral resource pages；服务端返回 scope、permission projection、version 与 `allowed_actions`。
- 现有 `X-Tenant-Id` 仅为请求上下文，服务端仍从 actor membership 和资源 owner 裁决。

## 3. App 信息架构

### 3.1 路由

现有路由继续保留，新增内部 typed routes：

```ts
type PaymentRoutes = {
  UnpaidBills: undefined;
  UnpaidBillDetail: { invoiceId: string };
  RecoveryStatus: { recoveryAttemptId: string; invoiceId: string };
  SupportCases: undefined;
  SupportCaseDetail: { caseId: string };
};
```

外部 linking 不接受这些资源 ID。外部支付回跳仍只进入既有 `payment-return`，校验 checkout session id/status 长度和 allowlist，再由服务端响应恢复关联的 attempt。

入口：

- D1 阻断卡片：主 CTA 打开 `UnpaidBills`，次 CTA 打开支持。
- PaymentHub/Account：显示欠费入口；badge/数量必须来自服务端，不读本地布尔值作为事实。
- ChargingHistoryDetail：按服务端 `allowed_actions` 显示欠费详情、退款状态或支持入口。

### 3.2 页面职责

#### UnpaidBills

- 使用 opaque cursor 追加加载，固定按服务端顺序渲染。
- 首屏 loading、刷新、加载更多、真实 empty、partial page、cursor invalid、offline/error 分开。
- 卡片只显示 Invoice 安全摘要、outstanding COP、D1 状态、最近恢复状态和更新时间。
- 失败不得 `catch => []`；empty 只来自成功响应。

#### UnpaidBillDetail

- 读取单个不可变 Invoice projection、Payment/Allocation/Refund/Chargeback timeline、`available_methods`、`allowed_actions` 和支持关联。
- 金额/币种/merchant/tenant/Invoice target 只读；不允许选择/合并多张欠费账单。
- 支付方式禁用原因由服务端 code 映射；前端不依据余额、卡类型、构建 flag 或历史状态自行开放。
- 点击支付先创建 RecoveryAttempt；重复点击锁定到当前 request，网络 unknown 先 GET detail/active attempt。

#### RecoveryStatus

- 以 `recovery_attempt_id` 为唯一查询目标，渲染 `created/processing/action_required/approved/allocated/declined/failed/cancelled/expired/manual_review/unknown`。
- `approved` 表示 Provider/checkout 阶段已批准，不代表 Invoice 已分配或 D1 已解除。
- `manual_review + reason_code=duplicate_approval + allocation=null` 表示迟到非赢家；不得创建第二条 Allocation 或自动退款，原赢家保持 `allocated/confirmed`。
- 只有 `allocation.status=confirmed` 且 `eligibility.status=eligible` 才显示“继续充电”。
- `unknown`、503、超时和应用恢复只继续 GET；不自动 POST 新 attempt。

#### ChargingHistory / Detail

- 复用现有 transaction 列表/详情，增加 `data_quality`、账单/恢复/退款/拒付/支持状态与安全 timeline。
- `legacy/unknown` 明确显示“信息仍在确认”，不推导 paid 或 D1 eligible。
- 不提供 PDF、邮件、下载或 DIAN 收据入口。

#### SupportCases / Detail

- 支持列表/详情覆盖 open 到 closed、SLA target、safe timeline 和关联资源。
- 用户退款诉求以 `category=refund_request` 创建 SupportCase；关联 RefundCase 后只展示其服务端 projection。
- 描述框禁止引导输入卡号/CVV/密码/证件；客户端日志对自由文本按现有隐私规则处理。

## 4. App 数据层与恢复协调

### 4.1 Adapter

建立 PAY-MP-002 feature adapter，职责仅为：

- 固定发送和验证 `PAY-MP-002-v1` media type；transactions 只有 P002 adapter 发送 vendor `Accept`，P001 adapter 不加 vendor header；
- URL/query 编码和 cursor page 解码；
- runtime schema guard；严格映射 `provider_approved→approved`、`committed→confirmed`、`needs_review→unknown`、`recheck_required→evaluating`，其他未知 enum 映射为 `unknown`；
- Decimal string 保持为 string，展示层才格式化；
- 保存 canonical error 的 `code/reference/retryable/retry_after_seconds`；
- 绝不接受前端传入 tenant、amount、currency、merchant、Provider 或最终状态。

禁止页面直接拼 endpoint 或读取 raw `response.data`。P002 transactions 携带 `offset` 是客户端缺陷，必须在 adapter 阻止；收到 `406 CONTRACT_VERSION_UNSUPPORTED` 或 `400 PAGINATION_MODE_INVALID` 进入安全错误态，不能回退并猜测另一版本。

### 4.2 Recovery coordinator

在现有 checkout coordinator 上增加非敏感关联，不另建 Provider coordinator：

```ts
type PendingRecoveryRef = {
  checkoutSessionId?: string;
  recoveryAttemptId: string;
  invoiceId: string;
  expiresAt: string;
  source: 'unpaid_recovery';
};
```

只允许存储 opaque IDs/expiry/source，不存 checkout URL、卡信息、Provider token、金额或权限。相同 attempt 的 GET 使用 in-flight dedupe；POST 使用同一 client-generated idempotency key，网络 unknown 后先查询，不换 key 重试。

### 4.3 Hosted next action

只执行 contract 允许的：

- `none`
- `poll`
- `open_checkout`（既有同源 checkout URL）
- `open_provider_url`（既有 Provider host allowlist）
- `contact_support`

未知 type、无效 URL、过期或 audience 不符一律 fail closed 并显示 reference。

### 4.4 D1 资格

FinancialEligibility adapter 只消费财务 `eligible|blocked|evaluating|unknown`，其中 `recheck_required` 已由服务端投影为 `evaluating`；reason code 中不得出现 `rail_closed`。App 可在补缴 allocation 收敛、退款/拒付后重新进入和应用恢复时刷新该事实，但不能只凭 `eligible` 启动某个资源。

收费资源 UX 必须调用 `POST /api/v1/app/charging/preflight`，只提交 `qr_token` 和 `settlement_method`。服务端解析 charge point/site/connector/pricing/provider 和 platform/provider/tenant/site scopes，分别返回 FinancialEligibility、`paid_admission` rail 与组合 decision。前端不发送 tenant/site/provider/scope，不把预检结果持久化为能力 token。

用户最终点击启动仍调用 `/api/v1/app/charging/start`；服务端在同一请求内重新解析资源并重算财务资格和 scoped rail。只有 start 的 authoritative 成功响应才进入 RemoteStart 旅程。`RAIL_CLOSED` 与 `RAIL_STATE_UNKNOWN` 独立于 FinancialEligibility 显示并 fail closed。

## 5. App 状态与呈现矩阵

| 领域状态 | 主文案/动作 | 禁止行为 |
|---|---|---|
| list loading | skeleton + 可返回 | 显示空列表 |
| list empty | 无欠费；允许返回充电入口前再次读 eligibility | 从本地 empty 推导 eligible |
| recovery processing | 正在确认；轮询/刷新 | 宣称已支付、重复创建 |
| action_required | 打开经校验的 Hosted action | 页面采集 PAN/CVV/证件 |
| approved | 支付已获确认，正在应用到账单 | 解锁 D1 |
| allocated + eligible | 已结清且当前可继续充电 | 使用本地金额判断 |
| allocated + blocked | 已处理本账单，仍有其他阻断项 | 宣称全部欠费已清除 |
| manual_review / duplicate_approval | 资金需人工核对 + support reference | 创建第二条 Allocation、自动退款或解锁 |
| declined/failed | 安全原因 + 允许动作 | 显示 Provider raw error |
| unknown | 状态待确认 + 查询/支持 | 自动重试写操作 |
| refund/chargeback | 显示 case 状态、SLA、对资格影响 | 本地决定 D1 |

## 6. Admin 信息架构

新增受权限控制的页面组，路由名称可在实现阶段按现有 Next.js 结构落位，但资源语义必须保持：

```text
Payments Operations
├─ Refund cases
├─ Chargeback cases
├─ Reconciliation runs / exceptions / CSV export
├─ Support cases
├─ Runtime rails
└─ Audit events
```

### 6.1 通用列表/详情

- 所有列表由服务端按 `PAY-MP-002-v1` cursor 分页并使用契约固定 stable sort；前端不得本地重排后再生成下一 cursor。URL search params 只保存非敏感筛选，便于刷新/分享。
- tenant/platform scope 显示为服务端 projection；不可见资源统一安全 403/404。
- detail 展示 version、updated time、actor references、safe Provider reference、timeline、`allowed_actions`。
- SWR/cache key 包含资源和服务端确认的 scope；切换 tenant context 时清除跨 scope cache。
- 前端不读取 raw Outbox，也不假设每个 platform 事件都有 tenant；`platform:eslatin` 投影可无 tenant，资源 ownership 仍以服务端 HTTP projection 为准。

### 6.2 退款双控

1. Initiator 创建 RefundCase，输入服务端允许范围内的 requested amount/reason。
2. 页面刷新 case，显示 `approval.required=true` 和 initiator。
3. 不同授权 actor 才会从服务端收到 `approve/refuse` action；UI 不自行比较账号 ID。
4. decision 提交 `expected_version` 和 idempotency key；409 后刷新，不覆盖。
5. Provider processing/unknown、partial/refunded/rejected 都由查询结果渲染。

### 6.3 三方对账

- Run 列表/详情显示 source watermarks、cutoff、matched/pending/mismatch/manual-review 汇总。
- Exception resolution 只能提交 intent；不能直接切为 matched。
- 临时例外分 create request 与 different-actor decision；倒计时使用服务端 `expires_at`。
- CSV 创建固定接收 `202 ReconciliationExportProjection`，UI 轮询同一 resource 并渲染 `queued→generating→ready→downloaded`；`failed/expired` 为独立终态。只有 ready 才使用固定同源 download path 一次下载；处理 `EXPORT_NOT_READY/FAILED/CONSUMED/EXPIRED`，不把 bearer token 放 URL，不导出 raw Provider payload。

### 6.4 Runtime rails

- 页面分 `paid_admission` 和 `payment_creation` 两轴，并展示 scope、status、reason、incident、version、closed_by、reopen request。
- close 是单人受限动作；reopen 必须创建 request，再由另一授权 actor 决定。
- `processing/unknown` 保持原状态并要求刷新；前端不自动恢复。
- 明确说明 close 不停止 Webhook、query、refund、chargeback、reconciliation、history、support 或进行中 OCPP 会话。

### 6.5 Support、Chargeback、Audit

- Support event 只改变案件协作状态，不直接改变 Payment/Refund/D1。
- Chargeback 只展示 canonical state、金额/hold、deadline、allowed actions 和关联审计。
- Audit 页面不展示 secret/raw payload；按 actor/resource/action/result/time filters 服务端分页。

## 7. Admin RBAC 与审批呈现

前端使用服务端返回的固定 permissions 和 resource `allowed_actions` 控制可见性，但所有请求都允许服务端再次 403/404/409。`PAY-MP-002-v1` 只认：

`payment.read`, `refund.request`, `refund.approve`, `chargeback.read`,
`reconciliation.read`, `reconciliation.resolve`, `reconciliation.exception.request`,
`reconciliation.exception.approve`, `support.manage`, `rail.read`, `rail.close`,
`rail.reopen.request`, `rail.reopen.approve`, `audit.read`。

组件不得发明别名，也不得用 `is_super_admin` 替代细粒度授权；superadmin `*` 的解释仍由服务端/现有 permission utility 负责。

统一 approval projection：

```ts
type ApprovalProjection = {
  status: 'not_required' | 'pending' | 'approved' | 'rejected' | 'expired' | 'unknown';
  initiator: ActorRef | null;
  approver: ActorRef | null;
  requestedAt: string | null;
  decidedAt: string | null;
  expiresAt: string | null;
  version: number;
};
```

它是显示结构，不是客户端授权依据。

## 8. 错误、并发和幂等 UX

- Adapter 将 HTTP + canonical code 映射为 typed result；组件不匹配英文 message。
- `CONTRACT_VERSION_UNSUPPORTED/PAGINATION_MODE_INVALID/REQUEST_INVALID` 是契约错误，不降级猜测 P001/P002 或另一成功 body。
- `PERMISSION_DENIED/RESOURCE_NOT_FOUND` 不泄露目标是否存在。
- `RESOURCE_VERSION_CONFLICT/APPROVAL_CONFLICT/RECOVERY_CONFLICT` 先重新 GET，保留用户输入但不自动重发。
- `RAIL_CLOSED/RAIL_STATE_UNKNOWN/FINANCIAL_ELIGIBILITY_BLOCKED/FINANCIAL_RECHECK_REQUIRED` 分开显示服务端 safe reason 和支持入口，不显示 D-204 参数。
- `EXPORT_NOT_READY/FAILED/CONSUMED/EXPIRED` 严格对应 §6.3 生命周期，不签发或猜测第二种下载 URL。
- `PROVIDER_UNAVAILABLE/RECOVERY_UNKNOWN` 只允许查询、等待或支持。
- 每次写操作在用户确认时生成 idempotency key；按钮 loading 防抖不是幂等保证。

## 9. i18n、格式化和敏感数据

- 所有新文案以 key 写入 es-CO/en/zh；es-CO 为产品验收语言。
- Decimal string 通过共享 formatter 显示 COP；禁止 `Number(amount)` 参与业务判断或重新提交。
- UTC 通过现有日期工具本地化；server timestamp/version 优先于设备时钟。
- 错误展示安全 message + reference；日志仅记录 code/reference/resource type，不记录描述全文、checkout token 或 Provider payload。
- 卡品牌/支付方式 label 来自安全 projection；不要求用户手动选择 Visa/Mastercard 等卡类。

## 10. 响应式与可访问性

App：320px 窄屏、动态字号、44px 触控目标、Safe Area、屏幕阅读器顺序、错误 live announcement。Admin：支持既有桌面断点，窄屏表格可滚动/卡片化，危险操作 dialog 保持 focus trap，关闭后焦点返回触发器。

状态 badge 必须含文本；图标有 label；分页/筛选/confirm/reject/close/reopen 可用键盘；processing 不使用无限动画作为唯一信息。

## 11. 测试设计输入

前端实现后由独立 qa-agent 覆盖：

- adapter schema/unknown enum/error mapping/Decimal/UTC；
- CF-201 domain→public golden mapping 与 duplicate approval `manual_review/allocation=null`；
- P001 无 vendor Accept 的 array/offset/number-null golden response，以及 P002 vendor Accept 的 cursor/decimal-string/406/400/Vary；
- cursor paging、刷新、失败不伪装 empty；
- recovery 重复点击、网络 unknown、回跳、应用重启、换设备；
- approved 未 allocated、allocated 仍 blocked、refund/chargeback 后重新阻断；
- Hosted URL allowlist 和敏感日志扫描；
- Admin 三类双控的 same-actor denial、version conflict、expiry 和 permission denial；
- tenant scope/cache 切换、CSV export、rail unknown；
- QR context preflight 与 `/charging/start` 重算；FinancialEligibility 不含 rail reason；platform scope 不伪造 tenant；
- es-CO、窄屏/桌面、键盘、focus、screen reader；
- P001 add card/top-up/direct charge/payment result 和现有 history 回归。

E2E 在前后端 QA 通过后覆盖 D1 → Invoice → Recovery → Allocation → Eligibility → 重新充电，以及 refund/chargeback/reconciliation/rail/support 的跨模块收敛。

## 12. CF-206 同步结论

- CF-201～CF-205 的前端 adapter、状态、权限、分页、HTTP/body、错误和 CSV 行为均直接引用 `PAY-MP-002-v1`，没有第二套命名或兼容策略。
- Frontend 不消费 raw Outbox；platform scope 不要求 tenant，不会用 dummy/selected tenant 补值。
- 本设计状态是 `candidate-cf-closed-by-backend-and-frontend / not-frozen`，只等待 architecture-agent 限定复审。

## 13. D-204-B v2 contract mapping

- App/Admin 使用 `Accept: application/vnd.eslatin.pay-mp-002.v2+json` 获取 D-204 projections；P001 default 与 v1 routes 保持既有协商和响应兼容。
- 客户端只发送用户旅程所需的业务输入；tenant、scope、amount、policy version、attempts、timeout、stop result、provider status 和 raw Provider payload 均禁止进入 request body/query。
- `406 CONTRACT_VERSION_UNSUPPORTED`、`409` version/idempotency/risk-state conflicts、`422 CLIENT_AUTHORITY_FORBIDDEN` 和 `503 RISK_STATE_UNKNOWN` 按 API.md §12 映射；unknown projection 不得渲染为成功。
- UTC rolling 24h window、active/unresolved inclusion 和 released/settled exclusion 只作为服务端 safe display projection，客户端不重算。

## 14. 非目标与门禁

- 不实现 D-204 风险预算、风险 ledger、阈值文案、RemoteStop 或默认参数。
- 不实现用户 PDF/邮件/下载/DIAN 收据。
- 不实现客户端金额、D1、rail、tenant、RBAC、审批或 Provider 终态计算。
- 不改变 P001 Hosted fields、OCPP owner、数据库、迁移、部署或生产配置。
- contract refresh 已冻结；前端 runtime、独立 frontend QA、E2E 和生产发布仍保持各自门禁。
