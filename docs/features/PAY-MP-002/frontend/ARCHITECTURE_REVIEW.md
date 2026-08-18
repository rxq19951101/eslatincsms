---
id: PAY-MP-002
change_id: CHG-20260812-002
status: architecture-approved
owner: frontend-agent
review_scope: app-admin-frontend-architecture-and-contract
contract_status: frozen
contract_version: PAY-MP-002-v2
compatible_contracts: P001-default, PAY-MP-002-v1
frontend_contract_sync: cf-206-closed-d204-v2
implementation_authorization: be205-contract-frozen-only
---

# PAY-MP-002 前端架构审核

## 1. Verdict

**前端 verdict：`architecture-approved / contract-frozen`。**

已批准产品范围可以在现有 App/Admin 边界内实现，不需要新的产品选择，也没有发现要求改变 ADR-004/ADR-005 的前端阻塞项。frontend-agent 已完成 CF-206，并同步 `PAY-MP-002-v2`；P001 默认 API 与 `PAY-MP-002-v1` 兼容边界保持不变，v2 D-204 projections 现已冻结。

D-204 v2 只冻结 App/Admin 安全投影与状态/错误映射；本设计不实现风险 runtime、默认值计算、RemoteStop 或 Provider command。BE-205 runtime、前端 QA/E2E 和真实资金发布仍是独立门禁。

本轮只修改前端架构/技术设计/任务、共享候选契约和前端状态交接；未修改 App/Admin 业务代码、后端设计、数据库、迁移、部署或生产配置。

## 2. 审核输入与当前代码事实

已读取治理文件、frontend-agent 运行规则、产品/技术架构、前端边界、ADR-004/005、CHG-20260812-002、PAY-MP-001 基线、PAY-MP-002 产品批准记录、总架构审核、后端设计、候选契约、状态以及当前 App/Admin 代码和工作区 diff。工作区含负责人已有改动，本轮不回退、不清理、不取得业务代码所有权。

| 区域 | 当前代码事实 | PAY-MP-002 差距与复用结论 |
|---|---|---|
| App 导航 | 已有 `PaymentResult`、`PaymentHub`、`PaymentMethods`、`ChargingHistory`、`ChargingHistoryDetail`、`UnpaidBills`；Main Tabs 有 Wallet/Account。 | 复用现有栈；增加欠费详情、恢复状态、支持案件详情的内部路由，不建立第二套支付导航。 |
| P001 Checkout | coordinator 仅持久化非敏感 checkout 引用，Deep Link/前台/轮询统一 GET；Hosted 页面负责敏感数据。 | 继续复用 Hosted boundary；P002 额外持久化非敏感 `recovery_attempt_id`/`invoice_id`，回跳后查询 Recovery/Allocation/D1，不把 checkout approved 当作已解锁。 |
| 欠费页 | 当前 `UnpaidBillsScreen` 使用旧 `/wallet/unpaid-charges` 数组与 session-id 钱包补缴，并把请求失败降成空列表。 | P002 UI 改用分页 Invoice 资源；错误、空列表、processing、unknown 必须可区分。旧接口仅兼容，不作为新页面 authority。 |
| D1 | `ChargingProcessScreen` 能展示 `UNPAID_CHARGES` 阻断。 | 增加明确的欠费入口；FinancialEligibility 只表达财务资格，收费资源必须用 QR context 执行组合 preflight，`/charging/start` 再重算；本地支付结果、余额或预检缓存都不能授权启动。 |
| 支付结果 | `PaymentResultScreen` 对 P001 checkout 的 `approved` 作为支付成功终态。 | P001 行为保持；当 purpose 为 `unpaid_charge` 时，approved 仅触发 Recovery 查询，直至 allocation 和 D1 recheck 收敛。 |
| 历史 | 现有 `/api/v1/app/transactions` 列表/详情展示充电、Invoice 和基础 billing 状态。 | 默认请求严格保持 P001 bare array、offset/limit 和既有 number/null 类型；只有 vendor `Accept: application/vnd.eslatin.pay-mp-002.v1+json` 获得 P002 cursor/decimal-string 投影，不另建 `/charging-history`。 |
| Admin 支付 | 当前 `/payments` 为 super-admin 页面，读取 Provider/Wompi 导向数据，可直接 reconcile，并显示 metadata/webhook。 | 新运营能力使用 Provider-neutral 资源、服务端 `allowed_actions` 和细粒度权限；不复用直接改状态或 raw metadata 的交互。 |
| Admin rail | 当前设置页主要展示构建/环境配置。 | 运行时 rail 独立为服务端控制事实；构建 flag 仅作外围 kill switch，不作为 UI 业务裁决。 |
| 权限/租户 | Admin 从服务端读取 permissions，但会发送客户端选择的 `X-Tenant-Id`。 | 菜单/按钮只做体验优化；服务端必须重新裁决 actor、资源 tenant/platform scope、双控与版本。 |
| 错误 | App/Admin adapter 主要把 HTTP 错误折叠成文本。 | P002 adapter 保留安全 `code/reference/retryable/retry_after_seconds`，再映射 es-CO 文案；不显示 Provider 原始错误。 |

