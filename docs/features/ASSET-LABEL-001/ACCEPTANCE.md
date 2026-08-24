---
id: ASSET-LABEL-001
status: ready-for-dev
---

# 验收标准

1. App 站点详情可获得充电桩运营名称、运营编号，以及每个充电枪的稳定数字编号和可选现场编号。
2. Admin 活跃会话与充电记录可获得站点、充电桩和充电枪公共展示字段。
3. App API 响应不包含 OCPP Identity 或 OCPP transaction ID。
4. 默认展示名缺失时，客户端只回退到运营编号或国际化的充电枪编号，不回退到 OCPP、EVSE 或数据库标识。
5. Admin 技术诊断仍可获得执行远程命令所需的协议字段。
6. 中文、英文、西班牙语使用同一充电枪编号，文案符合各语言字典。
7. 所有查询继续按认证租户隔离；App 继续遵循公开站点可见性规则。
8. 公共 App 和 Admin 运营响应中不存在与 `connector_number` 重复的 `connector_id` 或 `evse_id`。
