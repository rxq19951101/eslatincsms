---
id: APP-ORDER-TRACE-001
status: ready-for-dev
---

# 验收标准

1. 已结算充电历史详情展示发票号、最终金额、币种和支付状态。
2. 金额来自 `Invoice.total_amount`，App 不根据电量与当前站点价格重新计算。
3. 未结算会话显示国际化“待结算”，不显示虚构金额。
4. 钱包 `charge` 流水携带对应的 `charging_session_id`，点击后进入 `ChargingHistoryDetail`。
5. 无 `charging_session_id` 的钱包流水保持不可点击。
6. 订单详情不展示 OCPP 交易号、OCPP 身份或数据库充电桩 UUID。
7. 设备和枪口使用面向用户的公开标签，并支持中文、英文和西班牙文。
8. 后端验证当前 App 用户拥有被访问的会话，不能通过钱包关联越权读取其他用户订单。
9. 金额在后端和前端均按十进制定点语义处理；展示符合 COP 格式。
10. 直接相关后端测试、App 测试和 TypeScript 检查通过。
