# 影响分析

- `charger-sim`：目录级重构，保留 `run-one` 兼容入口，新增 `scenario validate/run/list`。
- `csms`：修正 OCPP UniqueId、连接 fencing、安全停止和自动告警；补 seed 与契约测试。
- `admin`：只增加稳定选择器和必要 QR 测试载荷展示，不改变业务权限。
- `app`：修正 UUID 类型、增加稳定选择器和 Web 手动 QR E2E 路径。
- Compose：默认不自动启动场景，新增显式测试 profile；支付凭证全部环境注入。
- 数据：开发环境重建；不迁移旧测试数据。
