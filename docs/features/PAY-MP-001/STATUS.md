---
id: PAY-MP-001
status: p0-fe-p0-1-done-review-required
product: approved
contract: frozen
backend_design: approved-p0
backend_implementation: be-p0-2-done-review-required
backend_qa: blocked-current-recheck
frontend_design: approved-p0
frontend_implementation: fe-p0-1-done-review-required
frontend_qa: blocked
e2e_qa: not-started
human_review: not-started
production_launch_readiness: draft-owner-review
---

# PAY-MP-001 状态

## 接口治理（CHG-20260817-PAY-API-GOVERNANCE）

- App 当前唯一支付创建/确认/查询入口为 Checkout Session；Provider-specific Webhook 使用 `/api/v1/app/payments/webhooks/mercadopago`，本地测试使用 `/api/v1/app/payments/webhooks/sim`。
- 历史 Wompi、旧 Mercado Pago create/status/webhook 路由不属于当前 API；本次不做数据库迁移或历史支付数据处理。
- 未来 Provider 必须复用 Checkout Session，并在服务端 Provider Registry/Adapter 边界接入。

## QA continuation checkpoint（2026-08-18 UTC）

- 后端 QA 已按负责人“继续完善”要求恢复本地/测试范围复测；当前不是 `paused-by-owner`，但仍是 `blocked`，没有宣称 PASS。
- CSMS 迁移以外完整回归：`558 passed, 5 skipped, 20 warnings`；定价五类 P0 门禁：`9 passed`；定价/计费/支付意图联合回归：`28 passed`。
- 本地测试 Compose 与 API 健康检查保持通过；App/Admin 自动化此前分别为 `188 passed` / `186 passed`；charger-sim 测试为 `74 passed`。
- Mercado Pago Sandbox 直接 Provider create/query 已观察到：Card Token `201`；支付 `201`、Provider payment ID 存在、`approved/accredited`、`2001 COP`；主动查询 `200` 且状态和金额一致。该证据不等于本地 Checkout Session、签名 Webhook、PaymentOrder/Invoice 结算或重复通知闭环。
- PRC-MODE-001 五类门禁已完成并更新为 `passed`；本次修复的站点定价 UUID 写入缺陷无数据库迁移影响。
- 仍保持 blocked：真实订单关联 Webhook/结算/对账/重复通知、3DS/退款 mutation、PostgreSQL/Redis 业务并发、生产 DNS/TLS/备份/告警/回滚、D-204/BE-205 真实运行时与容量、前端独立 QA、正式 E2E 和人工 release review。

## 当前阶段

- 当前实现状态：`FE-P0-1` 前端实现已完成并交接，等待根主线程只读复核。
- 当前任务：`FE-P0-1` 为 `done-review-required`，已完成 prepaid/null 投影、单用途 Checkout、独立添加卡、saved-card CVV 入口及 404/409/503/网络未知恢复对齐。
- 文件所有者：FE-P0-1 App 实现文件与测试已交接；Admin、后端业务代码、数据库、迁移和共享契约未进入本任务所有权。
- 当前非阻塞延期：项目负责人确认欠费列表、银行卡/钱包欠费补缴 UI 和欠费恢复页属于后续边缘场景，标记为 `deferred-by-owner`。本期 App 遇到 `UNPAID_CHARGES` 只显示安全提示并阻止继续充电，不依赖未冻结的欠费列表字段。
- 发布门禁：后端 QA 已恢复本地/测试复测，但独立报告最新结论仍为 `blocked`，不存在 PASS；独立前端 QA 结论为 `blocked`，仍缺真实后端、Provider、设备、3DS 和可访问性证据；E2E 仍未正式闭环。前后端 P0 设计均已批准，FE-4B 仍为非阻塞延期。

## 生产上线产品准备（2026-08-12）

