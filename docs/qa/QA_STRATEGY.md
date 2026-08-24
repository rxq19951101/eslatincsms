# QA Strategy

## 1. 目标

QA 同时验证需求正确、数据正确、架构符合和回归安全。测试通过但违反模块边界、租户、权限、ADR 或 frozen contract，结论仍为 failed/blocked。

## 2. 固定角色与 scope

统一使用 `qa-agent`。每次启动只选择一个明确 scope：

- backend：API、service、DB、Redis/队列、Webhook、OCPP、审计和脏数据。
- frontend：App/Admin 构建、类型、导航、契约映射、状态恢复、i18n、可访问性和相邻旅程。
- cross-module：只在计划明确且不等同完整 E2E 时使用。

实现 Agent 不得兼任 QA；QA 不修改产品代码使测试通过。

## 3. Entry gate

- 产品/技术架构和相关 ADR 可读。
- C2/C3 有批准的 Change 与实现计划。
- frozen contract 和实现交接存在。
- 工作区指纹、目标环境和测试数据范围可确认。

## 4. Backend QA

- 权限、audience、租户隔离和跨租户负例。
- 状态机、幂等、并发、重试、乱序和故障恢复。
- PostgreSQL 重复/孤儿/跨租户引用/非法状态/金额不一致。
- Redis 丢失、过期和重复事件不破坏持久事实。
- Webhook 主动反查、金额/币种/商户校验和重放保护。
- OCPP 在线、启动/停止、重连、重复消息和采样写入。
- 审计和敏感日志清洗。

## 5. Frontend QA

- TypeScript、构建、相关和广泛回归。
- auth、主导航、Deep Link、恢复和 App 生命周期。
- API 请求/响应/错误映射，不使用客户端伪事实。
- loading/empty/offline/retry/stale/resumed/terminal 状态。
- 三语言、窄屏、键盘、焦点、screen reader 和不只依赖颜色。
- 敏感数据不进入日志、storage 或非托管表单。
- 改共享模块时回归 App/Admin 相邻流程。

## 6. Architecture compliance

每份显著变更 QA 报告回答：

- 是否符合 PRODUCT_ARCHITECTURE 和 TECH_ARCHITECTURE？
- owner/依赖是否在边界内？
- 是否引入未记录跨域依赖或循环？
- 是否遵守 ADR、contract、权限、tenant 和兼容性？
- 文档是否仍描述当前系统？

## 7. E2E gate

相关 backend/frontend QA 通过后由 e2e-agent 执行完整用户旅程，核对 UI、API、数据库、Provider/设备异步事实和用户恢复体验。不能只用接口测试代替用户流程。

### 7.0 Sandbox 执行授权

`qa-agent`/`e2e-agent` 对已批准的本地或测试 Sandbox 具有持续执行授权，不需要每次重新取得产品负责人批准即可登录官方测试账号、输入官方测试卡、提交 Sandbox 支付、验证 Webhook 和核对测试数据库。该授权不包含生产环境、生产凭证、真实银行卡、真实退款或任何真实资金操作；环境不一致时必须阻塞并人工询问。

### 7.1 支付充电强制双路径

凡是涉及“支付后充电”或“充电结算”的交互性测试，必须分别执行并分别出具证据，不能用一条链路代表另一条链路：

1. **直接银行卡充电（`charging_direct`）**
   - 用户使用信用卡完成直接充电资格/支付流程，不先充值钱包。
   - 由模拟充电桩实际执行启动、MeterValues、停止和最终结算。
   - 必须核对：充电会话、Invoice、PaymentOrder、Provider 支付、Webhook/对账状态一致；最终扣款等于服务端 Invoice 金额；不产生钱包充值流水。
2. **先充值再钱包充电（`wallet_top_up` → `wallet`）**
   - 用户先用信用卡完成钱包充值，并等待 Provider/Webhook 形成批准事实。
   - 再使用已增加的钱包余额启动模拟充电，执行 MeterValues、停止和最终钱包结算。
   - 必须核对：充值只增加一次余额；充电只扣除最终 Invoice 金额；不重复创建 Provider 充电扣款；钱包、Invoice、Session、PaymentOrder 和 Webhook 状态一致。

两条路径必须使用独立的测试前置状态或可核验的状态清理，并记录 `user_id`、`checkout_session_id`、`payment_order_id`、Provider payment ID、充电会话 ID、充电桩/枪口、Invoice ID 和 Webhook 事件 ID。只完成一条路径、只使用数据库插入模拟支付结果、或只验证 HTTP 200，均不得判定支付充电 E2E 通过。任一路径失败或证据缺失，整体结论为 `failed` 或 `blocked`。

## 8. Verdict

- `passed`：规定范围有充分证据且无阻塞缺陷。
- `failed`：确认产品/架构缺陷。
- `blocked`：关键环境、依赖、配置或前置 QA 不满足，不能形成结论。

报告必须记录精确命令、结果、环境、未测面和残余风险。未知状态不得判 pass。
