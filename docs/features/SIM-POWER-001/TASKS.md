---
id: SIM-POWER-001
status: ready-for-dev
---

# 任务拆分

## Simulator

- S1：在充电桩 profile 中加入可选共享功率上限并校验正数。
- S2：实现受每枪上限约束的公平功率分配函数。
- S3：MeterValues 和电量累积改用实时分配功率。
- S4：为 `run-one` CLI 和 `run-many` YAML/JSON 接入新配置。

## QA

- Q1：覆盖无共享上限、单枪、双枪、非对称枪口上限和停止后重分配。
- Q2：覆盖 CLI 与 `run-many` 配置解析。
- Q3：执行 charger-sim 定向测试并记录结果。

## 文件范围

- `charger-sim/simulator/profiles.py`
- `charger-sim/simulator/metering.py`
- `charger-sim/simulator/charge_point.py`
- `charger-sim/cli.py`
- `charger-sim/tests/` 下直接相关测试
- `charger-sim/README.md`