- 已建立 [生产上线最低要求](./product/PRODUCTION_LAUNCH_MINIMUM.md) 和 [充电平台支付对标](./product/COMPETITOR_BENCHMARK.md)。
- 当前预金丝雀判定：`NO-GO`。后端 QA 最新复测仍为 `blocked`；前端 QA 为 `blocked`；E2E 未正式闭环。真实订单关联 Webhook/结算/重复通知、3DS/退款、支持与事故演练、法律/隐私/财税/商业签字和人工审查也尚未形成放行证据。
- 当前单笔生产金丝雀：未授权。生产 Payment ID 与 Mercado Pago 生产质量评估只能在预金丝雀全部通过并取得一次性书面批准后形成，不作为预金丝雀前置证据。
- 当前受控试点扩展判定：`NO-GO`。必须先在支付轨关闭状态下完成唯一金丝雀 Payment ID 的三方对账和 Mercado Pago 质量评估，再另行审批试点范围。
- 当前公开发布判定：`NO-GO`。除共同门禁外，无预授权 A1 的资金敞口方案和 D-008 自助欠费恢复仍需负责人决定。
- A1/B1/C1/D1、D-008、D-017 均保持 `approved` 且未被本次文档任务改写。
- D-020 至 D-026 均保持 `proposed`：预金丝雀/单笔金丝雀/受控试点顺序与限额、公开发布资金风险、D-008 发布边界、访客支付、支持承诺和 C1 商业责任。
- `PAYMENT_RAILS_ENABLED` 默认及任何未获批窗口外必须为 `false`；只有预金丝雀 GO 且具体单笔金丝雀获得书面批准后，授权操作人才能在测试人即将操作前临时启用，并在取得唯一 Payment ID、触发停止条件或窗口结束后立即关闭。本文不授权部署或生产配置变更。
- 本次仅更新产品文档和发布准备引用；没有修改契约、实现、测试、迁移、密钥、部署或生产状态。

## P0 增量状态（2026-08-12）

- 产品方案：`approved`。
- 共享 API 契约：已重新 `frozen`；`payment_type` 明确由 `credit_card | debit_card` 扩展为 `credit_card | debit_card | prepaid_card`，旧投影允许 `null`；仅 `purpose=save_card` 可令 `save_card=true`，其他 purpose 必须为 `false`。
- 数据库与迁移：无变化；本 P0 禁止新增迁移或历史数据导入。
- 后端设计/实现：P0 架构评估和技术设计已 `approved`；`BE-P0-1` 已由根主线程只读复核，97 项开发回归通过；`BE-P0-2` 为 `done-review-required`，最终定向与相邻支付回归 108 项通过，详见 `backend/BE-P0-2_HANDOFF.md`。
- 前端设计/实现：P0 架构评估与技术设计已 `approved`，`FE-P0-1` 已 `done-review-required`；App 已移除 `charging_direct` 保存卡选择，仅独立添加银行卡入口创建 `save_card=true` Checkout。最终 TypeScript 通过，12 个定向/相邻套件 65 项通过，详见 `frontend/FE-P0-1_HANDOFF.md`。
- QA：独立前端 QA 自动化/构建/静态审查已运行但结论为 `blocked`；后端 QA 本地全量回归通过但外部与运行时证据不足，结论为 `blocked`；E2E 尚未取得正式闭环。三者均无可用于发布的完整 PASS，不能启用生产支付轨。

## P0 顺序

1. 后端已按重新冻结的独立 `save_card` 决策更新并批准 P0 技术设计。
2. `BE-P0-1`（`done-reviewed`）：卡类型契约和 Provider 投影扩展已完成并经根主线程只读复核，支持 `prepaid_card`，未知类型和客户端 saved-card 覆盖均失败关闭。
3. `BE-P0-2`（`done-review-required`）：首次新卡动态证件能力、BIN 自动卡识别、全西语紧凑托管页、saved-card 仅 CVV、单用途 Token 校验和 404/409/503 安全状态页已实现；等待根主线程只读复核。
4. 后端 QA 恢复后独立验收；暂停期间只保留开发测试事实，不宣称 QA 通过。
5. 前端已按重新冻结的互斥流程完成架构评估并批准 P0 技术设计。
6. `FE-P0-1`（`done-review-required`）：App 支付方式 prepaid/null 投影、移除单次充电保存卡选择、独立添加卡、saved-card CVV 入口、404/409/503/网络未知恢复与三语言文案已对齐；等待只读复核。独立 frontend QA 已执行且为 `blocked`，缺失证据须在后续 QA 中关闭。
7. 后端 QA 恢复并取得 PASS、前端 QA 关闭 blocker 并取得 PASS 后，才可开始 E2E；E2E 通过且其余预金丝雀门禁完成前保持 `PAYMENT_RAILS_ENABLED=false`。

