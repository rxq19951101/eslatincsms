---
id: ADM-ACTIVE-001
status: ready-for-dev
---

# 任务拆分

## BE-1

- 按冻结契约扩展 active sessions 响应。
- 批量加载站点、设备、EVSE、计量和费率，避免逐会话 N+1。
- 使用 Decimal 计算预估费用。
- 增加 API 与租户隔离测试。

## FE-1

- 将进行中会话改为运营信息优先的列表。
- 增加详情入口、权限控制、停止确认和操作结果反馈。
- 补充三语言及针对性组件测试。

## QA-1

- 验证两租户隔离、多个站点/设备/枪口定位。
- 验证停止确认、取消、成功、拒绝、离线和幂等重试。
- 验证金额与缺失计量/费率显示。

## BE-2（QA 阻断修复）

- `GET /api/v1/transactions/active` 强制校验 `transactions.read`。
- 站点默认费率只能来自 `charge_point_id IS NULL` 的站点级 Tariff，禁止串用同站点其他充电桩的专属费率。
- 增加无读取权限拒绝访问和同站点多设备费率选择测试。
