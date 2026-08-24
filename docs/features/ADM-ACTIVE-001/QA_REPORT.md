---
id: ADM-ACTIVE-001
task: QA-1
date: 2026-07-21
verdict: superseded
scope: targeted-source-acceptance
---

# QA 报告

> 本报告主体记录的是旧的 OCPP Identity + transaction ID 客户端契约。该契约已于 2026-07-22 被业务 `session_id` 远程停止契约替代，以下旧结论不再作为当前实现验收依据。

## 2026-07-22 契约修订证据

- 活跃会话公共响应不再返回 OCPP Identity、OCPP transaction ID、EVSE ID 或重复的 connector_id。
- 远程停止改为 `POST /api/v1/ocpp/remote-stop-session`，客户端只提交 `session_id` 与操作原因，协议字段由服务端按租户解析。
- Admin 和 App 统一使用 `connector_number`；现场编号缺失时分别显示“充电枪 / Connector / Conector + 编号”。
- 后端站点与活跃会话定向测试：10 passed。
- 后端远程停止定向测试：29 passed；严格请求校验补充用例：1 passed。
- Admin 定向测试：11 passed；TypeScript 通过。
- App 定向测试：3 passed；TypeScript 通过。
- 本轮未构建容器，未执行全量回归。

## 结论

针对性测试均通过，但源码验收发现 2 个阻断验收的问题，因此 QA-1 结论为 **失败**。本轮未修改产品代码、未重建容器，也未把当前修改前镜像中的页面作为新代码证据。

## 通过项

- 两租户隔离：active 查询以认证上下文中的 `tenant_id` 过滤会话及关联数据；后端测试包含其他租户 ongoing 会话不可见场景。
- 运营字段映射：源码按 session 的 `charge_point_id`、`site_id`、`evse_id` 批量映射站点、设备和枪口，返回冻结契约新增字段并保留旧字段。
- 金额格式：预估费用通过 `BillingService.calculate_cost` 的 Decimal 结果转为字符串；可靠计量缺失时返回 `estimated_cost=null`、`currency=null`，前端显示“暂不可用”。
- 列表呈现：站点、display_code、physical_reference、用户引用、开始时间、电量、功率、时长、预估费用、最后计量时间和状态均有对应源码展示；OCPP Identity 与 transaction ID 被降为辅助信息。
- 停止交互：确认文本包含站点、充电桩、枪口和交易号；取消时不调用接口；确认后使用所选行 `charger.id` 与 `transaction_id`，并携带 `Idempotency-Key`。
- 停止反馈与刷新：源码区分成功、设备拒绝、503 离线及其他接口错误；请求完成后在 `finally` 中刷新列表。
- 权限展示：无 `chargers.control` 时前端不显示停止按钮；远程停止后端接口也要求 `chargers.control`。
- 三语言：本功能新增文案均有英语和西班牙语映射，未发现新增硬编码语言混用。

## 失败项

1. **active 会话读取接口缺少 `transactions.read` 后端权限校验。** `GET /api/v1/transactions/active` 仅依赖 `get_current_admin_user`，没有使用 `require_permission("transactions.read")`。仅隐藏侧栏不能阻止无读取权限用户直接调用接口，不满足 PRD“查看需要现有交易/会话读取权限”。

2. **同站点多设备时可能套用错误的充电桩专属费率。** 充电桩专属 Tariff 同时带有 `site_id`；active 接口构建 `tariffs_by_site` 时未限制 `charge_point_id IS NULL`，会把最新的某桩专属费率登记为站点默认费率。若同站点另一充电桩没有专属费率，可能错误使用前一充电桩费率，违反“沿用当前费率选择规则”和金额准确性要求。

## 自动化测试证据

- `python3 -m pytest -q tests/test_api_transactions_active.py`：2 passed，1 warning。
- `npm test -- --run 'app/(dashboard)/__tests__/sessions-transactions.integration.test.tsx'`：6 passed。
- 首次直接执行 `pytest` 因命令不在 PATH 失败，改用同一 Python 环境的 `python3 -m pytest` 后通过。

## 覆盖缺口

- 后端现有新增测试只覆盖一个本租户站点/设备/枪口加一个其他租户会话，未覆盖同一租户多个站点、多个设备、多个枪口同时映射。
- 缺失计量已覆盖；“有可靠计量但无可用费率”未作为独立后端测试场景覆盖。
- 前端测试验证幂等键存在，但未验证失败后重试复用同一幂等键；通用接口错误反馈与失败后刷新也未单独断言。

## 待容器重建后人工验收

- 使用新镜像登录普通租户，核对多个站点/设备/枪口的实际列表定位与横向滚动布局。
- 使用仅有 `transactions.read`、同时无 `chargers.control` 的账号确认可查看但无停止按钮；使用无 `transactions.read` 的账号确认接口和页面均拒绝访问。
- 连接真实或测试 OCPP 设备验证停止成功、设备拒绝、设备离线、接口错误提示，以及请求完成后的状态刷新。
- 对同站点两个设备配置“站点默认费率 + 其中一桩专属费率”，核对各会话预估费用不会串用费率。
- 切换中文、英语、西班牙语检查确认框、反馈消息、缺失数据文案及金额显示。
