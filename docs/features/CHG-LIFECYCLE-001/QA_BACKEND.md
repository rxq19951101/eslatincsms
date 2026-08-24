---
id: CHG-LIFECYCLE-001
status: passed
tested_at: 2026-08-02
scope: backend-focused
---

# 后端 QA 记录

## 结论

后端生命周期定向回归通过，未发现阻止进入 Admin QA 的后端缺陷。本轮仅增加 QA 测试，不修改业务实现，不增加数据库迁移。

## 覆盖矩阵

| 验收范围 | 测试证据 | 结果 |
| --- | --- | --- |
| 生命周期状态映射与原因校验 | `test_asset_lifecycle_service.py` | 通过 |
| 退役、恢复、归档状态迁移与幂等 | `test_charger_lifecycle_api.py`、`test_site_lifecycle_api.py` | 通过 |
| 进行中会话和未完成业务阻塞 | 生命周期 API 与业务门禁测试 | 通过 |
| 普通查询、Dashboard 和绑定候选过滤 | `test_asset_lifecycle_query_filters.py` | 通过 |
| 扫码、订单、OCPP 和远程操作门禁 | `test_asset_lifecycle_business_gates.py` | 通过 |
| 历史归属和迁移安全 | `test_charge_point_move_safety.py` | 通过 |
| 归档资产租户隔离 | `test_asset_archive_api.py` | 通过 |
| 生命周期读写权限与跨租户修改防护 | `test_asset_lifecycle_permissions.py` | 通过 |
| 站点与充电桩永久删除阻塞 | 生命周期 API 测试及充电桩删除定向用例 | 通过 |

## 执行结果

```text
38 passed, 1 warning in 13.03s
```

测试命令仅使用内存 SQLite 测试数据库，不访问或修改生产数据库。

## 剩余范围

- Admin 交互 QA 尚未执行。
- 端到端集成验收尚未执行。
- 生产阶段专用生命周期字段和迁移仍按计划延期。
