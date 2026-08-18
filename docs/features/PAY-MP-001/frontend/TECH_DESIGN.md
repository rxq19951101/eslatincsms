---
id: PAY-MP-001
status: approved
owner: frontend
reviewed_at: 2026-08-12
---

# 前端技术设计

## 1. 任务边界

本设计只授权 FE-P0-1 的 App 改造。产品事实来自 `product/`，字段、状态与错误码来自冻结的 `contracts/API.md`，后端行为依据 `BE-P0-1_HANDOFF.md` 与 `BE-P0-2_HANDOFF.md`。

硬边界：

- 不修改 `csms/`、Hosted Checkout HTML、Admin、共享契约、数据库、迁移或生产开关。
- App 不采集或存储 PAN、有效期、CVV、证件类型、证件号码和 Card Token。
- App 不允许用户选择或猜测卡品牌、发卡方、信用/借记/预付类型或分期。
- `charging_direct` 与所有 saved-card Checkout 固定 `save_card=false`；只有独立 `save_card + new_card` Checkout 使用 `save_card=true`。
- FE-4B 欠费列表和补缴继续延期；本任务只保留 D1 安全阻止提示。

## 2. 类型与展示模型

将非敏感支付方式类型收敛为：

```ts
type CanonicalPaymentMethodType =
  | 'credit_card'
  | 'debit_card'
  | 'prepaid_card';

interface CanonicalPaymentMethod {
  id: string;
  provider: string;
  brand?: string | null;
  payment_type?: CanonicalPaymentMethodType | null;
  last_four?: string | null;
  is_default: boolean;
}
```

新增或复用一个纯展示映射，输入只接受 canonical type/null，输出 i18n key：

| API 值 | es | en | zh |
|---|---|---|---|
| `credit_card` | Tarjeta de crédito | Credit card | 信用卡 |
| `debit_card` | Tarjeta débito | Debit card | 借记卡 |
| `prepaid_card` | Tarjeta prepagada | Prepaid card | 预付卡 |
| `null`/未知 runtime 值 | Tarjeta bancaria | Bank card | 银行卡 |

支付方式列表和 `PaymentMethodBar` 必须共用该映射，避免一个页面把 prepaid/null 显示成信用卡。品牌仅格式化显示，不参与卡类型判断；缺失品牌使用通用卡品牌文案。

## 3. Checkout 请求约束

### 独立添加卡

`createSaveCardCheckoutSession()` 保持 purpose 专用固定请求：

```text
purpose=save_card
payment_method_mode=new_card
saved_payment_method_id omitted/null
save_card=true
amount/charge_point_id/connector_id/session_id omitted
```

`AddPaymentScreen` 只打开服务端 `checkout_url` 并跟踪非敏感 session；成功后返回 `PaymentMethods` 刷新 canonical 列表。

### 直接充电

`buildChargingDirectCheckoutRequest` 删除 `saveNewCard` 参数并固定：

```text
new card:
  purpose=charging_direct
  payment_method_mode=new_card
  saved_payment_method_id=null
  save_card=false

saved card:
  purpose=charging_direct
  payment_method_mode=saved_card
  saved_payment_method_id=<current-user canonical id>
  save_card=false
```

`ChargingProcessScreen` 删除 `saveNewCard` state、setter 和组件 props。新卡选项文案明确“仅用于本次充电”；不得显示 Switch、checkbox 或隐含保存动作。需要保存卡的用户通过独立支付方式管理入口完成后，再选择服务端返回的 saved card。

### 其他 purpose

- `wallet_top_up` 继续固定 `save_card=false`。
- `unpaid_charge` 本期 App 不创建。
- generic `createCheckoutSession` 可以保留为底层 transport，但页面只调用 purpose 专用 builder；测试必须覆盖互斥矩阵，防止 future caller 重新传入冲突组合。
- 每次用户显式创建操作生成一个幂等键；按钮和 in-flight mutex 防止同一操作重复创建。404/expired 后只有用户点击“重新开始”才生成新键；409/503/网络未知状态不创建新 Checkout。

## 4. 支付方式页面和充电选择组件

### `PaymentMethodsScreen`

- 继续只读取 canonical `/api/v1/app/payment-methods`。
- 每项显示格式为“品牌 + 末四位”“卡类型”“默认标记”；prepaid 与 null 使用第 2 节映射。
- 默认切换和删除保持 loading/disabled、幂等请求、删除确认和安全 404 行为。
- 添加按钮只进入 `AddPayment`，不渲染本地卡片字段。

