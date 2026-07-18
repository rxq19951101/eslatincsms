# 测试计划

## Backend

- Schema 边界、唯一冲突、事务回滚、权限、跨租户、幂等与审计测试。
- 远程控制请求契约与活动 transaction ID 测试。

## Admin

- Vitest 覆盖站点、租户、钱包、设置和远程控制表单。
- 三语言字段错误与切换刷新测试。

## 集成

- PostgreSQL、Redis、WebSocket OCPP 和 charger-sim 场景。
- 浏览器执行创建站点失败/成功、预注册充电桩、远程控制和品牌视觉检查。
