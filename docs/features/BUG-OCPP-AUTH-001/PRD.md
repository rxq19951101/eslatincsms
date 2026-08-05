---
id: BUG-OCPP-AUTH-001
status: ready-for-dev
priority: P0
---

# 含冒号 OCPP identity 的设备认证修复

## 背景

系统允许 OCPP identity 使用 `:`，生产设备也采用了区域化 identity，例如
`CO.BOGOTA:SIM-AC-7KW-01`。设备使用 Basic Auth 发送
`<ocpp_identity>:<secret>` 时，服务端按第一个冒号拆分，导致 identity 被截断并返回
HTTP 403。数据库中保存的密钥哈希与创建接口返回的密钥实际一致。

## 目标

- 含冒号的已预注册 OCPP identity 可使用其独立密钥完成 WebSocket 认证。
- 不含冒号的现有设备认证行为保持兼容。
- 错误 identity、错误密钥和畸形 Authorization 继续失败关闭。
- 不轮换现有设备密钥，不修改数据库结构。

## 非目标

- 不改变 OCPP identity 格式。
- 不修改 Admin 创建充电桩流程。
- 不修改 OCPP 1.6J 消息契约。
- 不操作生产数据库或自动部署生产环境。
