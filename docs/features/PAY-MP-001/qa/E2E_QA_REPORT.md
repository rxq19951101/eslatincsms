---
id: PAY-MP-001
status: blocked
owner: e2e-qa
---

# 端到端 QA 报告

仅在后端 QA 和前端 QA 均通过后，由 `e2e-agent` 从用户角度执行完整链路、数据事实和体验验证。

## 当前复核（2026-08-18 UTC，重启后）

使用现有测试 Compose 入口重建并重启 CSMS；入口执行既有 `alembic upgrade head`
且未新增迁移文件，容器健康检查和 `/health` 均为 `200`。新建零余额、无历史账单
的本地 AppUser 完成真实 Sandbox `charging_direct`：Checkout `200` → Card
Token `201` → Hosted confirm `303` → RemoteStart/StartTransaction →
MeterValues → StopTransaction → Invoice/PaymentOrder 结算。服务端按批准的
D-027 最低金额创建 `1011.00 COP` Invoice，Provider 返回 `201 approved`，
PaymentOrder/Invoice/Session 均为已支付/完成，Checkout 最终为 `approved`。

Mercado Pago 自动签名 Webhook 随后到达并返回 `200`。此前发现的“结算响应先
标记 approved、同一 Provider payment 的 Webhook 被误判为 duplicate approved
并触发退款”已修复：当前日志为 `Repeated approved provider fact is idempotent`，
数据库未写入 `settlement_exception` 或 `refund_required`。对应独立后端回归
`13 passed`，真实 Sandbox 直付链路已重新通过。

## 支付充电强制验收矩阵

以下两条路径必须分别执行；任何一条未执行、失败或缺少 Provider/设备/数据库证据，PAY-MP-001 不能标记为 `passed`。

| 路径 | 必须经过的用户交互 | 必须核对的最终事实 | 结果 |
|---|---|---|---|
| A. 直接信用卡充电 | 选择信用卡 → `charging_direct` → 启动模拟桩 → MeterValues → 停止充电 | Invoice 准确金额、Provider 支付、PaymentOrder、Webhook、Session 一致；无钱包充值流水 | `passed`（重启后真实 Sandbox，1011 COP） |
| B. 充值后钱包充电 | 信用卡充值 → Provider/Webhook 批准 → 钱包余额增加 → 选择钱包充电 → MeterValues → 停止充电 | 充值只增加一次；钱包只扣最终 Invoice；不产生重复 Provider 充电扣款；Invoice、PaymentOrder、Webhook、Session 一致 | `passed` |

### 证据字段

每条路径至少记录：

- `user_id`
- `checkout_session_id`
- `payment_order_id`
- Provider payment ID
- 充电 `session_id`
- ChargePoint ID / connector ID
- Invoice ID
- Webhook event ID 与处理结果
- 测试前后钱包余额和交易流水计数

单独验证充值成功不等于直接充电成功；单独验证直接充电成功也不等于充值后钱包充电成功。

## 历史 Sandbox 交互 QA（2026-08-18 UTC，保留为历史证据）

### 历史总体结论（不覆盖当前复核）

历史结果为 `passed`。两条用户交互路径均曾执行并形成 Provider、Webhook、设备、Invoice、PaymentOrder 和钱包事实；本节保留原始证据，但不覆盖上方当前复核的旧镜像 blocker。未修改业务代码、未插入支付结果、未执行数据库迁移。

### A. 直接信用卡充电：首次限制与成功重跑

