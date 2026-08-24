---
id: SIM-POWER-001
status: ready-for-dev
---

# 验收标准

- [x] 未设置共享上限时，两个活跃枪口仍分别使用各自 `power_kw`。
- [x] 共享上限 60kW、枪口上限均为 60kW、仅枪口 1 活跃时，分配 60kW。
- [x] 同一配置下两枪同时活跃时，各分配 30kW，总和不超过 60kW。
- [x] 一枪停止后，另一枪下一次计量恢复到 60kW。
- [x] 枪口上限分别为 20kW 和 60kW、共享上限 60kW 时，分配 20kW 和 40kW。
- [x] `Power.Active.Import` 使用实际分配功率，而不是静态枪口上限。
- [x] `Energy.Active.Import.Register` 按实际分配功率累积。
- [x] 非活跃枪口不参与功率分配。
- [x] `shared_power_limit_kw <= 0` 在配置构造或 CLI 入口被拒绝。
- [x] `run-one --shared-power-limit-kw` 和 `run-many.shared_power_limit_kw` 均生效。
- [x] charger-sim 定向单元测试通过。
- [x] 不新增数据库迁移，不修改服务端 API。
