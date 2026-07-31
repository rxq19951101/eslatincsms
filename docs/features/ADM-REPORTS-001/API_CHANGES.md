---
id: ADM-REPORTS-001
status: ready-for-dev
contract: frozen
---

# 适用端点

- `GET /api/v1/admin/statistics/revenue`
- `GET /api/v1/admin/statistics/energy`
- `GET /api/v1/admin/statistics/orders`
- `GET /api/v1/admin/statistics/export`

# 公共查询参数

- `days?: 1..365`：兼容快捷范围；默认 30。
- `start_date?: YYYY-MM-DD`
- `end_date?: YYYY-MM-DD`
- `site_id?: string`：站点公开编号或内部 UUID，服务端必须验证当前租户归属。
- `group_by=day`：P0 仅支持 day，其他值返回 422。

`start_date/end_date` 必须同时出现；出现时优先于 `days`。日期范围按 UTC 左闭右开处理，`end_date` 包含整天。

# 响应

收入：

```json
[{"date":"2026-07-21","total_revenue":"2700.00","total_energy_kwh":"2.660","invoice_count":1,"currency":"COP"}]
```

电量：

```json
[{"date":"2026-07-21","total_energy_kwh":"2.660","session_count":1}]
```

订单：

```json
[{"date":"2026-07-21","order_count":1,"completed_count":1}]
```

金额和电量使用十进制字符串；计数使用整数。

# 导出

`report_type` 必须为 `revenue|energy|orders`，`format` P0 仅支持 `csv`。日期与站点参数和查询端点一致。无数据时仍输出该报表类型正确的表头。

