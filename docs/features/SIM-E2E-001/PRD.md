---
id: SIM-E2E-001
status: ready-for-dev
owner: product
---

# 场景驱动充电桩与三端测试平台

## 目标

将 `charger-sim` 重构为可重复、可注入故障、可驱动管理员与 App 用户行为、可输出机器报告的 OCPP 1.6J 场景测试平台，并用它完成 Admin、App、CSMS 三端本地验收。

## 用户角色

- 设备：单桩、多桩、多 connector、正常计量、故障、断线、重连、重复及乱序消息。
- 管理员：租户/站点/桩初始化、远程启停、钱包调账、告警处理、权限及跨租户验证。
- App 用户：注册/登录、余额、扫码检查、启动、实时计量、停止、结算、历史及语言。

## 交付范围

- YAML 场景 DSL、变量、步骤、超时、重试、并发、断言和确定性 seed。
- ChargePoint、Admin、AppUser、FakePayment 四类 actor。
- OCPP 1.6J happy path、故障、重连、重复、乱序、多 connector 行为。
- JSON、JUnit XML 和可读 timeline 报告；所有敏感字段脱敏。
- P0 场景包：接入、Admin 远程充电、App 扫码充电、余额不足、安全停止、断线重连、重复/乱序、故障告警、权限、跨租户、会话归属、三语言。
- App Web 与 Admin 作为完整业务 E2E；iOS/Android 在本地可用时执行权限/扫码冒烟。

## 非目标

- 不实现 OCPP 2.0.1。
- 不连接真实支付平台，不保存测试卡、账号或平台密钥。
- 不部署生产环境，不向生产开放测试支持接口。
- 本阶段不做 8–24 小时稳定性和 100 桩压力门禁。

## 产品原则

- 安全停止不得被余额、欠费或支付状态阻止。
- OCPP identity、内部 UUID、OCPP transaction ID 永不混用。
- 场景失败必须失败运行，不允许吞异常后继续标记 PASS。
- UI 自动化使用稳定 `testID/data-testid`，不得依赖翻译文本。
- 每个场景生成独立 `run_id`，重跑不得覆盖首次失败证据。
