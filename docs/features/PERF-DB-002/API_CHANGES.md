---
id: PERF-DB-002
status: ready-for-dev
---

# API 变更

`GET /api/v1/app/charging/meter-values` 保持数组响应，单项新增字段：

```json
{
  "source": "database"
}
```

- 数据库记录：`source=database`，`id` 仍为 MeterValue UUID，可作为 `since_id`。
- Redis 实时记录：`source=realtime`，`id` 为 `realtime:<timestamp>`，不得作为 `since_id`。
- Redis 不可用或没有快照时，接口只返回数据库记录。

OCPP MeterValues CALLRESULT 结构不变。
