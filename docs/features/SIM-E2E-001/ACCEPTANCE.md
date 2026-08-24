---
id: SIM-E2E-001
status: ready-for-dev
---

# 验收标准

1. `scenario validate` 能拒绝未知 action、重复 step id、未定义变量、明文 secret 和非法 OCPP identity。
2. `scenario run` 可执行至少四类 actor，并输出 JSON、JUnit 与 timeline 报告。
3. Boot、Status、Authorize、Start、Meter、Stop、Heartbeat 使用标准 OCPP 1.6J array frame；业务拒绝返回 CALLRESULT。
4. RemoteStart 并发只接受一个；Authorize 拒绝不得继续 Start；未知 transaction 的 RemoteStop 返回 Rejected。
5. 可注入 disconnect/reconnect、Faulted、相同 UniqueId 重放、Meter-before-Start 与 Stop-before-Start。
6. 相同 UniqueId 重放不产生第二会话、第二计量、第二结算或第二告警。
7. App 端会话、EVSE、计量 ID 使用 UUID 字符串；OCPP transaction ID 保持整数。
8. App 用户可通过正式 QR token 完成 check → start → active/meter → stop → settle，钱包只扣一次。
9. 余额不足阻止启动；任何支付/欠费状态都不能阻止已有会话安全停止。
10. Faulted/离线自动产生租户内告警且去重；恢复后可确认并解决。
11. 租户 A 管理员不能查看或控制租户 B 设备；只读角色写操作返回 403。
12. Admin 与 App Web 的 P0 UI 场景实际点击通过；语言切换 zh/en/es 后错误与状态文本正确。
13. 仓库和报告不包含密码、JWT、支付 token、完整卡号或第三方密钥。
14. 单元、契约、后端集成、Admin、App、charger-sim 测试全部通过后才允许启动三端验收。
15. 假支付必须实际请求本地 CSMS webhook；首次、重复、乱序和冲突投递分别验证订单状态、
    钱包余额、Webhook 事件唯一性和账本唯一性，禁止模拟器本地合成成功响应。
16. 8 个 P0 场景只能依赖 seed JSON 和环境 secret，不要求测试人员手工查找 alert、
    session、QR 或租户 ID。
17. 默认 Compose 不启动任何模拟器；`simulator` 与 `e2e` profile 显式启用，
    数据库密码和应用密钥不得有非空硬编码默认值。
18. 重复/乱序、故障、权限、归属、余额和远程控制场景必须断言后端状态不变量，
    不能只断言请求已发送或接受一组宽泛状态码。
19. 未通过后台预登记的 OCPP identity 发送 BootNotification 时必须返回 `Rejected`，
    且不得创建 ChargePoint、Device、站点归属或其他设备资产；已预登记设备仍返回 `Accepted`。
