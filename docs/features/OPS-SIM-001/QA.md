---
id: OPS-SIM-001
status: accepted
---

# QA 结果

## 干净环境

- PostgreSQL 业务表已清空，schema 与 `alembic_version` 保留。
- Redis DB 0 已清空。
- `sim-e2e-seed` 在空业务数据上退出码为 0，并可重复执行。
- 常驻 `charger-sim` 当前持续运行，不再进入 403 重启循环。

## OCPP 与计量

- WebSocket 连接接受。
- BootNotification 返回 Accepted。
- StatusNotification Available 成功。
- Heartbeat 成功。
- 12 秒真实充电窗口产生多次 MeterValues：PostgreSQL 仅一条分钟采样，Redis 保留最新 18 Wh，MeterValues 永久 OCPP 消息行为 0 条。

## 自动化测试

- 模拟器 Actor 与场景 schema：17 项通过。
- seed 幂等、环境限制和敏感信息测试：1 项通过。
- 三个受影响 P0 场景 YAML 校验通过。

## 新发现问题

- Admin 场景在远程启动幂等重放步骤返回 409：首次真实启动创建 ongoing session 后，后端在读取既有幂等结果前先执行连接器占用校验。该问题属于独立后端任务，不在本初始化任务中扩展修改。
