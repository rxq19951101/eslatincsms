# FE-P0-1 前端交接

STATUS: done

CHANGED_FILES:

- `app/src/types/index.ts`
- `app/src/api/payments.ts`
- `app/src/api/charging.ts`
- `app/src/features/payment/checkoutCoordinator.ts`
- `app/src/components/payment/PaymentMethodBar.tsx`
- `app/src/screens/account/PaymentMethodsScreen.tsx`
- `app/src/screens/charging/ChargingProcessScreen.tsx`
- `app/src/screens/payment/PaymentResultScreen.tsx`
- `app/src/i18n/en.ts`
- `app/src/i18n/es.ts`
- `app/src/i18n/zh.ts`
- `app/src/api/__tests__/payments.checkout.test.ts`
- `app/src/api/__tests__/payments.paymentMethods.test.ts`
- `app/src/api/__tests__/charging.contract.test.ts`
- `app/src/features/payment/__tests__/checkoutCoordinator.test.ts`
- `app/src/components/payment/__tests__/PaymentMethodBar.test.tsx`
- `app/src/screens/account/__tests__/PaymentMethodsScreen.p0.test.tsx`
- `app/src/screens/payment/__tests__/PaymentResultScreen.recovery.test.tsx`
- `docs/features/PAY-MP-001/STATUS.md`
- `docs/features/PAY-MP-001/frontend/TASKS.md`
- `docs/features/PAY-MP-001/frontend/FE-P0-1_HANDOFF.md`

COMMANDS_RUN:

- `cd app && npx tsc --noEmit`
- `cd app && npm test -- --runInBand src/api/__tests__/payments.checkout.test.ts src/api/__tests__/payments.paymentMethods.test.ts src/api/__tests__/charging.contract.test.ts src/features/payment/__tests__/checkoutCoordinator.test.ts src/components/payment/__tests__/PaymentMethodBar.test.tsx src/screens/account/__tests__/PaymentMethodsScreen.p0.test.tsx src/screens/charging/__tests__/ChargingProcessScreen.start.test.tsx src/screens/payment/__tests__/PaymentResultScreen.recovery.test.tsx src/navigation/__tests__/linking.test.ts src/screens/payment/__tests__/MercadoPagoPaymentScreen.walletTopUp.test.tsx src/screens/payment/__tests__/unpaid-entry-deferral.test.tsx src/i18n/__tests__/i18nIntegrity.test.ts`
- 对授权文件执行限定 `rg`、`git diff --check`、`git diff --stat` 和限定 diff 审查。

TEST_RESULTS:

- 最终 TypeScript：`npx tsc --noEmit` 通过，0 error。
- 最终定向与相邻回归：12 个测试套件、65 passed、0 failed。
- 首轮新测试整合为 58 passed、6 failed，失败均来自新增测试 mock/语言夹具；修正夹具后针对失败套件 17 passed，随后以同一最终命令得到 65 passed。
- canonical payment method fixture 覆盖 `credit_card`、`debit_card`、`prepaid_card`、`null` 和非法 runtime 值；prepaid 显式展示，null/非法值使用通用银行卡，不回退信用卡。
- 请求矩阵 fixture 证明独立 `save_card + new_card` 固定 `save_card=true` 且不含金额/卡原始字段；`charging_direct` 的 new/saved card 和 wallet top-up 均固定 `save_card=false`。
- PaymentMethodBar fixture 证明保存 Switch、测试 ID 和相关 props 已移除；saved card 显示品牌、类型、末四位、默认标记及重新采集 CVV 提示，加载失败仍保留新卡和重试入口。
- coordinator fixture 覆盖 404/expired 清理、409 单次只读复查且不 create、503/网络未知保留引用、业务终态清理、旧引用 source 推导及并发 GET in-flight 去重。
- PaymentResult fixture 证明 Deep Link 的 `approved` 提示不能覆盖 GET 事实，submitted 只查询原 session，expired 只通过用户显式 CTA 返回来源；ChargingProcess 定向 fixture 覆盖重复 start、free、会话恢复和 D1 阻止，代码路径只在用户点击且存在 ready intent 时 start，并在 `PAYMENT_INTENT_INVALID` 后清理旧引用。
- 三语言 key 完整性、Reset Password Deep Link、wallet top-up、wallet/free 启动、D1 `UNPAID_CHARGES` 安全阻止和 FE-4B 延期边界测试通过。

CONTRACT_CHANGES:

- 无冻结 API 路径、请求字段、响应字段、状态或错误码变化。
- App 本地 `CanonicalPaymentMethodType` 按冻结契约扩展为 `credit_card | debit_card | prepaid_card`，`payment_type=null` 继续兼容旧投影。
- 无 Admin、后端、Hosted Checkout HTML、共享契约、数据库、迁移、生产配置、Wompi 或 FE-4B 欠费 adapter/UI 变化。

RISKS:

- 未执行 iOS/Android/Web 真机或浏览器视口、键盘、屏幕阅读器和前后台系统级验证；未执行真实 Mercado Pago Colombia sandbox、真实保存卡 CVV、BIN 识别或 3DS。
- 未执行独立 frontend QA 的广泛 App 回归，也未执行 Admin build/smoke；backend QA 仍为 `paused-by-owner`，E2E 和人工审查尚未开始，因此本交接不代表 QA 或生产上线通过。
- 本任务未修改禁止范围内的生产配置。只读检查发现既有根 `.env.production` 的 `PAYMENT_RAILS_ENABLED=true` 与状态文档要求“全部 QA/人工审查完成前保持关闭”不一致；发布前必须由项目负责人核对并保持支付轨关闭。
- 工作区已有大量未提交和未跟踪改动均已保留；本任务未回退、覆盖或清理无关内容。