## 最近架构审查

- BE-P0-2：实现完成。新卡动态调用 Mercado Pago 证件类型和 BIN 能力，严格应用 Provider 返回的数据类型/长度并失败关闭；卡品牌、issuer 和三类卡只读展示；保存卡页仅渲染服务端投影及 CVV；GET 404/409/503 返回无卡表单的西语状态页；创建时冻结 save-card 单用途矩阵。最终定向与相邻支付回归 108 passed，new-card/saved-card 内联脚本均通过 Node 语法检查；真实 Mercado Pago sandbox、浏览器视觉/可访问性和 Redis/PostgreSQL 证据仍缺失。当前独立后端 QA 报告为 `blocked`，没有 PASS。
- BE-P0-1：实现完成，三类卡已贯通 codec、confirm、Provider Card、本地支付方式投影与 reconciliation hints；旧纯 brand/未知 v1 类型继续读取为 `payment_type=null`，新写入及支付使用缺失、未知、冲突类型时失败关闭，saved-card 客户端卡事实覆盖被拒绝。开发回归 97 passed；真实 Mercado Pago sandbox 和 Redis/PostgreSQL 证据仍缺失。当前独立后端 QA 报告为 `blocked`，没有 PASS。
- BE-2B：通过。Checkout API/签名 URL 与冻结契约一致；`charging_direct` 仅允许 paid；认证错误结构及 ChargePoint-Site、Invoice-Session 租户一致性已失败关闭；无数据库或迁移变化。
- BE-2C：通过。托管 CardForm/Secure Fields、签名页面、confirm、Redis 加密 Token、并发单次确认和 303 Deep Link 已实现；无数据库或迁移变化。真实 Mercado Pago sandbox 和 3DS 证据仍缺失；当前独立后端 QA 报告为 `blocked`，没有 PASS。
- BE-3：通过。Customers/Cards、保存卡、默认卡/删除、旧接口兼容、用户隔离和 Token 单次消费已实现；无数据库模型或迁移变化。定向回归 45 passed；真实 Provider sandbox 和 3DS 证据仍缺失；当前独立后端 QA 报告为 `blocked`，没有 PASS。
- BE-4：实现完成。Charging Payment Intent 使用 `Order.pre_authorization` 版本化保存，`charging/start` 在服务端锁定并校验 QR/用户/租户/桩/connector/有效期后才发送 RemoteStart；RemoteStart 失败回到 `ready`，StartTransaction 单次绑定到实际 Session；无数据库模型或迁移变化。定向 BE-4 测试 7 passed；OCPP 组合回归 23 passed、1 个既有 fixture 失败，详见 `backend/BE-4_HANDOFF.md`。
- BE-4：通过。另补强 checkout session 投影失败后的 Intent 恢复幂等，按 checkout_session_id 及用户/桩/租户/connector 归属找回已有 Order；架构复核定向 7 passed，恢复与组合回归详见 `backend/BE-4_HANDOFF.md`。无数据库模型或迁移变化。
- BE-5：通过。wallet/direct_card/free 三分支以 Invoice 为金额权威；余额不足不扣款、不截断、不标记 paid；direct_card 不写钱包；free 仅 0 COP 审计 Payment；同 Session 唯一 Invoice。根线程复跑结算/定价 8 passed；真实 PostgreSQL 并发及后端 QA 仍暂停。
- BE-6：通过。统一 direct-card 扣款/对账、Provider 状态投影、Webhook 验签与主动反查、金额/币种/商户/租户归属校验、乱序保护、重复 approved 异常标记和全局 D1 事实门禁已实现；根线程复跑 BE-6 定向 10 passed；真实 Provider/3DS、PostgreSQL 并发和后端 QA 仍暂停。
- BE-7：通过。欠费列表/补缴改用 Invoice 权威金额，银行卡补缴复用统一 reconcile，退款按 Provider 累计事实与版本化 metadata 串行累计，支持部分/全额退款和钱包余额保护；修正了保存卡 provider hints 传递。根线程复跑 BE-7 定向 5 passed；真实 Provider refund、PostgreSQL 并发和后端 QA 仍暂停。
- 前端 P0 设计：通过。现有 App 架构和冻结契约可支撑 FE-P0-1；设计已明确 canonical `credit_card | debit_card | prepaid_card | null` 映射、`charging_direct save_card=false`、独立 `save_card=true`、saved-card CVV、404/expired 清理、409 只读回查、503/网络未知保留引用及三语言/相邻回归。FE-4B 继续 `deferred-by-owner`；Admin 不在实现范围内。独立 frontend QA 已执行 Admin 构建和既有支付页面 smoke，整体仍为 `blocked`。
- FE-P0-1：实现完成并等待只读复核。canonical 类型与三语言集中映射已覆盖 credit/debit/prepaid/null/非法 runtime 值；App 充电保存卡 Switch、props/state 和 `save_card=true` 路径已移除，独立 AddPayment 继续固定 `save_card=true`。Checkout coordinator 对 404/expired 清理、409 单次只读复查、503/网络未知保留引用，并为 Deep Link、前台、轮询和手动刷新共享 GET in-flight；PaymentResult 与 ChargingProcess 已显示安全恢复状态且不会自动启动充电。最终 `npx tsc --noEmit` 通过，12 个套件 65 passed。后续独立 frontend QA 已运行自动化、构建和静态审查并给出 `blocked`；真实后端、Provider、设备、3DS 和可访问性证据仍缺失。
- FE-1：完成。支付方式 canonical projection、添加卡托管 Checkout、默认卡/删除及加载/空/错误状态已实现；主线程复跑相关测试 7 passed，TypeScript 通过。
- FE-2：完成。Hosted Checkout、Deep Link 清理、3DS allowlist、支付状态轮询和 App 恢复已实现；主线程复跑相关测试 16 passed，TypeScript 通过。
- FE-3：历史实现完成。wallet/direct_card/free 启动与结算、Payment Intent、十进制金额及处理中/3DS/未支付状态已实现；其中与重新冻结决策冲突的 `charging_direct` 新卡显式保存选择已由 `FE-P0-1` 移除。此前 37 passed 和 TypeScript 通过仅代表旧实现测试事实，不代表 P0 验收。
- FE-4A：完成。钱包充值统一使用 `wallet_top_up` Hosted Checkout，保存非敏感 Checkout Session 引用，支持恢复/重试并在批准后刷新钱包余额；主线程复跑 6 个相关测试套件、19 passed，TypeScript 通过。
- FE-4B：`deferred-by-owner`。欠费列表、银行卡/钱包欠费补缴 UI 和欠费恢复页后续另立需求；本期不创建 `UnpaidCharge` 前端类型、字段映射或测试 fixture。

