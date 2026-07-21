---
id: INT-001
status: ready-for-dev
---

# 验收标准

1. 用户单击一次开始充电，App 只发送一次 start 请求；加载态不会触发重复派发。
2. 相同用户、二维码和活动会话的重复 start 不会重复发送 OCPP RemoteStartTransaction，并返回可恢复的幂等结果。
3. start API 明确区分已接受、已拒绝、超时和已有活动会话；不能把“已入队/已发送”等同于设备接受。
4. App 重新加载或重新登录后能自动发现本人 ongoing 会话并进入充电过程页。
5. App 启动确认、充电完成、钱包流水不出现非当前语言文案，不展示充电桩/会话数据库 UUID。
6. Admin 交易列表的 OCPP 身份列展示 `ocpp_identity`，状态和时间按当前语言本地化。
7. Dashboard 在线数、离线数和状态数基于同一套在线判定，不互相矛盾。
8. SIM E2E seed/cleanup 不留下跨场景 ongoing 会话；历史脏测试会话可由清理脚本删除。
9. App 仍能看到所有租户的公开充电桩；Admin、账务和结算租户隔离测试继续通过。
10. 统一构建后完成一次 start → MeterValues → stop → completed → 单次扣款三端回归。
11. App 充电页不得产生重叠轮询，退到后台或离开页面后停止轮询；Admin 页面不可见时停止刷新；CORS 预检不消耗 API 限流额度，认证用户之间不共享同一个 IP 限流桶。
