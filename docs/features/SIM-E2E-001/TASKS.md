---
id: SIM-E2E-001
status: ready-for-dev
---

# 任务拆分

## Backend / charger-sim

- B1：清除明文测试凭证，建立环境 secret 规则。
- B2：实现 scenario schema、loader、variables、runner、reports。
- B3：实现 OCPP 1.6 actor、状态机、UniqueId、远程命令及故障注入。
- B4：实现 Admin/App/FakePayment API actor 与公共 API 断言。
- B5：修正 CSMS greeting、CALLRESULT、连接 fencing、UniqueId 幂等、transaction 分配。
- B6：修正安全停止、自动故障/离线告警、测试 seed。
- B7：交付 P0 YAML 场景和单元/协议测试。

## Frontend

- F1：修正 App UUID 类型。
- F2：Admin/App 增加稳定 testID/aria 标识。
- F3：Admin 暴露非敏感扫码载荷复制入口；App Web 保留手动 QR。
- F4：补 Admin/App 组件与契约测试。

## QA

- Q1：验证场景 schema、secret 扫描和报告脱敏。
- Q2：执行 L0-L3 门禁与 P0 场景。
- Q3：启动三端并执行 Admin/App Web UI E2E。
- Q4：在可用模拟器上执行 iOS/Android 冒烟并给出 GO/NO-GO。
