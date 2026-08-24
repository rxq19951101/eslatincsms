---
id: PAY-MP-002-BE-FEASIBILITY-EVIDENCE
change_id: CHG-20260812-002
status: evidence-baseline-complete-implementation-blocked
owner: backend-agent
scope: BE-211-A, BE-204
evidence_date: 2026-08-12
---

# PAY-MP-002 后端 feasibility evidence

本文件是 BE-211-A 和 BE-204 的只读证据层。它记录当前工作树实际代码/schema 与官方 Mercado Pago Colombia 资料之间的可验证边界；不构成 API、数据库、事件、Provider adapter、迁移、部署或生产配置批准。

## 1. 证据规则和结果

证据状态只使用以下含义：

- `observed`：从当前仓库代码、模型、迁移、配置默认值或当前 diff 直接观察到。
- `official-candidate`：官方资料描述的候选能力；不能证明当前商户、当前凭证、当前产品流或当前 adapter 可用。
- `verified-sandbox`：本商户 sandbox 中可重复执行并保存脱敏 request/response、Provider reference、Webhook/status 序列和重放结果。
- `unsupported-current-integration`：当前代码/协议没有该能力，或当前边界明确不能承载该事实。
- `unverified`：本轮没有真实 sandbox replay 或当前商户书面确认；不能作为“集成通过”。

本轮结果：仓库/模型基线为 `observed`；Mercado Pago Orders/manual-flow 能力为 `official-candidate`；真实 sandbox matrix 全部仍为 `unverified`，除非明确标注为当前代码已经存在的自动 Payments API 行为。没有读取或使用生产凭证，没有调用真实支付 API，没有创建/捕获/退款交易，也没有执行压测或数据库写入。

## 2. BE-211-A：当前后端实际基线

### 2.1 财务、会话、钱包和审计实体

| 实体/表 | 当前实际事实（代码/模型） | 索引、锁和当前边界 | P002 缺口/脏数据风险 |
|---|---|---|---|
| `ChargingSession` / `charging_sessions` | `tenant_id`、EVSE/CP、OCPP `transaction_id`、AppUser、起止时间、meter start/stop、`status`、`payment_status`、`payment_order_id`、deadline；状态 CHECK 只有 `ongoing/completed/cancelled`。 | CP+EVSE+transaction unique；status/idTag/start/CP/tenant indexes。Start/Stop/MeterValues 路径对 session 使用 `FOR UPDATE`。 | payment_status 没有 DB CHECK；没有 composite tenant FK 保证关联事实同租户；RemoteStart accepted 不是 session/financial fact；StopTransaction 未到时会保留未收敛事实。 |
| `Order` / `orders` | 旧订单与 `pre_authorization` JSON；当前 `charging_payment_intent` 只写版本化、非敏感 charging intent，不能解释成 Provider authorization。 | status/user/created/tenant indexes；intent lookup 可按 owner/tenant/CP 加锁，但 JSON 解析不是 DB 约束。 | JSON 可变、缺少 typed operation/authorization facts；legacy `pre_authorization` 与当前 intent 混杂，错误/未知文档会被跳过而不是可查询事实。 |
| `PricingSnapshot` / `pricing_snapshots` | 服务端 tariff、COP price/service fee、session/order reference、snapshot data/time；Billing 在结束结算时读取或创建。 | session/order/tenant indexes；由 Billing 事务写入。 | snapshot data 没有版本/hash 强制；历史金额可重建性依赖当前写入完整性，不能用客户端 amount。 |
| `Invoice` / `invoices` | 每个 session 仅一张（`uq_invoices_session`）；tenant/session/order/pricing snapshot；`energy_kwh`、duration、rate、energy/service/total COP；status comment 为 pending/paid/cancelled/refunded。 | status/session/order/issued_at/tenant indexes；Billing 查询 Invoice `FOR UPDATE`，IntegrityError 后按 session 重载。 | 状态没有 DB CHECK；没有 immutable trigger/hash/version；没有 allocation、partial settlement、reversal、refund/chargeback/hold/reconciliation facts。唯一 session 约束也不等于足额结算。 |
| `Payment` / `payments` | invoice、tenant、amount、method/provider、nullable unique `transaction_id`、status pending/completed/failed/refunded。 | status/invoice/transaction/tenant indexes；Billing/settlement 依赖事务锁和应用检查。 | 没有 invoice+operation 唯一事实或 payment attempt；status 没 DB CHECK；同一 Invoice 的多笔 completed 只能由应用锁防止，数据库不能独立证明。 |
| `PaymentOrder` / `payment_orders` | AppUser、type、Decimal COP amount/currency、provider、idempotency、Wompi/MP refs、JSON `metadata`、expires/deadline；status CHECK 为 created/processing/approved/declined/voided/error/expired/refunded。 | user+created/status/type/provider indexes；user+idempotency、Wompi tx、MP payment id unique。当前 create/reconcile/refund 分支使用 row lock，但 provider call 有锁外窗口。 | 没有 tenant_id 直接列、authorization/capture/void operation、partial/final capture、attempt、funds hold/release、chargeback、reconciliation case；status CHECK 无 action_required/waiting_capture/charged_back/partially_refunded 等 P002 语义。metadata 不是权威账本。 |
| `AppWalletTransaction` / `app_wallet_transactions` | AppUser、可选 PaymentOrder/Invoice、`operator_tenant_id`、CP、type top_up/charge、Decimal amount、nullable idempotency、admin adjustment。 | user+created/operator tenant/CP indexes；payment_order+type、user+idempotency unique；钱包补缴锁 AppUser/Session/Invoice/ledger。 | nullable idempotency 在 SQL NULL 语义下可重复；type 没 DB CHECK；invoice FK SET NULL 可产生 orphan ledger；operator tenant CASCADE 会影响历史保留；`AppUser.balance` 是另一个 mutable aggregate。 |
| `PaymentWebhookEvent` / `payment_webhook_events` | payment_order、provider、generic provider/event id/type、payload JSON、processed/processed_at；MP route 存最小安全 envelope 后主动查询 Provider。 | `(provider,provider_id,event_id)`、Wompi pair unique；order/processed/provider indexes。 | nullable identity 的 unique 约束不覆盖所有重复；没有 payload hash/attempt/lease/backoff/DLQ/conflict/retention；模型可存 payload，必须继续禁止敏感数据进入。 |
| `AuditLog` / `audit_logs` | nullable tenant、actor/type、action、resource、before/after JSON、IP/user agent、metadata、created_at；Admin OCPP/资产路径已写审计。 | tenant/actor/resource/action/created indexes；无通用 payment-specific FK/operation identity。 | tenant nullable、actor 非 FK、无 immutable/append-only DB enforcement；无 initiator/approver、approval reference、result/error code 和支付事实约束；不能替代 typed financial facts。 |

