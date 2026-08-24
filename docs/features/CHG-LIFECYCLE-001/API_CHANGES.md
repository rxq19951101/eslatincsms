---
id: CHG-LIFECYCLE-001
status: ready-for-dev
contract: frozen
---

# API 契约

## 公共约定

- 所有接口使用认证租户上下文进行隔离，不接受请求体中的 `tenant_id` 作为授权依据。
- 生命周期写操作的 `reason` 去除首尾空格后长度为 3–500。
- 所有时间使用 UTC ISO 8601。
- 业务状态冲突统一返回 `409` 和稳定的 `code`、`message`、`blockers`。
- 写操作成功时返回资源当前生命周期；已达到目标状态的重复请求返回当前状态，不产生重复副作用。

### 测试阶段兼容约定

- 本契约的测试阶段实现不新增数据库迁移。
- 站点 `lifecycle_status` 由 `is_active` 映射为 `active | archived`，本阶段不返回 `closing`。
- 充电桩 `lifecycle_status` 以 `is_active` 映射为 `active | retired`；退役写操作同时设置 `commissioning_status=suspended`，本阶段不返回 `retiring`。
- 生命周期原因、操作者和时间从现有 `AuditLog` 返回，不新增资源表字段。
- 存在进行中会话或未完成必要账务时，退役返回 `409`；本阶段不提供异步等待退役。
- 存在历史会话或订单的充电桩不得迁移；历史站点快照契约延期到生产数据库迁移阶段。

通用冲突响应：

```json
{
  "detail": {
    "code": "site_has_active_charge_points",
    "message": "Site has charge points that must be moved or retired",
    "blockers": [
      {
        "type": "active_charge_point",
        "resource_id": "charge point UUID",
        "display_code": "A01"
      }
    ]
  }
}
```

## 站点字段变更

Admin 站点列表和详情增加：

```json
{
  "lifecycle_status": "active | archived",
  "archived_at": "2026-08-02T12:00:00Z | null",
  "archive_reason": "string | null",
  "active_charge_points_count": 3,
  "retiring_charge_points_count": 0,
  "retired_charge_points_count": 2
}
```

默认 `GET /api/v1/sites` 只返回 `active` 站点，并增加查询参数：

- `lifecycle_status?: active | archived`

未传参数时不得返回 `archived`。

创建站点必须以 `active` 状态创建；普通站点更新接口不得直接修改
`is_active`，生命周期变化只能通过归档和恢复接口完成。

普通 Admin 站点详情的 `charge_points` 只返回 `active` 充电桩，并为每项返回 `lifecycle_status`；`retired` 不得混入该数组。

## `GET /api/v1/sites/{site_id}/archive-preflight`

权限：`sites.read`。

响应：

```json
{
  "site_id": "site UUID",
  "lifecycle_status": "active",
  "can_archive_now": false,
  "counts": {
    "active_charge_points": 2,
    "retiring_charge_points": 0,
    "retired_charge_points": 3,
    "ongoing_sessions": 1,
    "unsettled_business_records": 1
  },
  "blockers": [
    {
      "type": "active_charge_point | ongoing_session | unsettled_business",
      "resource_id": "UUID or stable business identifier",
      "display_code": "A01 | null"
    }
  ]
}
```

`retired_charge_points` 不阻止归档，但会阻止永久删除。

## `POST /api/v1/sites/{site_id}/archive`

权限：`sites.write`。

请求：

```json
{
  "reason": "Location contract ended"
}
```

仅当不存在 `active` 充电桩及进行中/未完成业务时成功。成功响应：

```json
{
  "site_id": "site UUID",
  "lifecycle_status": "archived",
  "archived_at": "2026-08-02T12:00:00Z"
}
```

存在阻塞项返回 `409 site_archive_blocked`。

## `POST /api/v1/sites/{site_id}/restore`

权限：`sites.write`。

请求：

```json
{
  "reason": "Location reopened"
}
```

成功后站点变为 `active`；不得自动恢复站点下的退役充电桩。

## `DELETE /api/v1/sites/{site_id}`

权限：`sites.write`。

请求体：

```json
{
  "confirmation": "site_ab12cd34ef56ab78",
  "reason": "Created by mistake"
}
```

`confirmation` 必须等于站点 `site_code`。仅完全未使用的站点允许永久删除；否则返回 `409 site_permanent_delete_blocked`，并在 `blockers` 中返回设备、业务、定价、收藏、归档或审计关联类型。

## 充电桩字段变更

Admin 充电桩详情及归档查询增加：

```json
{
  "lifecycle_status": "active | retired",
  "retirement_reason": "string | null",
  "retirement_requested_at": "2026-08-02T12:00:00Z | null",
  "retired_at": "2026-08-02T12:05:00Z | null",
  "original_site": {
    "id": "site UUID",
    "site_code": "site_ab12cd34ef56ab78",
    "name": "Bogota Centro"
  }
}
```

默认充电桩运营列表、Admin 站点详情、App 和 Dashboard 只消费 `lifecycle_status=active` 的设备。

## `GET /api/v1/chargers/{charge_point_id}/retirement-preflight`

权限：`chargers.read`。