- 测试用户：`AppUser:f397b331-c695-5494-b084-26346257a2a2`
- Checkout：`crkfUQrf2EOH2bCBZABiGPRKcbb6XCUv`
- Payment Intent：`008cade4-c3f5-4749-b068-27ec75679cb6`
- PaymentOrder：`72ef739c-8962-4662-84b7-47564d96341d`
- 充电会话：`a61f1327-ced0-4343-ac1a-6e69388cca28`
- 设备/枪口：`988ff246-8b6f-5e93-9dd2-57a7393bea1b` / `1`
- Invoice：`7f73718f-af3b-4a7d-b27d-c6b49317f788`
- 设备事实：启动 Accepted；MeterValues 写入；停止 Accepted；会话 `completed`。
- 金额事实：Invoice `1,000.00 COP`，能量 `0.108 kWh`，价格 `2,700 COP/kWh`；服务端按最低金额规则计算为 `1,000.00 COP`。
- Provider 事实：请求金额为准确的 `1,000.00 COP`；Mercado Pago Sandbox 返回 HTTP 400、错误码 `2072`（`Invalid value for transaction_amount`）；没有 Provider payment ID，也没有 Webhook 成功事件。
- 资金保护事实：PaymentOrder 为 `error`，Invoice 保持 `pending`，会话为 `unpaid`；该用户没有产生钱包充值流水。没有把 Provider 失败误记为已支付。
- 判定：`blocked`。这是当前 Sandbox 对 1,000 COP 测试金额的 Provider 能力限制；不是前端小数转换或 Vendor 收款路由问题。要验证“直付成功”需要使用金额高于该 Sandbox 限制的隔离测试前置，不能修改产品最低收费或伪造 Provider 成功。

#### 成功重跑证据

- 使用无欠费隔离测试账号 `AppUser:9ebaee50-f9df-5f6d-ac82-cf5eeaae4574` 创建独立 `charging_direct` Checkout：`91ScPFJvqojqJuJ8Xm_p4j3y34gt_nBw`；支付意图：`83f10875-fb7d-480a-9ee2-0dfb792649c9`。
- 临时测试前置：模拟桩功率 `60 kW`，MeterValues 为 `60.0 kW / 400 V / 150 A`；临时电价 `150,000 COP/kWh`。该调整只存在于本轮测试数据库，完成后已恢复。
- 充电会话：`a849eb65-7724-4465-8d2d-5d82675ace96`；事务号 `1283438575`；MeterValues 从 `0` 增至 `594 Wh`；停止响应 `Accepted`。
- Invoice：`4c9dfafe-040c-4c0c-9d31-955ed05db7f2`，准确金额 `89,100.00 COP`，能量 `0.594 kWh`，状态 `paid`。
- PaymentOrder：`b3c535d7-b6d9-4d9b-9896-e251bd34757b`，状态 `approved`，金额 `89,100.00 COP`。
- Provider payment ID：`1327898680`；Webhook：`52b2acce-a033-44ea-bf3e-2e9fddbd3327`，`payment.created`，已处理；Webhook HTTP 200。
- 资金保护事实：该 direct-card 结算没有新增钱包流水，钱包余额保持 `9,000 COP`。
- 判定：`passed`。Provider 扣款金额与服务端 Invoice 完全一致，未使用客户端伪造金额。

### B. 充值后钱包充电

- 测试用户：`AppUser:9ebaee50-f9df-5f6d-ac82-cf5eeaae4574`
- Wallet top-up Checkout：`J6zNjAEdpg3cp40wMivELnKAxoKfcMsA`
- Wallet top-up PaymentOrder：`b7a677b1-5d76-4465-8463-aa0addf6cefd`
- Provider payment ID：`1350490277`
- Webhook：`5bcf38c6-768d-4b13-80c3-6ca3dfae3491`，`payment.created`，已处理；Webhook HTTP 200。
- 钱包事实：充值前 `0 COP`，充值后 `10,000 COP`；充值流水 1 条；没有重复充值。
- 充电会话：`4ac8e864-5635-4bf3-b03d-e623bfbdf53e`
- 设备/枪口：`988ff246-8b6f-5e93-9dd2-57a7393bea1b` / `1`
- Invoice：`37c8bf0d-f45f-48a5-b957-acf152ba97ab`
- 设备事实：Preflight `allowed`；启动 Accepted；MeterValues 写入；停止 Accepted；会话 `completed`。
- 结算事实：Invoice `1,000.00 COP`，能量 `0.036 kWh`，价格 `2,700 COP/kWh`；钱包支付状态 `paid`；钱包余额从 `10,000 COP` 降至 `9,000 COP`；充电流水 1 条；没有为该充电会话创建 Provider 充电扣款订单。
- 判定：`passed`。

### 阻塞与下一步

1. 历史 1,000 COP 失败记录保留；当前生效产品决策 D-027 为付费会话最低 `1,011 COP`，免费模式仍为 `0 COP`。
2. 需要复测 direct-card 时，必须让测试 Compose 加载包含 D-027 的镜像；不得复用旧容器、插入“已支付”结果或用额外 Compose/env 绕过环境治理。
3. 历史两条用户路径证据仍保留；但当前复核发现测试账务脏数据与公网 Tunnel 阻塞，生产发布仍需遵守独立人工 release review 和生产开关门禁。