### 2.2 Schema、迁移、索引和空库差异

- 当前 ORM 在相关财务/会话表上没有 P002 新表、列、索引或迁移；本轮 diff 也没有 Alembic 变更。
- 迁移链为 `001_baseline -> 002 -> ... -> 011_app_wallet_invoice_link`。`001_baseline.py` 的 `upgrade()` 调用 `Base.metadata.create_all()`，不是冻结的显式 baseline DDL；因此“空库可创建”依赖运行时 ORM metadata，不能被视为 P002 typed facts 的迁移方案。
- `011_app_wallet_invoice_link` 对已有 wallet 数据做 invoice link/backfill；已有数据不能假定完整、可回溯或已符合 P002 状态语义。当前没有 recovery/refund/chargeback/funds/reconciliation/risk/approval migration。
- OCPP 的 `MeterValue` unique `(session_id,idempotency_key)` 允许 nullable idempotency 的 legacy rows；`OCPPMessageEvent` 的 nullable unique_id 也不能单独保证所有旧消息唯一。
- `SystemConfig` 使用 `(tenant_id, config_key)` unique；PostgreSQL 对 NULL tenant 的 global rows 允许多个相同 key，不能直接作为唯一的 global rail control。

### 2.3 D1 查询与租户隔离

当前 App charging D1 `_has_global_unpaid_charging_bill`：

1. 先按 AppUser ownership 查询跨 operator tenant 的 completed/unpaid `ChargingSession`；ownership 来源为 `app_user_id`、用户绑定 `user_id` 或 APP idTag，不信任客户端 tenant。
2. 再按 session 逐个检查 positive `Invoice.status == pending`，以及 completed/unpaid session 是否缺少 paid Invoice。
3. 该谓词没有 Refund/Chargeback、funds hold/release unknown、Provider reversal、reconciliation mismatch、duplicate approved 或 typed allocation 概念；`AppUser.has_unpaid_charges` 不是 authority。
4. 该查询存在按 session 的额外 Invoice 查询，属于 N+1 型 start-preflight 读热点；当前没有对所有 D1 blocking facts 的单一索引/谓词。

