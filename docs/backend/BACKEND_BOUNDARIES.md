# Backend Boundaries

## 1. 分层

- `api/v1`：身份/权限依赖、请求验证、契约映射和 HTTP 状态；不承载跨领域事务细节。
- `services`：用例编排、事务、状态机、租户和幂等校验。
- `domain`：稳定状态/规则类型，不依赖 FastAPI 或 UI。
- `database`：持久模型、session 与迁移边界；不调用 Provider/UI。
- `ocpp`：协议与连接传输；业务事实通过 service 交接。
- `payment_providers`：外部支付差异、凭证与事实查询；不决定充电/账单规则。

## 2. 权威所有者

| 事实 | Owner |
|---|---|
| 用户、成员、角色和租户授权 | identity/tenant services |
| 站点、桩、EVSE、设备生命周期 | asset/charge point services |
| OCPP 连接与消息路由 | OCPP transport/message handler |
| 充电会话与用量 | charging/session services |
| 价格与会话价格快照 | pricing service |
| 应收金额 | billing + Invoice |
| 支付状态与 Provider 对账 | payment/reconciliation services |
| 钱包余额变化 | wallet transaction service |
| 告警、监控和审计 | operations services |

## 3. 强制规则

- API 不信任客户端 tenant_id；服务必须从可信身份/设备/关联对象解析。
- 跨领域调用通过 service/明确 contract，不直接修改他域模型。
- 数据库 transaction 包含一个用例需要的原子变化；外部网络调用不能在未知状态下重复扣款。
- 金额使用 Decimal；UTC 时间；状态迁移显式校验。
- OCPP、Webhook、Checkout confirm、远程命令和退款均须幂等。
- 高频设备事件使用 Redis/采样策略，不恢复每事件永久写入。
- 新 API/数据库/事件契约属于至少 C2，必须先架构审查。

## 4. 禁止

- Provider SDK 类型泄漏为核心 API。
- 从日志或 Redis 推导最终账务状态。
- 在 OCPP handler 中直接扣款。
- 使用通用 super session 绕过普通租户授权。
- 在启动时自动创建/改写 schema 代替 Alembic。
- 为前端便利复制支付、价格或权限业务规则。

## 5. Backend Agent 门禁

backend-agent 启动时读取 `TECH_ARCHITECTURE.md`、本文件、相关 ADR、批准的 Change/feature 和 frozen contract。发现边界不适配时提交 Architecture Change Request，不得自行重构全局架构。
