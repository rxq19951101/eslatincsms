---
id: INT-001
status: ready-for-dev
---

# 任务

- Frontend/App：修复重复 start、自动恢复 ongoing 会话、三语言、公开业务标识和钱包流水展示。
- Backend：实现 start 幂等与设备回执语义，提供公开展示字段，统一在线统计，修复 seed/cleanup 脏会话。
- Frontend/Admin：修复 OCPP 身份、状态、时间和统计展示。
- QA：补充请求次数、幂等、拒绝/超时、恢复、国际化、租户边界、清理和三端闭环测试。
- 集成：所有修改完成后统一测试、重建容器、运行一次人工三端闭环。
- P0 请求治理：App 防重叠轮询与后台暂停、Admin 刷新收敛和 429 退避、后端认证身份/接口类别限流及 `Retry-After`。
