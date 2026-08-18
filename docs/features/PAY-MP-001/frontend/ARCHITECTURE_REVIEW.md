---
id: PAY-MP-001
status: approved
owner: frontend
reviewed_at: 2026-08-12
---

# 前端架构评估

## 结论

FE-P0-1 可以在现有 React Native、React Navigation、Axios、Redux、AsyncStorage 和三语言 i18n 架构内完成，不需要修改冻结 API、后端托管 HTML、Admin、数据库或迁移。BE-P0-1 与 BE-P0-2 已提供可消费的开发交接：canonical 支付方式支持 `credit_card | debit_card | prepaid_card | null`，Hosted Checkout 已执行单 Token 单用途校验，并负责动态证件类型、BIN 自动识别、保存卡 CVV 页面和 404/409/503 安全状态页。

本轮没有真实产品或契约阻塞，前端架构与技术设计批准，FE-P0-1 可进入开发。后端 QA 仍为 `paused-by-owner`，真实 Mercado Pago sandbox、浏览器和 3DS 尚未验收；这些是发布和 E2E 门禁，不阻塞本前端实现任务，也不能被前端开发测试替代。

## 实际架构与现有实现

### 可复用链路

- `app/src/api/payments.ts` 已提供 canonical 支付方式 CRUD、Checkout Session 创建/查询、允许的 Hosted Checkout origin 和 Mercado Pago 3DS hostname 校验。
- `app/src/features/payment/checkoutCoordinator.ts` 已只持久化非敏感 Checkout 引用，并集中执行创建、查询和终态清理。
- `app/src/screens/account/AddPaymentScreen.tsx` 已使用独立 `purpose=save_card` Hosted Checkout，不在 App 内采集 PAN、有效期、CVV 或证件信息。
- `app/src/screens/account/PaymentMethodsScreen.tsx` 已以 `/api/v1/app/payment-methods` 为唯一卡片事实来源，支持默认卡、删除、加载、空态和错误重试。
- `app/src/screens/charging/ChargingProcessScreen.tsx` 与 `PaymentMethodBar.tsx` 已具备 wallet/direct-card 选择、新卡/保存卡选择、Checkout 打开和 Payment Intent 后启动的主链路。
- `app/src/screens/payment/PaymentResultScreen.tsx`、`navigation/linking.ts` 和 `RootNavigator.tsx` 已具备安全 Deep Link、前后台恢复、轮询及 App 重启后的 pending Checkout 查询入口。
- 既有 UI 基础组件、`useI18n`、`formatMoneyCOP` 和错误归一化能力可以继续复用，不需要引入新的全局状态库或 WebView 卡片表单。

### P0 必须修正的实现差距

| 位置 | 当前事实 | P0 处理 |
|---|---|---|
| `app/src/types/index.ts` | `CanonicalPaymentMethodType` 只有 credit/debit | 扩展为 credit/debit/prepaid；`null` 继续表示旧记录未知类型 |
| `PaymentMethodsScreen.tsx` | 只识别 credit/debit，其他值落到通用卡 | 显式展示 prepaid；`null` 使用通用银行卡文案，不能猜测信用卡 |
| `PaymentMethodBar.tsx` | 新卡下仍渲染保存 Switch，并且 saved card 只显示品牌和末四位 | 删除保存开关和相关 props；saved card 显示品牌、类型、末四位和默认标记 |
| `app/src/api/charging.ts` | `buildChargingDirectCheckoutRequest` 接受 `saveNewCard` 并可能发送 `save_card=true` | 删除该参数；所有 `charging_direct` 新卡/保存卡固定 `save_card=false` |
| `ChargingProcessScreen.tsx` | 持有 `saveNewCard` 状态并传入请求；所有查询异常统一进入 error | 删除保存状态；按过期/404、已确认/409、503/网络未知分别恢复 |
| `checkoutCoordinator.ts` | 只按服务端终态清理引用，HTTP 错误没有可恢复分类 | 集中返回安全恢复决策；只有 404/expired 清理，409 只读回查，503/网络保留引用 |
| `PaymentResultScreen.tsx` | 查询失败只显示一个通用错误，不能指导重建或继续查询 | 分别展示“重新创建”“查询原会话”“稍后重试查询”，不根据浏览器页面猜支付结果 |
| i18n 与测试 | 三语言仍有“本次支付同时保存”文案，测试还要求 Switch 存在 | 删除冲突文案/断言，补 prepaid/null、恢复状态和相邻流程测试 |

Hosted Checkout 的动态证件类型、卡品牌/类型识别、西语表单和保存卡 CVV 由后端 HTML 负责；App 不复制这些字段、不增加卡种选择，也不解析 Provider 原始错误。

## 组件边界与状态所有权

### API 和纯映射

- API adapter 精确映射冻结契约，不接受 `tenant_id`、商户信息、Provider 凭证或原始卡数据。
- Checkout 请求由 purpose 专用 builder 约束。页面不得直接拼接会造成 `purpose/save_card/payment_method_mode` 冲突的对象。
- 支付方式类型转用户文案使用一个纯映射函数，供支付方式列表和充电卡片选择复用；未知 runtime 值与合法 `null` 都安全显示通用银行卡，不能回退为信用卡。

