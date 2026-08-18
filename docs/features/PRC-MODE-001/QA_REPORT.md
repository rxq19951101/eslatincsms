---
id: PRC-MODE-001
date: 2026-08-05
status: passed
---

# QA 报告

## 结论

本次定向回归未发现实现失败，且已补齐五类 P0 定价门禁的直接自动化证据。后端、Admin、App 既有回归通过；本轮未部署、未访问生产数据库。

当前结论为 **passed（测试通过）**，仅表示 PRC-MODE-001 的本地/测试 QA 门禁通过，不代表支付模块或生产发布已批准。

## 已执行检查

- 后端：60 项通过。
  - `test_pricing_modes.py`
  - `test_api_chargers.py`
  - `test_app_sites_api.py`
  - `test_p0_app_regressions.py`
  - `test_user_charging_flow.py`
  - 站点、充电桩及资产生命周期直接相关测试
- Admin：4 个测试文件、20 项通过。
- App：7 个测试文件、24 项通过。
- Admin TypeScript：通过。
- App TypeScript：通过。
- Python `compileall`：通过（字节码缓存定向到 `/tmp`）。
- Git diff 格式检查：通过。
- PRC-MODE-001 直接门禁：9 项通过（`tests/test_pricing_mode_qa.py`）。
- 定价/计费/支付意图联合回归：28 项通过。
- 后端全量回归：558 项通过，5 项跳过，20 项 warning。

## 已覆盖验收项

- 旧正价兼容为 `paid`，旧零价兼容为 `unavailable`。
- 桩级显式 `unavailable` 覆盖站点 `paid`。
- 会话启动只生成一个价格快照。
- Tariff 修改后，进行中会话仍使用启动时快照结算。
- 免费会话生成 0 COP 账单及支付记录，不扣余额、不生成 0 金额钱包流水。
- Admin 定价配置与展示相关回归通过。
- App paid/free/unavailable 展示、免费低余额启动及业务错误本地化相关回归通过。
- 既有公开站点、设备生命周期和充电流程回归通过。

## 本轮补齐的五类门禁

1. `free` 原因长度、时区感知的未来截止时间，以及过期后回落为 `unavailable`。
2. 有效模式为 `unavailable` 时，投运接口返回 HTTP 409 和 `TARIFF_NOT_CONFIGURED`。
3. 扫码检查与启动返回 HTTP 409 和稳定错误码，并断言没有发送 OCPP RemoteStart。
4. 定价变更 AuditLog 验证租户隔离、前后模式与原因，同时不包含敏感信息。
5. 站点 `unavailable` 与桩级 `paid/free` 覆盖组合的完整优先级矩阵。

## 风险判断

- 未发现 PRC-MODE-001 范围内的阻断性实现缺陷。
- 站点定价接口的 UUID 写入缺陷已修复并由上述门禁及后端全量回归覆盖。
- 本报告不解除 PAY-MP-001/PAY-MP-002 的 Provider、生产、人工 release 或 E2E 门禁。
