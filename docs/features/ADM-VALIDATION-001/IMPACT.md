# 影响分析

- Backend：数据库模型、Alembic baseline、站点/充电桩/远程控制/租户/钱包/配置 API。
- Admin：站点、租户、用户、设置、充电桩详情、登录和公共布局。
- App：仅在充电桩业务标识响应字段变化时验证兼容性。
- Simulator：继续通过 OCPP identity 连接，不依赖内部 UUID。
- 数据：开发环境重建；不执行旧数据迁移。
