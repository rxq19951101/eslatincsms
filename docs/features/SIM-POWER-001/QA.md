---
id: SIM-POWER-001
status: accepted
---

# QA 结果

## 行为验证

- 单枪活跃时可使用完整 60kW 共享上限。
- 双枪同时活跃时公平分配为 30kW + 30kW。
- 20kW 与 60kW 枪口并发时分配为 20kW + 40kW。
- 一枪停止后，剩余枪口下一次计量恢复为 60kW。
- OCPP 瞬时功率与累计电量均按实际分配功率生成。
- 未配置共享上限时保留原有每枪独立功率行为。

## 配置验证

- `run-one --shared-power-limit-kw` 可用。
- `run-many` 的 `shared_power_limit_kw` 可传入充电桩 profile。
- 非正数及非有限共享上限会被拒绝。

## 测试结果

- Python 语法检查通过。
- charger-sim 容器完整回归：74 项通过。
- 未新增数据库迁移，未修改服务端 API。
