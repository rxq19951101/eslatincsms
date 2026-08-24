---
id: INT-001
status: ready-for-dev
contract: frozen
---

# API 契约

## POST `/api/v1/app/charging/start`

- 请求仍使用 `qr_token`，不新增前端可控 `tenant_id`。
- 成功响应必须包含稳定结果状态：`accepted` 或 `already_active`。
- `already_active` 返回当前会话所需的公开数据，供 App 恢复。
- 设备明确拒绝返回业务冲突错误；等待设备超时返回网关超时类错误。
- 同一用户、二维码、连接器已有 ongoing 会话时，不再次发送远程启动命令。

## 展示字段

- App 和 Admin 的设备展示字段使用 `ocpp_identity`。
- 数据库 UUID 仍可作为内部 API 关联键存在，但不得作为用户可见标签。
- 钱包流水由结构化 `type/reference` 在客户端本地化；不得把中文描述作为跨语言唯一展示事实。

## 租户规则

- App 公共站点列表不按 App 用户租户过滤。
- Admin、交易、账务、结算继续从认证上下文确定租户边界。