## 3. 前端边界审核

### 3.1 App

App 只拥有界面状态和用户意图：欠费查看、选择服务端允许的支付方式、打开 Hosted Checkout、恢复查询、查看历史/退款/拒付/支持投影以及导航。以下事实均由服务端拥有：

- Invoice、金额、币种、PaymentAllocation、RecoveryAttempt 状态；
- D1/FinancialEligibility、refund/chargeback/reconciliation 重新阻断；
- rail 是否开放及某种支付方式是否可用；
- 用户、租户、支付方式所有权和资源可见性；
- 支付、退款、审批和支持的最终结果。

App 不提交或计算金额、D1、tenant、merchant、Provider、rail、审批人、风险阈值或退款终态。

### 3.2 Admin

Admin 只展示授权投影并提交操作意图。退款、对账临时例外和 rail 恢复都由服务端创建/批准状态机保证双控；前端显示 initiator、approver、version、expiry、reason、scope 和 `allowed_actions`，但不自行判定“不同人员”或允许跨租户操作。

Admin 不直连 Provider，不展示/存储 raw Provider payload、PAN、CVV、证件、token、secret，也不通过隐藏菜单代替 RBAC。

### 3.3 Hosted sensitive boundary

PAN、CVV、证件号、卡 token 化及 3DS 继续完全位于 Mercado Pago Hosted/Secure Fields 边界。App 只保存短期、非敏感、可撤销的 checkout/recovery 引用。URL 必须通过既有 same-origin/Provider allowlist 校验，日志和错误追踪不得记录完整 URL token。

## 4. 用户旅程覆盖

### 4.1 App 欠费恢复

```text
D1 服务端阻断
→ 欠费列表（分页）
→ 不可变 Invoice 详情
→ 服务端 available_methods
→ wallet / new_card / saved_card + Hosted CVV
→ RecoveryAttempt processing/action_required/unknown/declined
→ PaymentAllocation confirmed
→ FinancialEligibility 全局重算
→ 以 QR/settlement context 执行 ChargingAdmissionPreflight，组合 scoped rail
→ 用户发起 /charging/start，服务端在同一请求内重新执行组合 preflight
→ start 返回 allowed 才继续；否则显示财务/rail 的独立安全原因和支持入口
```

网络 unknown、重复点击、应用重启、外部回跳和换设备都恢复同一 attempt，不自动创建第二笔。单笔 Invoice 已付也不能推导全局 D1 已解除。

迟到重复批准固定显示为 `manual_review`、`reason_code=duplicate_approval`、`allocation=null`；原赢家仍是 `allocated/confirmed`。前端不得创建第二条 Allocation、自动退款或从迟到的 `approved` 推导结清。

### 4.2 App 历史、退款与支持

- 历史复用现有 transactions 路径，显示充电、账单、补缴、退款、拒付和支持的非敏感时间线。
- `paid/approved`、`allocated`、`refunded`、`disputed`、`unknown` 分开显示；旧数据缺事实时标为 `legacy/unknown`。
- 用户的退款诉求先形成结构化 SupportCase；若运营创建 RefundCase，则详情显示关联退款状态和 SLA，不允许 App 直接调用 Provider 退款。
- 提供支持案件列表/详情和上下文入口；只传服务端可验证的资源 ID/问题类别，不传敏感卡数据。
- D-205-A 只提供基础结构化历史；不得新增 PDF、邮件、下载收据或 DIAN 收据/发票能力。

### 4.3 Admin 运营旅程

