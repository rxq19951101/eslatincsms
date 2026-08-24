---
id: OPS-SIM-001
status: ready-for-dev
---

# 本地模拟器可重复初始化

## 背景

本地 `charger-sim` 会直接连接 `SIM-E2E-CP-001`，但 Compose 没有在模拟器启动前创建对应的预注册资产。清空业务数据后，CSMS 按安全规则返回 WebSocket 403，模拟器进入重启循环。

## 目标

- 模拟器 profile 启动时自动执行现有 SIM-E2E 开发数据 seed。
- seed 完成后才启动充电桩模拟器。
- 清空业务数据和 Redis 后可重复恢复同一套稳定测试资产。
- 保持 OCPP 预注册校验开启，不通过关闭安全规则绕过问题。

## 非目标

- 不修改生产环境初始化逻辑。
- 不新增数据库迁移。
- 不在日志、Compose 配置或 seed JSON 中输出密码或设备密钥。