Operator financial/asset rows 普遍带 tenant_id；普通 DB engine 在 transaction begin 设置 `SET LOCAL app.tenant_id`，但多个 App/Admin/payment 路径使用 `SuperSessionLocal`，因此不能依赖数据库 RLS 自动完成隔离。`PaymentOrder` 没有 tenant_id，tenant/merchant 主要在 `metadata` snapshot 中，reconcile 通过 Invoice tenant 和 metadata 校验；这是跨租户误绑的结构性风险。Admin payment 路由当前为 platform superadmin-only，不能视为 P002 的 tenant-scoped RBAC/双控设计。AppUser 本身是平台级身份，D1 跨运营租户聚合是产品事实，但 Admin 资源查询必须另行从 Invoice/Session/site 推导 tenant。

### 2.4 事务、锁和并发窗口

- Billing：锁 session、AppUser、Invoice、PaymentOrder、Wallet ledger；钱包扣款与 Payment/Invoice 状态在同一 DB transaction。Invoice session unique 是保护线，但无 DB immutable/one-completed-payment 约束。
- Session：Start/Stop/active lookup/MeterValues 对 ChargingSession 和 EVSE/EVSEStatus 使用 `FOR UPDATE`；EVSEStatus upsert 查询没有始终先锁，可能遇到并发 insert/unique conflict。
- MeterValues：Redis Lua 先做 per-value dedupe、latest projection 和 60 秒 persistence gate；Redis 不可用时退回把 prepared values 全部写入 PostgreSQL，形成写放大。
- Payment create/reconcile：`PaymentReconciliationService` 和 current MP create flow 在 Provider HTTP call 前后存在本地 row 与外部 payment 的不一致窗口；Webhook/redirect/status poll 共享 reconcile 但 webhook 去重前仍可能主动查 Provider。没有 operation-level capture/void/refund attempt lease。
- Refund：当前按 PaymentOrder row lock 串行，Provider 累计 refund facts 与本地 metadata summary 比较；没有 RefundAttempt/Chargeback/Funds typed facts。
- Remote OCPP：Admin control 先把幂等命令写 Outbox+AuditLog；跨节点使用 Redis Stream consumer group、pending claim、最多 5 次失败后 dead-letter。App charging `/start` 有 30 秒内存 coalescing，不能作为跨实例 durable command idempotency；设备 `Accepted` 仍不等于 StartTransaction。

### 2.5 写热点、Redis/队列/Webhook/OCPP/Payment

| 热点 | 当前写路径 | 静态写入/容量含义 | 证据/风险 |
|---|---|---|---|
| Heartbeat | `ChargePointService.record_heartbeat` 按 CP/EVSE 更新 `EVSEStatus.last_seen`；默认 persist interval 60 秒；不是 Redis-only。 | 近似上界为 `eligible EVSE / 60s` DB update 级别，实际取决于 last_seen cutoff、CP/EVSE 数量和连接分布。 | 没有本轮 live count 或吞吐测量；必须标 `unmeasured`，不能沿用“heartbeat 只在 Redis”叙述。 |
| MeterValues | OCPP handler 调 `MeterTelemetryService` Redis Lua；healthy Redis 时每 session/value 只按 persistence gate 采样 PostgreSQL，latest/dedupe TTL 默认 86400 秒；Redis failure 时 fallback 写所有 prepared rows。 | 健康路径约 `active sessions * 1/60s` 的持久化 gate 级别，fallback 接近 inbound MeterValues item rate。 | Redis 是 realtime/dedupe accelerator，不是 financial authority；fallback 是容量风险，需压测但本轮禁止压测。 |
| Status/Start/Stop OCPP | StatusNotification 更新 EVSEStatus/DeviceEvent/alerts；Start 创建 Session/Order/PricingSnapshot/Outbox；Stop 更新 Session/EVSEStatus/Outbox。非 Heartbeat/MeterValues 的 OCPP message 有 dedupe event。 | DB 写入与设备事件突发成正比，Start/Stop 是事务热点；MessageEvent unique/index 可成长。 | OCPP facts 和 financial facts 分属 owner；消息 response/命令 acceptance 不能直接改 P002 financial terminal state。 |
| Webhook | MP webhook 验签、按 data.id 主动查询、按 provider/provider_id/event_id 去重、写安全 envelope、调用 reconcile。 | 每次回调至少包含 DB read/write + Provider API read；没有 queue/lease/retry/DLQ，provider burst 直接压 API/DB pool。 | duplicate replay 仍可能在 dedupe 前触发主动 query；payload conflict 只在当前事件模型层面处理。 |
| Payment/status | Hosted checkout token 在 Redis；PaymentOrder/Invoice/Session 在 PostgreSQL；Provider create/status synchronous。 | 当前 DB pool default 10 + 20 overflow per engine；Provider latency 占用 request/transaction orchestration，但无法据此推出 throughput。 | 没有 Provider operation queue/worker/attempt fact；external side effect 与 local commit 需后续架构裁决。 |
| Refund/reconciliation | Refund 在 PaymentOrder lock 下调用 Provider、写 metadata summary；reconcile 由 webhook/status/admin 入口触发。 | Provider/API/DB 调用按重试与人工 replay 次数增长；无 bounded queue lag/attempt metrics。 | metadata summary 不能承载可查询、可审计、可并发的 P002 refund/dispute ledger。 |
| Remote OCPP route | Redis Stream `ocpp:route`, maxlen 100000 approximate；consumer group XAUTOCLAIM idle 30s，batch 20，失败最多 5 次后 `ocpp:route:dead-letter`；response key TTL约 timeout+1s。 | 是跨节点命令消息容量预算，不是财务事实；maxlen/dead-letter/attempt key retention 未纳入财务对账。 | route message may retry/handoff; command idempotency and device facts still need durable domain owner。 |