- **退款双控**：发起人创建 request；另一授权身份 approve/reject；UI 显示待审批、过期、版本冲突、Provider processing/unknown 和审计引用。
- **三方对账**：run → item/exception → resolution intent；符合范围的 24h 临时例外也采用 finance 发起、platform 另一人决定，不能直接改成 matched。
- **运行时 rail**：一人可关闭；恢复必须创建 request 并由另一人批准，服务端健康检查失败/unknown 时保持 closed。
- **拒付/支持/审计**：只读 canonical 状态和安全事件；支持事件不能直接改账务终态。
- **导出**：只允许认证、同源、权限过滤的异步对账 CSV；UI 严格处理 `queued→generating→ready→downloaded`，并处理 failed/expired/not-ready/consumed。它是财务运营导出，不是 D-205-A 用户收据。

## 5. UI 状态、导航和展示要求

所有 App/Admin 资源统一覆盖：

| 状态 | UI 行为 |
|---|---|
| loading | skeleton/progress；禁用重复写操作，但保留返回/取消。 |
| empty | 仅在成功响应的 `items=[]` 显示；请求失败不得伪装为空。 |
| processing | 显示安全状态、更新时间和可查询动作，不宣称成功。 |
| action_required | 仅执行服务端 `next_action`；URL 需校验。 |
| unknown | fail closed；允许刷新/继续查询/支持，不自动重试写请求。 |
| error | 按 canonical code 映射 es-CO 文案并展示 reference；未知 code 使用安全兜底。 |
| recovery | 读取同一 resource/version；409/503 后先 GET，不能创建替代动作。 |

导航要求：

- D1 页面、PaymentHub/Account、历史详情均可进入欠费或支持；完成恢复后按服务端资格决定返回充电还是继续欠费。
- 外部 deep link 只接受既有 checkout return 参数和长度/状态 allowlist；Invoice/attempt/case 只使用内部 opaque ID 并重新 GET 鉴权。
- 浏览器/移动端返回、应用重启和前后台切换不丢失恢复目标；过期引用回到安全详情而不是错误成功页。

## 6. i18n、响应式与可访问性

- es-CO 是验收主语言；金额只由 Decimal string 格式化为 COP，时间以服务端 UTC 转用户 locale。
- App 适配手机窄屏、动态字号和触控目标；Admin 覆盖桌面及最小支持宽度，表格在窄屏转卡片/横向滚动且不隐藏状态和审批人。
- 所有状态不能只靠颜色；按钮有可访问名称，错误与状态更新使用 live region，dialog 管理焦点，表格有 header，键盘可完成筛选、分页、确认和取消。
- Provider/card brand 由 Hosted/服务端安全投影提供；用户不手动选择“卡类”来决定路由。

## 7. CF-206 同步结果

frontend-agent 逐项确认并同步后，没有发现前端与后端唯一候选冲突：

1. **CF-201 closed：** adapter 只消费 §3.10 固定 domain→public 投影；`provider_approved→approved`、`committed→confirmed`、`needs_review→unknown`、`recheck_required→evaluating`。未知状态 fail closed。迟到非赢家固定为 `manual_review/duplicate_approval/allocation=null`。
2. **CF-202 closed：** transactions adapter 的默认请求继续是 P001 bare array + offset/limit + 既有 number/null 类型；P002 只发送 `Accept: application/vnd.eslatin.pay-mp-002.v1+json`，消费 cursor/decimal string，并处理 `406 CONTRACT_VERSION_UNSUPPORTED`、`400 PAGINATION_MODE_INVALID` 和 `Vary: Accept`。不存在 query/body/其他 header 版本分支。
3. **CF-203 closed：** FinancialEligibility 只渲染财务资格，不能包含或推断 rail。收费入口把 `qr_token` 与 `settlement_method` 交给 `/app/charging/preflight`；资源/Provider/scope 全由服务端解析；预检不是 capability token，`/charging/start` 必须重新执行组合 preflight。
4. **CF-204 closed：** 前端不消费 raw Outbox，不为 platform event 构造 tenant，也不从 scope 反推资源 ownership。`platform:eslatin` 可以没有 tenant；App/Admin 只消费 HTTP 的服务端 scope/allowed-actions 投影。
5. **CF-205 closed：** Admin adapter 使用 §6 固定 permission strings、Projection fields、endpoint HTTP/body、stable sort 和 §7 单一错误码。CSV 唯一生命周期为 `queued→generating→ready→downloaded`，失败/过期独立处理，只有 ready 可按固定同源 path 下载一次。
6. **CF-206 closed：** 本前端架构、技术设计和任务引用 v1 compatibility 与冻结的 `PAY-MP-002-v2`；未改变后端唯一化语义。