## 最新后端全量回归与直接充电复核（2026-08-18）

在既有测试 Compose 重建、重启并完成现有入口 `alembic upgrade head` 后，执行了唯一一次全量后端回归：

- 命令：`cd csms && python3 -m pytest -q`
- 结果：`559 passed, 5 skipped, 20 warnings in 143.35s`
- 支付相关回归、Checkout Session、账务结算、Webhook 幂等、模拟器 E2E 和全量后端测试均通过。
- 新建的零余额隔离测试用户完成真实 Sandbox direct-card 充电：结算金额 `1,011 COP`，Provider `approved/accredited`，PaymentOrder/Invoice/Session 均为已支付/已完成，Webhook HTTP `200`。
- 同一 Provider approved Webhook 重复到达时被识别为同一支付事实，不再触发 `duplicate_approved` 或退款；`test_payment_reconciliation_be6.py` 为 `13 passed`。

本证据只关闭本地/测试范围的后端回归与 direct-card 运行链路；生产凭证、DNS/TLS、备份恢复、生产 Redis/Outbox、容量、告警、回滚和人工 release review 仍未通过，生产支付开关必须保持关闭。

## 当前治理预授权后的复核（2026-08-18）

本轮依据 `AGENTS.md` 的 Sandbox QA 预授权执行，不需要再次申请产品批准；目标限定为本地测试 Compose 与 Mercado Pago Sandbox。未创建环境文件或 Compose 文件，未执行迁移，未触碰生产。

### 自动化与运行态证据

- App：`cd app && npm test -- --runInBand` → `43` 个测试套件、`188 passed`。
- Admin：`cd admin && npm test -- --run` → `36` 个测试文件、`186 passed`。
- CSMS：迁移以外完整回归 → `548 passed, 5 skipped`。
- 测试 Compose：`docker compose --env-file .env.test.local -f docker-compose.test.yml config` → `ok`；`ENVIRONMENT=test`、`MERCADOPAGO_ENVIRONMENT=sandbox`、测试支付开关仅在本地测试注入。
- 本地运行态：`http://localhost:8001/health` → HTTP `200`，database/redis 为 `ok`，websocket 为 `configured`；Admin `http://localhost:3002/` → HTTP `200`。
- Webhook 路由：Mercado Pago 和 sim 路径均已注册；GET 返回 `405` 且声明 `Allow: POST`，符合 POST-only 设计。
- Sandbox Provider 只读反查：已有 3 个 Provider payment 均 HTTP `200`、`approved/accredited`；本轮未创建新支付、未伪造支付成功。
- 测试数据库聚合：PaymentOrder `19`；低于 `1,000 COP` 的历史订单 `5`；重复幂等键 `0`；孤儿 Webhook 引用 `0`；Mercado Pago 重复 Provider event `0`；已处理 Mercado Pago Webhook `4`。

### 当前阻塞项

1. **账务脏数据：`blocked`。** 测试库存在 `1` 条 `top_up` 钱包流水，关联 PaymentOrder 状态仍为 `created` 而非 `approved`，金额为 `10,000 COP`。该事实违反“只有 Provider 批准后才能入钱包”的规则；本轮未删除或改写数据，需后续按负责人指示清理或修复来源后复测。
2. **公网 Tunnel：`blocked`。** `https://sandbox-api.eslatin.com.co/health` 当前返回 Cloudflare `530`；本地 API 正常，因此不能据此判定 Provider Webhook 公网链路通过。
3. **浏览器交互复测：`not rerun`。** 当前本地 Expo Web 服务未成功监听 `8081`，因此本轮没有新增浏览器端 Secure Fields/hosted return 证据；历史报告中的两条完整用户路径证据保留，但不能覆盖当前脏数据和 Tunnel 阻塞。

### 本轮结论

`VERDICT: blocked`。自动化回归和本地测试 API 通过，Sandbox Provider 既有支付反查通过；但账务脏数据和公网 Tunnel 仍未闭环，不能签署本轮完整 E2E PASS，也不能据此放开生产支付。
