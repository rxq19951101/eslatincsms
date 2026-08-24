---
id: BUG-OCPP-AUTH-001
status: ready-for-dev
---

# 验收标准

- [x] identity `CO.BOGOTA:SIM-AC-7KW-01` 与正确密钥通过设备凭证校验。
- [x] 含冒号 identity 可完成 `/ocpp?id=<identity>` WebSocket 握手。
- [x] 不含冒号 identity 的现有 Basic Auth 校验继续通过。
- [x] 其他 identity 的正确密钥不能冒充目标设备。
- [x] 正确 identity 携带错误密钥必须拒绝。
- [x] 缺失、畸形或非 UTF-8 Basic Auth 必须拒绝且不得抛出未处理异常。
- [x] 现有 `X-API-Key` 和 Bearer 兼容行为不回归。
- [x] 不新增数据库迁移，不轮换设备密钥。