## 已确认产品决策

- A1：充电结束后按准确金额直接扣卡。
- B1：EsLatin 托管 Mercado Pago 安全结账页。
- C1：首期 EsLatin 统一收款，并通过商户解析接口为 C2 留扩展边界。
- D1：存在任何欠费时禁止开始下一次充电。
- D-027：付费充电每个会话最低支付 `1,011 COP`；免费定价模式仍为 `0 COP`。该规则已写入用户协议、App 文案、结算技术设计和 API 结算规则；原因是 Sandbox 对 1,010 COP 及以下返回 2072，1,011 COP 起已验证成功。
- P0 卡保存：`charging_direct` 的新卡 Token 只用于当前充电最终扣款且 `save_card=false`；保存卡必须先完成独立 `purpose=save_card` Checkout，后续充电使用已保存卡并重新采集 CVV。

## 连续开发授权

1. 项目负责人已授权 BE-2B、BE-2C、BE-3、BE-4、BE-5、BE-6、BE-7 按编号串行开发，不需要在任务之间等待人工确认。
2. 每项完成后由根主线程执行只读架构审查；未发现契约、安全、数据或架构门禁问题时自动进入下一项。
3. 后端 QA 已恢复本地/测试范围复测；架构审查不等同于 QA 通过，外部 Provider、运行时、E2E 和生产测试缺口必须保留在交接记录中。
4. 任一时刻只运行一个实现 Agent，不并行开发相邻 BE 任务。
5. `PAYMENT_RAILS_ENABLED` 继续保持关闭。
