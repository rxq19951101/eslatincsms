---
id: PAY-MP-001
status: approved
owner: product
audience: frontend
---

# 前端专用产品需求

## 前端责任

- App 支持支付方式列表、添加卡、默认卡、删除卡、钱包充值、单次直接充电、已保存卡支付、3DS 和支付状态恢复。欠费列表、银行卡/钱包欠费补缴 UI 和欠费恢复页本期延期。
- 移除支付方式页面的本地演示数据，不再使用自定义卡号/CVV 表单直接调用 Mercado Pago Card Token API。
- App 通过后端 Checkout Session 打开托管 HTTPS 安全页；Deep Link 只接收会话和结果引用，不接收 Card Token。
- App 支付方式投影支持 `credit_card | debit_card | prepaid_card | null`，使用用户可读文案展示信用卡、借记卡、预付卡和旧记录未知类型。
- App 不提供卡品牌、卡类型、发卡银行、证件资料或分期输入；这些属于后端托管页与 MercadoPago.js 边界。

## 用户流程和页面状态

- `charging_direct` 新卡固定“仅本次使用”，不得展示保存卡开关或发送 `save_card=true`；用户要保存卡时必须离开当前单次支付选择，通过“我的 → 支付方式 → 添加银行卡”完成独立 `purpose=save_card` Checkout，再选择该已保存卡充电。
- 已保存卡显示品牌、信用/借记/预付类型、尾号和默认标记；付款前进入安全页重新输入 CVV，不要求 App 收集证件资料。
- 启动收费充电前选择 `wallet` 或 `direct_card`；direct card 必须先获得 ready Payment Intent。
- 显示“充电结束后按实际金额扣款”，不得把直接支付描述为充值或预授权。
- 结算覆盖 processing、action required、approved、declined、expired、error、unpaid 和 refunded。
- App 被关闭或进入后台后，重新打开可恢复 Checkout Session 和 PaymentOrder；欠费账单列表/补缴恢复体验属于后续需求。
- 收到 `402 UNPAID_CHARGES` 时只显示安全、可本地化的阻止提示并停止继续充电；不得显示未冻结的欠费字段、伪造已支付或通过 UI 乐观解除门禁。
- Checkout 404/过期返回后，App 必须清理不可复用的本地会话引用并允许创建新会话；409 已确认先查询原会话事实，503 保留未知状态并允许安全重试查询。
- App 所有直接充电文案只说明结束后按实际金额扣款，不显示预授权、冻结、预扣或已付款承诺。

## 展示规则

- 金额以 COP 本地格式展示，但提交和状态映射以契约十进制字符串为准。
- 支付错误显示可行动的业务文案，不暴露 Provider 原始错误、Token 或用户敏感信息。
- `prepaid_card` 显示为“Tarjeta prepagada”；`payment_type=null` 显示安全的通用银行卡文案，不猜测为信用卡。
- 受支持语言必须同步更新；按钮禁用、加载、空列表、失败重试和危险删除确认完整。
- 托管页、3DS 和 Deep Link 需要覆盖返回、取消、过期、网络中断和重复回跳。

## API 依赖

- 所有字段、枚举、路径和错误引用 `contracts/API.md`。
- 前端不得提交 `tenant_id`、merchant account、金额型充电账单或 Provider 密钥。
- 后端 MerchantContext 从 C1 延伸 C2 时，App 契约和页面流程保持不变。

## 前端验收重点

- 安全卡片采集、信用/借记/预付投影、支付方式用户隔离的 UI 表现、单次新卡禁止同时保存、独立添加卡、保存卡 CVV 流程、状态恢复、3DS、准确账单、D1 欠费门禁安全提示、全语言和相邻钱包/充电流程回归。

## 前端非范围

- Mercado Pago Access Token、Customer/Card 服务端调用、Webhook、数据库、Redis、OCPP、计费和退款记账实现。
- C2 租户商户授权页面。
- 本期不实现欠费列表 API adapter、`UnpaidCharge` 前端类型/字段映射、银行卡或钱包欠费补缴 UI、欠费恢复页；后续需单独补充并冻结契约。
- 不在 App 内实现托管页 HTML、Secure Fields、证件输入或卡 BIN 识别；不以本地逻辑猜测支付类型。