D-204 runtime、BE-205 业务实现和真实资金发布仍严格排除；v2 contract 已冻结，前后端不得分叉资源、状态、错误或审批语义。

## 8. 需 architecture-agent 复审的精确事项

以下是限定技术复审项，不需要 Product Owner 选择：

- P001 checkout `purpose=unpaid_charge` 与 P002 `recovery_attempt_id` 的 additive 关联是否符合现有 adapter/outbox 边界；
- FinancialEligibility 与 scoped rail 的分层、QR resource context 和 `/charging/start` 重算是否一一对应；
- transactions 的 vendor `Accept` 协商是否完整保持 P001 array/offset/type，并隔离 P002 cursor/decimal-string；
- Refund、reconciliation exception、rail reopen 的两步 approval resource 与后端 command/state machine 是否一一对应；
- Admin 固定 permissions、HTTP/body/stable sort/errors 和 CSV lifecycle 是否与后端状态机一一对应；
- support/refund 关联和 `allowed_actions` 是否均由服务端 authoritative projection 生成。

## 9. Completion SELF_CHECK

1. 原始目标是仅执行 CF-206；本轮没有进入实现、产品、后端设计或开放式研究。
2. 当前产物只同步三份前端文档、共享契约前端状态和 STATUS，直接完成原始任务。
3. 新证据是 CF-201～CF-205 已有唯一后端候选，前端逐项可无分叉消费；没有新产品决定。
4. 无无理由重读、无 scope drift、无隐藏治理冲突；重大自我修正次数为 0。
5. 当前 gate 有证据支持 `candidate-cf-closed-by-backend-and-frontend / not-frozen`；唯一下一动作是 architecture-agent 限定复审。
6. D-204/BE-205/风险参数/UI/runtime/真实资金仍被排除。

## 10. 实现门禁

前端实现仍为 `blocked-until-architecture-approval-and-contract-freeze`。通过复审后依赖顺序为：共享契约冻结 → 后端 typed resource/adapter → App/Admin adapter 与路由 → 页面/状态恢复 → frontend QA → cross-module E2E。

当前没有真正产品决策 blocker；D-204 继续隔离在 TODO 和生产发布门禁之外。

## 11. 统一交接

```text
STATUS: done

CHANGED_FILES:
- docs/features/PAY-MP-002/frontend/ARCHITECTURE_REVIEW.md
- docs/features/PAY-MP-002/frontend/TECH_DESIGN.md
- docs/features/PAY-MP-002/frontend/TASKS.md
- docs/features/PAY-MP-002/contracts/API.md
- docs/features/PAY-MP-002/STATUS.md

COMMANDS_RUN:
- frontend-agent-carson 重新加载 AGENTS.md、RUNTIME_POLICY、frontend-agent skill 和 CF-206 权威文档，并执行 startup/completion SELF_CHECK
- 仅对照后端已唯一化的 CF-201～CF-205 和 `PAY-MP-002-v1`，未扩展研究
- 仅用 apply_patch 修改获准的五份文档

TEST_RESULTS:
- 未运行业务测试或构建；本轮没有业务代码变更
- 文档范围、状态、D-204 隔离和契约交叉引用一致性检查通过

CONTRACT_CHANGES:
- 未改变后端唯一化 API/domain/event 语义；完成 CF-206 前端同步
- contract 状态推进为 candidate-cf-closed-by-backend-and-frontend，仍未 frozen

ARCHITECTURE_COMPLIANCE:
- C3 总 verdict 仍为 changes-required；前端子审核 ready-for-architecture-rereview
- 保持 P001 Hosted boundary、服务端 tenant/RBAC/D1/金额/rail/审批 authority 和 Provider-neutral core

RISKS:
- v2 contract 已冻结；风险 runtime、前端 QA/E2E 和真实资金发布仍 blocked
- 客户端不得提交 tenant、scope、amount、policy version、attempts、timeout、stop result 或 raw Provider payload

## D-204-B v2 frontend contract handoff

- App consumes only the safe RiskSession/RiskStop/ProviderResolution projections and `risk_decision`/`risk_status`/canonical errors from `PAY-MP-002-v2`.
- Admin receives only server-authorized tenant/site/platform projections and `allowed_actions`; neither App nor Admin is an authority for tenant, scope, amount, policy version, stop result or Provider payload.
- `unknown` is rendered safely; a persisted Provider unknown remains non-success and converges for 24 hours. A `503` risk authority failure is fail-closed and must not be presented as an admission success.
- No frontend endpoint or business logic was implemented in this contract refresh.
```