### Checkout coordinator

- coordinator 是 pending Checkout 引用和恢复决策的唯一所有者；屏幕不直接读写 AsyncStorage。
- 持久化内容只包含 `checkoutSessionId`、`purpose`、`expiresAt` 和非敏感来源标识，不包含 Checkout URL、Card Token、证件资料、3DS URL、Provider payload 或原始错误。
- Deep Link、App 回前台、PaymentResult 刷新和 ChargingProcess 恢复全部调用同一个只读查询入口。
- Deep Link 只触发查询，不能触发 confirm、创建支付、启动充电或把 URL 中的 status 当作最终事实。

### 屏幕

- `PaymentMethods`/`AddPayment` 继续承担唯一显式保存卡入口。保存成功后刷新 canonical 列表。
- `ChargingProcess` 的新卡表示“仅本次使用”；不显示保存开关。用户需要保存卡时，走独立支付方式管理流程后再选择 saved card。
- saved card 进入后端托管页重新输入 CVV；App 只发送 `saved_payment_method_id`，不收集 CVV。
- `PaymentResult` 负责通用 Checkout 查询结果和恢复动作；`ChargingProcess` 只在拿到匹配的 `payment_intent_id` 后调用 start，不自动重复启动。

## 会话恢复可行性

冻结契约足够支持 P0 恢复，不需要新增响应字段：

| 服务端/网络事实 | 本地引用 | UI 和后续动作 |
|---|---|---|
| `expired` 或 404 `CHECKOUT_SESSION_NOT_FOUND` | 清除不可复用引用 | 显示会话已过期；用户显式操作后创建新 Checkout 和新幂等键 |
| 409 `CHECKOUT_ALREADY_CONFIRMED` | 保留 | 不重复 confirm/创建；查询原 `checkout_session_id`，展示服务端状态 |
| 503 `CHECKOUT_UNAVAILABLE` | 保留 | 显示状态暂无法确认；只提供重试查询或安全返回，不创建替代 Checkout |
| 网络失败/超时 | 保留 | 保留最后服务端状态，稍后重试 GET；不得显示成功或失败 |
| `processing/action_required` | 保留 | 继续可恢复；3DS URL 必须通过既有 allowlist |
| `approved/declined/error` | 清除 | 展示终态；按 purpose 返回支付方式、钱包或充电来源 |

Hosted 页面本身的 404/409/503 由 BE-P0-2 渲染安全页面；回到 App 后仍以 Checkout Session 查询为唯一事实。409 的恢复只执行读操作，若读查询继续不可用则保持“已提交、状态待确认”，不能自动新建或重复启动。

## 导航、国际化和可访问性

- 保留 `eslatin://payment-return`，只解析长度受限的 `checkout_session_id` 和白名单状态；密码重置 Deep Link 必须相邻回归。
- 西班牙语、英语、中文同步增加 prepaid、未知卡类型、会话过期、已提交待确认、暂不可用和安全重试文案；删除直接充电同时保存卡的用户文案。
- 直接充电只说明结束后按实际金额扣款，不出现预授权、冻结、预扣或已付款。
- 卡类型、默认状态、Checkout 状态使用文字配合 Badge/Icon，不只依赖颜色；按钮具备 disabled/loading 和可访问名称。
- FE-P0-1 不改后端西语托管页，但前端 QA 需要把托管页的手机宽度、键盘和屏幕阅读器列为后续真实浏览器回归面。

## Admin 和相邻回归面

Admin 不在 FE-P0-1 的业务实现范围内，不修改 Admin 文件。独立前端 QA 后续至少执行 Admin 构建与既有支付页面 smoke，确保 App 类型和配置变更没有破坏 Admin。

App 相邻回归包括：

- 支付方式加载/空态/默认/删除和独立添加卡；
- wallet top-up、wallet/direct-card/free 启动与 D1 `UNPAID_CHARGES` 安全阻止；
- 新卡、credit/debit/prepaid saved card 和旧 `null` 投影；
- Deep Link 去重、前后台、App 重启、3DS allowlist、404/expired、409、503 和网络失败；
- 三语言、Reset Password Deep Link、PaymentResult、ChargingComplete；
- 不新增欠费列表 adapter、`UnpaidCharge` 映射或补缴 UI，FE-4B 保持 `deferred-by-owner`。

## 风险与门禁

- BE-P0-1/2 的开发测试不是独立后端 QA；真实 Mercado Pago、Redis/PostgreSQL、3DS 和 Provider 回调仍未验收。
- 当前工作区有大量已有未提交改动；实现 Agent 必须限定文件所有权并保留全部无关改动。
- FE-P0-1 完成后只能声明开发测试结果，必须交给独立 frontend QA；backend QA、frontend QA、E2E 和人工审查完成前保持 `PAYMENT_RAILS_ENABLED=false`。
