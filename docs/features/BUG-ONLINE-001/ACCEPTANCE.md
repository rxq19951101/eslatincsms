---
id: BUG-ONLINE-001
status: ready-for-dev
---

# 验收标准

1. `last_seen` 在五分钟内但状态为 `Offline` 的充电桩不计入站点列表在线数量。
2. `last_seen` 在五分钟内且状态为 `Available`、`Charging` 或其他非 `Offline` 状态的充电桩计为在线。
3. `last_seen` 超过五分钟或为空时不计在线。
4. 站点列表在线数量与站点详情展示的离线结果一致。
5. 退役充电桩和归档站点继续从普通运营查询排除。
6. 定向后端测试通过，无数据库迁移。
7. CSMS 和 Admin 容器使用最新源码完成一次重建，并在已登录 Admin 页面复核。