响应：

```json
{
  "charge_point_id": "charge point UUID",
  "lifecycle_status": "active",
  "can_retire_now": false,
  "will_wait_for_sessions": false,
  "counts": {
    "ongoing_sessions": 1,
    "pending_remote_commands": 0,
    "unsettled_business_records": 0
  },
  "blockers": [
    {
      "type": "ongoing_session",
      "resource_id": "session UUID"
    }
  ]
}
```

进行中会话、无法安全完成的待执行指令或账务异常都作为 `blockers` 返回，并阻止测试阶段退役。

## `POST /api/v1/chargers/{charge_point_id}/retire`

权限：`chargers.write`。

请求：

```json
{
  "reason": "Physical charger removed"
}
```

无进行中会话：

```json
{
  "charge_point_id": "charge point UUID",
  "lifecycle_status": "retired",
  "retirement_requested_at": "2026-08-02T12:00:00Z",
  "retired_at": "2026-08-02T12:00:00Z"
}
```

有进行中会话或未完成必要账务时返回 `409 charger_retirement_blocked`，不修改充电桩、凭据或当前会话。运营人员完成会话和账务后重新提交退役请求。

## `POST /api/v1/chargers/{charge_point_id}/restore`

权限：`chargers.write`。

请求：

```json
{
  "reason": "Device returned to service"
}
```

仅 `retired` 可恢复。响应必须返回一次性新 OCPP 凭据，旧凭据继续失效：

```json
{
  "charge_point_id": "charge point UUID",
  "lifecycle_status": "active",
  "commissioning_status": "testing",
  "ocpp_identity": "CO.BOGOTA:CP-01",
  "ocpp_secret": "returned once",
  "credential_rotated": true
}
```

对已完成恢复的请求进行幂等重试时，不再次轮换凭据，返回
`ocpp_secret: null` 和 `credential_rotated: false`。

## `DELETE /api/v1/chargers/{charge_point_id}`

权限：`chargers.write`。

请求体：

```json
{
  "confirmation": "CO.BOGOTA:CP-01",
  "reason": "Created by mistake"
}
```

`confirmation` 必须等于 `ocpp_identity`。仅未投运草稿且不存在任何设备/业务历史时允许永久删除；否则返回 `409 charger_permanent_delete_blocked`。

## `GET /api/v1/asset-archive/sites`

权限：`sites.read`。

查询参数：

- `search?: string`
- `archived_from?: UTC datetime`
- `archived_to?: UTC datetime`
- `limit?: integer`，默认 50，范围 1–200。
- `offset?: integer`，默认 0。

只返回当前租户 `lifecycle_status=archived` 的站点。

## `GET /api/v1/asset-archive/chargers`

权限：`chargers.read`。

查询参数：

- `search?: string`，匹配公开编号、公开名称和 OCPP Identity。
- `original_site_id?: UUID`
- `retired_from?: UTC datetime`
- `retired_to?: UTC datetime`
- `limit?: integer`，默认 50，范围 1–200。
- `offset?: integer`，默认 0。

只返回当前租户 `lifecycle_status=retired` 的充电桩。

## 迁移接口约束变更

现有 `POST /api/v1/sites/{site_id}/bind-charge-points` 保留路径，但增加强制校验：

- 源设备与目标站点必须属于认证租户。
- 目标站点必须为 `active`。
- 设备必须为 `lifecycle_status=active`。
- 设备不得存在进行中会话、历史会话、订单或未完成远程指令。
- 迁移只更新从未产生业务历史的设备当前 `site_id`。
- 请求继续使用 `force_move=true` 确认跨站点迁移，可选传入 3–500 字符的
  `reason`；未传时审计日志使用服务端默认迁移原因。
- 批量请求先完整预检，再在一个事务内迁移；任一设备被阻塞时全部保持原站点。
- 已经属于目标站点的重复请求作为幂等成功，不重复写迁移审计。
- 归档站点同时拒绝通过任一充电桩创建接口新增活动设备，返回
  `409 site_not_operational`。

冲突返回 `409 charger_move_blocked`。

## App 与业务入口行为

- App 站点列表和详情不得返回 `archived` 站点或 `retired` 充电桩。
- 对退役设备的扫码检查返回 `409 charger_not_operational`。
- 对归档站点的扫码检查返回 `409 site_not_operational`。
- 对已失效二维码返回 `400 qr_token_invalid`，不得重新解析到退役设备。
- 创建充电会话/订单和远程启动使用同一运营状态门禁，不满足条件时不得产生会话、订单或待执行远程指令。
- OCPP 认证对 `retired` 设备失败关闭；恢复后仅接受新凭据。
- 恢复后的二维码重新生成时必须轮换 token；旧 token 继续失效。

## 生产阶段延期数据契约

生产数据库迁移阶段，`charging_sessions` 和 `orders` 新建记录必须保存不可变站点快照：

- `site_id`
- `site_code_snapshot`
- `site_name_snapshot`

既有记录通过迁移回填当前可解析站点；回填后历史报表优先使用快照，禁止在设备迁移时更新快照。测试阶段不执行该迁移，并通过禁止迁移已有业务历史的设备保护归属。