静态配置基线：DB pool size 10、max overflow 20、recycle 3600s；heartbeat/meter persistence 60s；meter realtime/dedupe TTL 86400s；OCPP message timeout 5s；checkout session TTL 900s；`PAYMENT_RAILS_ENABLED` 默认 false。以上是配置/公式，不是实测 p95/p99、连接池利用率、锁等待、队列 lag、表行数或可承诺 TPS。生产数据量、数据库健康和真实 sandbox response 本轮均为 `unverified/unmeasured`，不得用估算代替负责人容量批准。

### 2.6 脏数据和兼容性清单

- **账单/支付：** Invoice status/Payment status 依赖应用字符串；PaymentOrder status CHECK 不能表达 P002 provider states；PaymentOrder 无 tenant FK；Payment transaction/payment allocation 没有一一对应的数据库事实。
- **退款/争议：** 当前 refund summary 在 JSON metadata，不能证明逐次 attempt、累计资金、chargeback lifecycle 或 funds release；没有 Chargeback 表/状态。
- **Webhook：** provider/event identity 与 payload 允许 nullable/不完整；没有 payload hash、delivery attempt、lease、retention 和 conflict case。
- **钱包：** nullable idempotency、独立 balance、SET NULL invoice link 和 tenant cascade 可能产生重复、漂移、orphan 或历史丢失风险。
- **会话/采样：** nullable MeterValue idempotency、OCPP unique_id legacy NULL、session/payment_status 无 DB check；Redis fallback 可能制造高写量和历史重复，需要 high-water mark/样本规则。
- **意图/配置：** `Order.pre_authorization` 和 `PaymentOrder.metadata` 是 JSON mutable storage；global `SystemConfig` NULL tenant uniqueness 不足；均不能升级为 P002 authority。

空库/已有数据/混合版本结论：空库必须执行完整 Alembic 链且不能依赖 runtime `create_all` 作为未来 P002 migration；已有数据只能从可验证 Invoice/Payment/PaymentOrder/Webhook/OCPP facts 做 additive、幂等、可校验 baseline；缺少退款/拒付/资金释放/风险/approval 证据的历史保留 `unknown/legacy`；未完成 backfill/checksum/tenant reconciliation 前禁止 P002 entry；回滚只能关闭新入口并保留既有 P001/OCPP/financial facts，不 drop、不反向改写、不自动退款。

## 3. BE-204：Mercado Pago Colombia sandbox feasibility matrix

### 3.1 官方候选资料

