---
id: BUG-ONLINE-001
status: ready-for-dev
---

# API 契约

## `GET /api/v1/sites`

响应结构不变。

`online_charge_points_count` 的语义冻结为：站点下活动充电桩中，最近五分钟内有有效状态更新且有效状态不为 `Offline` 的充电桩数量。

本修复不增加字段、不改变错误响应、不修改数据库结构。