### `PaymentMethodBar`

- 删除 `saveNewCard`、`onSaveNewCardChange`、Switch import、测试 ID 和相关样式。
- 新卡选项只显示“本次使用新卡”和“不保存”的说明。
- saved card 选项显示品牌、类型、末四位；默认卡有文字或 Badge，不只靠排序表达。
- `payment_type=null` 仍可供旧卡选择，显示通用银行卡；付款时卡事实由服务端/Provider 校验，App 不补默认值。
- 列表加载失败时保留新卡入口，但显示 saved-card 加载失败和重试动作；不得把失败伪装成空列表。

## 5. Checkout 恢复模型

### 非敏感本地引用

`checkoutCoordinator` 继续独占 AsyncStorage，建议将引用扩展为：

```ts
interface PendingCheckoutReference {
  checkoutSessionId: string;
  purpose: PaymentCheckoutPurpose;
  expiresAt: string;
  source?: 'add_payment' | 'wallet_top_up' | 'charging_direct';
}
```

不得持久化 `checkout_url`、3DS URL、Card Token、证件信息、Provider payload、完整错误、QR token 或 Payment Intent。旧的无 `source` 引用必须兼容读取并按 purpose 推导安全结果页。

### 统一恢复结果

API adapter/协调器对 Axios 错误读取标准 `detail.code`，只输出前端内部的安全决策，不把 Provider 文本交给 UI：

```ts
type CheckoutRecoveryKind =
  | 'resolved'
  | 'expired_or_missing'
  | 'already_submitted'
  | 'temporarily_unavailable'
  | 'network_unknown';
```

处理规则：

1. 正常响应：以 `CheckoutSessionResponse.status` 为事实。
2. `expired` 或 404 `CHECKOUT_SESSION_NOT_FOUND`：清除 pending 引用和当前页面 Payment Intent；返回 `expired_or_missing`。
3. 409 `CHECKOUT_ALREADY_CONFIRMED`：不清除、不创建、不 confirm；立即执行一次原 Session 的只读状态查询。若仍无法读到事实，返回 `already_submitted` 并保留引用，后续只允许再次查询。
4. 503 `CHECKOUT_UNAVAILABLE`：保留引用和最后服务端状态，返回 `temporarily_unavailable`。
5. 网络/超时：保留引用，返回 `network_unknown`；不得自动新建 Checkout。
6. `approved|declined|error` 为业务终态并清理 pending；`expired` 按第 2 条；`created|ready|processing|action_required` 保留。

Hosted HTML 的 404/409/503 页面不直接改变 App 状态；用户回跳、App 前台或手动刷新后仍调用以上查询。Deep Link 的 status 只做安全占位，不覆盖 GET 返回。

### 页面行为

| 恢复结果 | `PaymentResult` | `ChargingProcess` |
|---|---|---|
| expired/missing | 显示会话过期和“重新开始/返回” | 清理旧 checkout；下次明确点击才创建新 checkout |
| already submitted | 显示“操作已提交，正在确认”，只允许查询 | 不重复 confirm/start；等待查询得到 intent 或终态 |
| temporarily unavailable | 显示“暂时无法确认”，允许重试查询/安全返回 | 保留 sessionId，不切换为新卡支付，不生成新 session |
| network unknown | 显示“状态待确认” | 保留最后状态和引用，恢复网络后查询 |
| ready + payment_intent_id | 按 purpose 返回来源 | 只在用户点击启动且 intent 存在时调用 start |

`resolveDirectCheckout` 需要从单一 `error` phase 扩展为可区分的 `expired`、`submitted`、`unavailable` 或等价 UI 状态。重复 Deep Link、定时轮询、前台恢复和用户刷新共享 in-flight 锁；这些入口只能发 GET，不得重复 start。

App 重启后，`RootNavigator` 可继续把 pending Checkout 导向 `PaymentResult`。`charging_direct` 恢复成功不自动启动充电；用户回到原屏或重新扫码后，由后端校验 Payment Intent 与桩/connector 是否匹配。`PAYMENT_INTENT_INVALID` 时清理旧 intent 并要求重新完成安全 Checkout。