- [Reserve, capture and cancel](https://www.mercadopago.com.co/developers/en/docs/checkout-api-orders/payment-management/reserve-capture-cancel)：Orders/manual capture 候选流程、reserve/capture/cancel、等待捕获和示例幂等 header。
- [Orders 3DS 2.0](https://www.mercadopago.com.co/developers/en/docs/checkout-api-orders/payment-management/integrate-3ds)：challenge/no-challenge、`action_required`/pending challenge 和恢复边界候选资料。
- [Transaction status](https://www.mercadopago.com.co/developers/en/docs/checkout-api-orders/payment-management/status/transaction-status)：候选状态包括 waiting capture、pending challenge、processing、captured/accredited、partial refund、charged back、expired/refunded 等。
- [Saved cards](https://www.mercadopago.com.co/developers/en/docs/checkout-api-orders/saved-cards)：saved card/customer/card token 与再次采集 CVV 的候选流程。
- [Cards](https://www.mercadopago.com.co/developers/en/docs/checkout-api-orders/payment-integration/cards)：credit/debit card 与 Orders/payment integration 候选资料；不能推断 prepaid/manual capture 兼容。
- [Chargebacks](https://www.mercadopago.com.co/developers/en/docs/checkout-api-orders/chargebacks)：争议通知、处理及资金 hold/扣回候选语义。

### 3.2 可复现 sandbox matrix

`Evidence` 统一为本轮 `unverified`：没有当前 Colombia merchant 的 sandbox token/credential，因此没有 request/response、Provider ID、Webhook/status replay 或资金结果可供验证。

| 能力 | 官方 candidate signal | 当前集成观察 | 可复现 sandbox 试验与通过证据 | 当前结论 |
|---|---|---|---|---|
| authorize / reserve | Orders/manual flow 候选支持 reserve，可能进入 waiting-capture/action-required。 | `PaymentProvider`/`MercadoPagoProvider` 只有 automatic Payments create/status/refund；`PaymentOrder.approved` 当前触发 P001 final settlement。 | 用当前 merchant 创建 manual Order；记录 COP/currency/card/merchant、idempotency、order/payment id；主动 GET + webhook replay，确认 reserve fact 和资金状态。 | `unverified`; 当前 adapter `unsupported-current-integration`；不能实现/宣称授权。 |
| capture | 官方候选 capture，文档示例有 manual capture 语义和捕获期限。 | 无 capture protocol/method/operation fact。 | 对同一 reserve 做 equal capture、重复 capture、超时 capture；保存 status sequence、captured amount、fees/settlement/资金 reference。 | `unverified`; 未获批前禁止把 approved 当 captured。 |
| void / cancel | 官方候选 cancel reserve。 | `voided` 只是 PaymentOrder 旧状态；无 provider void/cancel method。 | RemoteStart rejected、无 StartTransaction、用户取消、设备离线、3DS timeout、expired 后分别 cancel；重复 cancel + late webhook/status。 | `unverified`; unknown/late result 保持阻断。 |
| partial capture | 当前官方资料在本证据范围内明确 total capture 候选；没有当前商户 partial/incremental 证据。 | Invoice 在 StopTransaction 后按实际 MeterValues 产生；无 amount adjustment。 | reserve COP A，测试 final A/低于 A/高于 A/追加授权；记录 capture/refund/release/fee，不能用“全额 capture 后退款”替代 partial capture 证据。 | `unverified`，且是 A 的关键阻塞。 |
| final capture / final amount | reserve/capture 候选以订单金额为输入。 | P001 Invoice 可能在设备结束后才确定；没有 reserve-to-final mapping。 | equal/lower/higher final Invoice、COP rounding/service fee、late StopTransaction、capture deadline；证明差额 release 或安全转 manual review。 | `unverified`; 不能宣称满足 P001 A1。 |
| 3DS challenge/no-challenge | 官方 Orders 3DS 候选支持 challenge/no-challenge 与 action-required/pending challenge；challenge 有时间/恢复边界。 | Hosted page/adapter 当前只处理 token/next-action 的现有 Payments flow；没有 Orders manual 端到端证据。 | new/saved card × credit/debit/prepaid × challenge/no-challenge；重放 return/webhook/status；超时、取消、capture 前后责任/状态。 | `unverified`; 官方文档不等于当前 flow 通过。 |
| new card + CVV | Hosted Secure Fields/token 是当前 P001 boundary。 | 当前 checkout 只存加密一次性 token；不进 DB/log；provider hints 受限。 | 当前 Colombia merchant new-card token 创建 reserve/order；确认 CVV/3DS token 与 manual Orders 的兼容、重试和一次性消费。 | `unverified`; 不得使用真实 PAN/CVV。 |
| saved card + CVV | 官方 saved card 候选要求 customer/card/token 且再次采集 CVV。 | 当前 saved-card 是 Customers/Cards + Payments create；`AppUserPaymentMethod` 无 tenant/merchant unique scope；manual Orders 未接入。 | saved card customer/card id + fresh CVV token；重复 confirm、card deleted/updated、merchant mismatch、3DS；保存非敏感 reference 与状态序列。 | `unverified`; 不能假设复用 P001 saved-card。 |
| credit card | 官方 cards/Orders candidate 资料涉及 credit card。 | codec 支持 `credit_card` projection；当前 adapter automatic Payments only。 | credit test card reserve/capture/cancel/partial/final/refund/3DS 全序列。 | `unverified`。 |
| debit card | 官方 cards candidate 资料涉及 debit card。 | codec 支持 `debit_card` projection；manual Orders compatibility unknown。 | debit test card同上，额外记录 issuer/3DS/资金释放差异。 | `unverified`。 |
| prepaid card | 本轮官方 candidate 资料没有足以证明 manual reserve/capture/3DS 的当前商户支持。 | codec 有 `prepaid_card` projection，但不代表 Provider capability。 | prepaid test card（若 sandbox 提供）完整执行 reserve/capture/cancel/refund/3DS；否则取得 Provider 书面不支持/限制。 | `unverified`；不能从 codec 推断支持。 |
| webhook / active query | 当前 route 验签后主动 GET Provider，再进入 shared reconcile；官方产品页面提供状态语义候选。 | `PaymentWebhookEvent` 去重/processed；无 delivery attempt/lease/retry/DLQ。 | 发送/重放/乱序/重复 webhook；断开主动查询；同 identity 不同 payload；记录签名、query、event hash、reconcile result 和 retry。 | 当前 webhook+query path `observed`；P002 manual-flow `unverified`。 |
| operation idempotency | 官方示例候选使用 `X-Idempotency-Key`。 | 现有 local PaymentOrder idempotency 和 refund key；没有 authorize/capture/void operation key/facts。 | 每个 operation 独立 key：same request replay、same key different fingerprint、timeout after provider success、late webhook；证明只产生一个 external side effect/本地事实。 | `unverified`; 不能复用一个 PaymentOrder key 覆盖全部操作。 |
| refund | 当前 Payments adapter 有 get refund facts/create refund；P002 Orders lifecycle 未验证。 | Refund service 只在 PaymentOrder.metadata 写 summary；无 RefundAttempt。 | full/partial/refund replay、cumulative provider facts、amount mismatch、timeout/unknown、Invoice/Wallet effect；验证退款不替代 chargeback。 | current automatic refund path `observed`; P002 manual/typed refund `unverified`。 |
| chargeback / dispute / funds hold-release | 官方 chargeback candidate 有 notification/processing/hold/扣回语义。 | 无 ChargebackCase/FundsHold/Release/reconciliation facts；现有 D1 不识别。 | dispute notification、in_process、lost/won/reimbursed、资金扣回/释放、重复/乱序/late event、D1 re-block；保存 Provider reference/资金事实。 | `unverified`; 必须独立建模，不能用 refund 状态替代。 |

### 3.3 复现脚本的安全边界

未来仅在负责人提供并确认 sandbox merchant/account、非生产 base URL、可撤销测试方式和脱敏存储位置后执行。每个测试 case 至少保存：case id、产品/API family（当前 Payments 或候选 Orders）、merchant reference（不含 secret）、operation key 的 hash、Provider ID、金额/currency/card type、3DS path、Webhook/status 时间序列、最终资金/退款/争议状态和 replay checksum。禁止保存 PAN、CVV、card token、access token、完整 Provider payload 或生产凭证。

没有上述条件，本轮 matrix 保持 `unverified`；不能提交“集成通过”、不能选择方案 A、不能更新 frozen contract，也不能解除 P002 C3 implementation block。

## 4. 下一步门禁

当前最小下一步是继续建模并完成剩余产品决策，而不是提交实现复审：

1. 负责人已选择 D-203 方案 1；仍需为方案 1提供 sandbox/书面证据责任人，并保持方案 2 Provider 研究为非约束性候选。
2. 负责人仍需为 D-204 给出单会话、AppUser 日、租户/站点日、平台日 COP/Wh/time 上限、unknown buffer、最大损失和 RemoteStop SLA。
3. 在剩余产品决定和证据齐全后，再由 architecture-agent 复审 typed facts、D1、租户/RBAC、迁移/回滚和容量预算；当前不能提交“批准实现”的架构复审。
