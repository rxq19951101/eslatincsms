---
id: INT-001
status: ready-for-dev
---

# 测试计划

## 单元与契约

- App：一次按钮事件只派发一次 start thunk；恢复 ongoing 会话只调用 active/meter API；zh/en/es 快照或文本断言无跨语言硬编码；UUID 不进入可见文本。
- Backend：首次 accepted、设备 rejected、设备 timeout、已有 ongoing、并发重复 start；每种情况断言 OCPP 远程命令次数和 HTTP 结果。
- Admin：transactions 使用 ocpp_identity；状态和日期随三种语言变化；UUID 不作为 OCPP 身份回退。
- 数据：seed → scenario → cleanup 后 SIM E2E ongoing 为零；清理不影响非白名单数据。

## 集成

- App 公共站点列表同时返回 Tenant A/B 的公开站点。
- Tenant A Admin/transactions/statistics/wallet 不能读取 Tenant B 私有运营与结算数据。
- Dashboard 同一台在线 Available 设备同时计入 online 和 available，不计入 offline。

## 三端闭环

1. 重置并生成最小 SIM E2E 基线。
2. Admin 与 App 登录，确认设备在线可用。
3. App 单击一次开始；日志断言一个 HTTP start 和一个 OCPP RemoteStartTransaction。
4. 确认 Admin 只有一条 ongoing，会话功率/电量增长。
5. 刷新 App，自动恢复进行中页面。
6. App 停止，确认一条 completed、一次账本扣款、余额变化等于费用。
7. 三语言切换检查确认页、完成页、钱包、Admin 会话/交易页。
8. cleanup 后确认无 SIM E2E ongoing 脏会话，模拟桩回到 Available。