## 6. 状态、导航和 3DS

- `eslatin://payment-return` 只接受长度受限的 session id 与白名单状态，忽略其余 query。
- `next_action.type=open_url` 且 URL 通过现有 Mercado Pago HTTPS hostname allowlist 才能打开；无效 URL 显示安全错误并继续查询服务端。
- `processing` 不显示失败；达到本地轮询上限只停止自动轮询并显示手动查询，不修改服务端状态。
- `action_required` 打开受信任 URL，返回后再次查询；取消 3DS 不等于 declined/approved。
- 404/expired 后的 CTA 根据 purpose 返回 `AddPayment`、钱包充值或 ChargingProcess 来源；没有安全来源时返回上一页，不自动执行写操作。
- D1 `UNPAID_CHARGES` 仍只显示三语言安全提示并禁用重复启动，不导航到未冻结的欠费列表。

## 7. i18n、文案和可访问性

三语言同步维护以下键：

- `prepaidCard`、通用 `bankCard`；
- 新卡“仅本次使用/不会保存”，独立添加卡说明；
- Checkout 已过期、已提交待确认、暂不可用、网络状态未知、重新查询、重新开始；
- saved card CVV 提示和默认卡标签。

删除或停止使用 `charging.saveCard`、`charging.saveCardHint` 等“本次支付同时保存”的文案。所有直接充电文案仅说明“充电结束后按实际账单金额扣款”；不得出现预授权、冻结、预扣或已经付款。

交互要求：

- radio、默认卡、状态和按钮都有可访问名称与 state；
- loading 时按钮 disabled，重复点击无副作用；
- 卡类型和状态由文字 + 图标/Badge 表达，不只靠颜色；
- 小屏下卡品牌、类型、末四位不截断关键事实；
- 错误区域使用可访问 alert，Provider 原始英文错误不直接展示。

## 8. 文件所有权

FE-P0-1 实现 Agent 只可按需要修改：

- `app/src/types/index.ts`；
- `app/src/api/payments.ts`、`app/src/api/charging.ts`；
- `app/src/features/payment/checkoutCoordinator.ts`；
- `app/src/components/payment/PaymentMethodBar.tsx`；
- `app/src/screens/account/PaymentMethodsScreen.tsx`、`AddPaymentScreen.tsx`；
- `app/src/screens/charging/ChargingProcessScreen.tsx`；
- `app/src/screens/payment/PaymentResultScreen.tsx`；
- 必要时支付恢复相关 `RootNavigator.tsx`、`linking.ts`；
- `app/src/i18n/en.ts`、`es.ts`、`zh.ts`；
- 上述范围对应测试。

不得以“顺便清理”为由改 Admin、后端、Wompi、欠费页面、公共主题或不相关导航。

## 9. 开发验证策略

### 定向测试

- payment types/display：credit、debit、prepaid、null 和非法 runtime 值；
- request matrix：save_card 唯一 true；charging new/saved、wallet top-up 均 false；无敏感字段；
- PaymentMethodBar：不再出现保存 Switch；saved card 展示类型/尾号/默认；
- PaymentMethods：prepaid/null 三语言展示，加载/空/错误/默认/删除保持；
- coordinator：expired/404 清理，409 查询且不创建，503/网络保留，终态清理，旧本地引用兼容；
- PaymentResult/ChargingProcess：恢复 CTA、重复 Deep Link/前台/轮询不重复 confirm/start；
- linking：支付回跳安全过滤不破坏 reset-password；
- i18n：三语言 key 完整且无旧保存卡 UI 文案断言。

### 相邻回归

- wallet top-up Hosted Checkout；
- wallet/direct-card/free 启动、`PAYMENT_INTENT_INVALID`、`UNPAID_CHARGES`；
- ChargingComplete/PaymentResult 状态；
- 3DS allowlist；
- 支付方式默认/删除；
- FE-4B 延期边界测试，确保没有新增欠费 adapter/UI。

### 开发命令

在 `app/` 内运行：

```text
npx tsc --noEmit
npm test -- --runInBand <FE-P0-1 定向测试文件>
```

实现 Agent 只报告实际执行结果。App 全量广泛回归、Android/iOS/浏览器设备验证和 Admin build/smoke 由独立 frontend QA 执行；真实 Mercado Pago sandbox 与 3DS 由后续 QA/E2E/人工验收。
