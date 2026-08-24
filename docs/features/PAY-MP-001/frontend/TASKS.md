---
id: PAY-MP-001
status: approved
owner: frontend
reviewed_at: 2026-08-12
---

# 前端任务拆分

## P0 顺序与门禁

产品文档已 `approved`，API 契约已 `frozen`，BE-P0-1 与 BE-P0-2 交接可用于前端开发。前端架构评估和技术设计已批准；唯一实现任务 `FE-P0-1` 已完成并交接，状态为 `done-review-required`。

后端 QA 继续 `paused-by-owner`。FE-P0-1 完成后交给独立 frontend QA，不能用实现 Agent 的定向测试代替 QA；backend QA、frontend QA、E2E 和人工审查完成前保持 `PAYMENT_RAILS_ENABLED=false`。

## FE-P0-1：App 卡类型、单用途 Checkout 与恢复对齐

状态：`done-review-required`

实现证据：App canonical prepaid/null 映射、单用途 Checkout、保存卡 CVV 入口和安全恢复状态已按本任务完成；`npx tsc --noEmit` 通过，12 个定向/相邻测试套件 65 项通过。详细命令、变更和未执行范围见 `frontend/FE-P0-1_HANDOFF.md`。

### 目标

让 App 精确消费 P0 frozen contract：完整展示信用卡、借记卡、预付卡和旧未知类型；移除 `charging_direct` 同时保存卡能力；保留独立添加卡与 saved-card CVV 流程；按 404/expired、409、503 和网络未知状态安全恢复 Checkout。

### 允许文件

- `app/src/types/index.ts`
- `app/src/api/payments.ts`
- `app/src/api/charging.ts`
- `app/src/features/payment/checkoutCoordinator.ts`
- `app/src/components/payment/PaymentMethodBar.tsx`
- `app/src/screens/account/PaymentMethodsScreen.tsx`
- `app/src/screens/account/AddPaymentScreen.tsx`
- `app/src/screens/charging/ChargingProcessScreen.tsx`
- `app/src/screens/payment/PaymentResultScreen.tsx`
- 必要时 `app/src/navigation/RootNavigator.tsx`、`app/src/navigation/linking.ts`
- `app/src/i18n/en.ts`、`app/src/i18n/es.ts`、`app/src/i18n/zh.ts`
- 以上范围内现有或新增的 App 测试

实现前必须重新读取当前文件和 diff；工作区已有改动全部保留。只修改完成本任务所需文件，未实际需要的允许文件不得触碰。

### 禁止范围

- 不修改 `csms/`、后端测试、Hosted Checkout HTML、Admin、共享契约、数据库、迁移或生产配置。
- 不采集或记录 PAN、有效期、CVV、证件资料、Card Token、Provider 原始错误或完整敏感 URL。
- 不增加卡品牌/类型/发卡银行/分期选择，不把 unknown/null 猜成信用卡。
- 不创建 `UnpaidCharge` 新映射、欠费列表 adapter、补缴 UI 或欠费恢复页；FE-4B 继续延期。
- 不把 409/503/网络未知状态改成新 Checkout、支付失败或支付成功。

### 实现步骤

1. 扩展 canonical 类型为 `credit_card | debit_card | prepaid_card`，保留 `payment_type=null`；建立支付方式类型的三语言集中展示映射。
2. 更新 `PaymentMethods` 和 `PaymentMethodBar`：显示品牌、类型、末四位和默认状态；prepaid 显式展示，null 使用通用银行卡。
3. 删除 `PaymentMethodBar` 的保存卡 Switch、`saveNewCard` props/state/测试；新卡充电固定“仅本次使用”。
4. 修改 `buildChargingDirectCheckoutRequest`，无论 new/saved card 都固定 `save_card=false`；独立 `createSaveCardCheckoutSession` 继续固定 `save_card=true`。
5. 在 API adapter/coordinator 集中实现安全恢复分类：expired/404 清理；409 只读回查；503/网络保留；Deep Link/前台/轮询复用同一查询和 in-flight 去重。
6. 更新 `PaymentResult` 与 `ChargingProcess` 的恢复状态、CTA 和重复写保护；ready intent 只在用户点击启动时使用。
7. 同步 en/es/zh 文案，删除“本次支付同时保存”交互文案，保证直接充电没有预授权/冻结/预扣/已付款表述。
8. 更新定向测试并执行 TypeScript 和相邻支付/充电回归；不启动 QA 或其他 Agent。

