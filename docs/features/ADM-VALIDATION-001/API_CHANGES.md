---
id: ADM-VALIDATION-001
status: ready-for-dev
contract: frozen
---

# 冻结 API 契约

## 站点

`POST /api/v1/sites` 与 `PUT /api/v1/sites/{site_id}`：

- `name`: trim 后 2-120 字符。
- `address`: trim 后 5-300 字符。
- `latitude`: `[-90, 90]`。
- `longitude`: `[-180, 180]`。
- `(latitude, longitude)` 不得为 `(0, 0)`。
- `operating_hours`: 可空；保留字符串兼容，本阶段限制 500 字符。

## 充电桩预注册

请求字段保持 `id` 兼容，但语义固定为 `ocpp_identity`，格式 `^[A-Za-z0-9._:-]{1,64}$`。响应返回 `id`（内部 UUID）与 `ocpp_identity`。重复返回 409。

## 远程控制

统一使用 snake_case：

- remote start: `{charge_point_id, id_tag, connector_id}`
- remote stop: `{charge_point_id, transaction_id}`
- reset: `{charge_point_id, type}`，`type` 仅 `Soft|Hard`

全部要求管理员认证、`chargers.control` 权限和租户归属。

## 租户开通

新增 `POST /api/v1/admin/tenants/provision`，单事务创建租户、首个管理员和成员关系。原有分步接口保留但 Admin 不再组合调用。

## 钱包调账

`POST /api/v1/admin/app-users/{user_id}/adjust-balance` 新增必填 `description` 与 `idempotency_key`；金额最多两位小数。

## 错误

- 字段无效：422。
- 唯一冲突：409。
- 未认证：401。
- 无权限/跨租户：403。
