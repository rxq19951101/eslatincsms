# 技术债与待办

## TECH-HEARTBEAT-HISTORY-001：心跳历史旧代码清理与低频快照

- 状态：`deferred`（暂缓，不进入当前开发）
- 优先级：P2
- 现状：`app.utils.history_recorder` 仍导入已移除的 `HeartbeatHistory`、
  `StatusHistory` 和 `Charger`，启动时产生“历史记录功能不可用”警告。
- 当前影响：实时 OCPP 心跳、Redis 在线判断和 `EVSEStatus.last_seen` 正常；旧版逐条
  心跳历史不可用，相关历史统计可能为空。
- 后续范围：
  - 删除或替换旧 `history_recorder` 加载逻辑，消除误导性启动警告。
  - 明确心跳历史 API 的产品契约和数据保留周期。
  - 采用每 5～15 分钟健康快照或聚合方案，禁止恢复每次心跳一条数据库写入。
  - 补充数据库写入频率、历史查询和在线状态不回归测试。
- 本次决定：仅记录 TODO，不修改业务代码、不新增迁移、不部署。