### 独立验收

- `CanonicalPaymentMethod.payment_type` 编译期支持 prepaid，运行时 null/未知不回退 credit。
- 支付方式列表和充电卡片选择在三语言中准确显示 credit/debit/prepaid/null、末四位和默认卡。
- `app-charging-save-card-toggle`、Switch 及对应 props/state 不再存在；`charging_direct` 请求不能产生 `save_card=true`。
- 独立 AddPayment 请求保持 `save_card + new_card + save_card=true`，无金额、充电对象和原始卡字段。
- saved-card charging 请求包含用户选择的 `saved_payment_method_id` 且 `save_card=false`；App 页面不采集 CVV 或证件资料。
- expired/404 清除不可复用引用并允许用户显式新建；409 不重复 confirm/create/start；503/网络未知保留引用且只重试查询。
- 重复 Deep Link、App 回前台、轮询和手动刷新最多共享一个查询，不重复启动充电。
- `PAYMENT_INTENT_INVALID` 清理旧 intent 并要求重新 Checkout；`UNPAID_CHARGES` 仍只显示安全阻止提示。
- 三语言键完整，支付类型和状态不只靠颜色表达；loading/disabled/alert 可访问。
- wallet top-up、wallet/direct-card/free、Reset Password Deep Link、3DS allowlist 和 FE-4B 延期边界回归无新增失败。

### 开发验证

至少运行：

```text
cd app
npx tsc --noEmit
npm test -- --runInBand \
  src/api/__tests__/payments.checkout.test.ts \
  src/api/__tests__/payments.paymentMethods.test.ts \
  src/api/__tests__/charging.contract.test.ts \
  src/features/payment/__tests__/checkoutCoordinator.test.ts \
  src/components/payment/__tests__/PaymentMethodBar.test.tsx \
  src/screens/charging/__tests__/ChargingProcessScreen.start.test.tsx \
  src/navigation/__tests__/linking.test.ts \
  src/screens/payment/__tests__/MercadoPagoPaymentScreen.walletTopUp.test.tsx \
  src/screens/payment/__tests__/unpaid-entry-deferral.test.tsx
```

若实现新增 PaymentMethods/PaymentResult 屏幕测试，必须加入同一轮定向命令。测试未完成或发现相邻失败时按事实交接，不得宣称完整前端通过。

### 交接要求

完成后按统一格式报告：

- 实际修改的 App 文件和受影响路由；
- 请求矩阵、prepaid/null 映射和恢复状态证据；
- TypeScript 与定向测试命令/结果；
- iOS/Android/Web、三语言、真实 Mercado Pago 和设备验证中未执行的部分；
- 前端 QA 的广泛 App 回归与 Admin build/smoke 范围。

## 既有任务状态

| 编号 | 状态 | 说明 |
|---|---|---|
| FE-1 | done-development | canonical 支付方式、独立 AddPayment、默认/删除已实现；P0 显示修正在 FE-P0-1 |
| FE-2 | done-development | Hosted Checkout、Deep Link、3DS 和基础恢复已实现；P0 错误分类在 FE-P0-1 |
| FE-3 | done-development-p0-fix-required | wallet/direct-card/free 已实现；旧同时保存卡逻辑由 FE-P0-1 删除 |
| FE-4A | done-development | wallet top-up Hosted Checkout 已实现，需相邻回归 |
| FE-4B | deferred-by-owner | 欠费列表、补缴和恢复页不属于 P0 |
| FE-P0-1 | done-review-required | 实现与开发定向验证完成，等待只读复核和独立 frontend QA |

FE-P0-1 完成后停止并交接；不得自行进入 frontend QA、E2E、下一需求或生产部署。
