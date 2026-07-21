# 测试计划

## L0/L1

- Scenario schema/变量/secret 校验单元测试。
- OCPP frame、状态机、UniqueId、故障注入测试。
- Admin Vitest、App Jest/TypeScript、Backend pytest。

## L2/L3

- 空 PostgreSQL + Redis + CSMS + charger-sim。
- P0 API/协议：接入、Admin 启停、App 充电、余额、安全停止、重连、重复、乱序、故障、租户和权限。
- 每个账务用例断言最多一个订单、流水和结算。

## L4

- Admin 浏览器：登录、租户上下文、站点/桩、远程控制、会话、告警、语言。
- App Web：登录、手动 QR、启动、实时计量、停止、结算、钱包、历史、语言。
- iOS/Android：登录、相机/定位权限、手动 QR 或扫码、启动/停止冒烟（环境可用时）。

## 门禁

- P0 100% PASS，无 flaky、BLOCKED、NOT_RUN。
- 租户、权限、归属、幂等、安全停止、凭证泄漏任一失败直接 NO-GO。
- 后端精确回归集、SIM-E2E P0 与全量 `pytest tests` 必须同时通过。
- Admin production build 必须在允许构建器正常启动子进程的环境中通过。
- 浏览器 E2E 前，真实 PostgreSQL/Redis 的 `/health` 必须返回 `ok=true`。
