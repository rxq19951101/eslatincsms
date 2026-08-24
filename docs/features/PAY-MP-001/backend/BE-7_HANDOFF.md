---
id: PAY-MP-001-BE-7
status: done
owner: backend
---

# BE-7 后端交接

STATUS: done

CHANGED_FILES:
- `csms/app/api/v1/admin/payments.py`
- `csms/app/api/v1/app/payments.py`
- `csms/app/api/v1/app/wallet.py`
- `csms/app/services/billing_service.py`
- `csms/app/services/mercadopago_service.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/app/services/payment_providers/base.py`
- `csms/app/services/payment_providers/mercadopago_provider.py`
- `csms/app/services/payment_reconciliation.py`
- `csms/app/services/payment_refunds.py`
- `csms/tests/test_payment_refunds_be7.py`
- `docs/features/PAY-MP-001/STATUS.md`
- `docs/features/PAY-MP-001/backend/TASKS.md`
- `docs/features/PAY-MP-001/backend/BE-7_HANDOFF.md`

COMMANDS_RUN:
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be7-pycache python3 -m py_compile ...`（BE-7 Python 实现及测试）
- `git diff --check`
- `cd csms && python3 -m pytest -q tests/test_payment_refunds_be7.py tests/test_billing_service_be5.py tests/test_payment_reconciliation_be6.py --disable-warnings`（15 passed）
- `cd csms && python3 -m pytest -q tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_methods.py tests/test_payment_merchant_context.py tests/test_production_config.py --disable-warnings`
- `cd csms && python3 -m pytest -q tests/test_payment_refunds_be7.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_reconciliation_be6.py tests/test_billing_service_be5.py tests/test_phase4_payment_reliability.py tests/test_logging_security.py tests/test_production_config.py --disable-warnings`（58 passed）
- `rg -n '^PAYMENT_RAILS_ENABLED|payment_rails_enabled' csms/app/core/config.py csms/.env.example csms/env.example .env.example .env.production.example`

TEST_RESULTS:
- BE-7 新增定向测试：5 passed，包含保存 Mastercard/借记卡欠费补缴 provider hint 回归。
- BE-5/BE-6 直接回归：15 passed。
- Checkout/Redis/支付方式/MerchantContext/生产配置：40 passed。
- BE-7 组合定向回归（含支付可靠性和日志安全）：58 passed，1 个既有非失败 warning。
- Python 语法编译和 diff check：通过。
- `PAYMENT_RAILS_ENABLED` 仍为 `false`，Settings 默认值仍为 `False`。
- 后端 QA：按项目负责人要求暂停；未执行独立测试库脏数据、真实 Mercado Pago sandbox/3DS、真实 Provider refund API 或 PostgreSQL 并发验收。

CONTRACT_CHANGES:
- HTTP API：未新增路径或响应字段；兼容 `POST /api/v1/app/wallet/pay-unpaid-charge` 现在要求 `Idempotency-Key`，返回 Invoice 权威金额和结算结果；管理员退款继续使用既有路径并要求 `Idempotency-Key`。
- 欠费补缴：欠费列表和钱包补缴只读取同租户唯一 Invoice；钱包补缴锁定 AppUser、ChargingSession、Invoice，余额不足返回 402 且不产生账务副作用；托管 `unpaid_charge` 确认创建独立 direct-card PaymentOrder，并复用 BE-6 reconcile。
- 退款：新增 Provider refund facts/create 能力；退款前后主动查询 Provider 累计退款额，使用 PaymentOrder metadata 的版本化摘要串行累计；全额退款才投影 PaymentOrder/Invoice 为 `refunded`，部分退款保持 `approved`。
- 钱包充值退款：锁定余额并在余额不足时进入人工异常，不调用 Provider、不产生负余额；成功后使用现有钱包流水结构表达累计冲回，不新增迁移。
- 重复 approved：保留 BE-6 `settlement_exception=duplicate_approved` 安全策略，增加 `refund_required` 标记并尝试通过 BE-7 refund service 自动退款；Provider 能力/事实不一致时保留人工异常。
- Provider hints：欠费 PaymentOrder metadata 中只保留服务端校验后的 canonical provider hints；保存卡在当前用户与 Mercado Pago provider 约束下重新读取本地投影，metadata hints 优先于旧 Charging Order hints；无效 metadata fail-closed，禁止隐式回退 visa。
- 数据库/迁移：无模型字段变化，无新增迁移；仅复用 `PaymentOrder.metadata` 和现有钱包流水。
- 配置/生产：未修改支付开关为开启，未部署生产，未操作生产数据库。

RISKS:
- 后端 QA 仍暂停；本交接不代表后端 QA、前端 QA、E2E 或生产验收通过。
- 当前本地测试使用 SQLite、fake Provider 和 fake Redis；Provider refund 列表/创建、3DS、网络超时和 PostgreSQL `FOR UPDATE` 语义尚未真实验证。
- Mercado Pago SDK 的退款事实查询依赖其 `refund().list_all(payment_id)` 能力；Provider 返回累计额与本地 metadata 不一致时系统故意失败关闭并要求人工处理，可能需要运维重试/核对。
- 无迁移阶段的 refund summary 仅为可审计摘要，Provider 事实始终优先；未来应在批准迁移后拆分 RefundAttempt/Refund 事实模型。
- 现有工作区包含其他未提交前后端改动；本任务未回退、覆盖或清理无关修改。

BACKEND_QA_ENTRY_POINT:
- 优先运行：`cd csms && pytest -q tests/test_payment_refunds_be7.py tests/test_payment_reconciliation_be6.py tests/test_billing_service_be5.py tests/test_checkout_session_api.py tests/test_payment_methods.py tests/test_production_config.py`
- 在隔离 PostgreSQL/Redis/Provider sandbox 中核对：同一 Invoice 只有一次成功钱包入账；并发钱包补缴不重复扣款；多个银行卡 PaymentOrder 只有首个 approved 结清 Invoice；重复 approved 自动退款失败时保留人工异常；Provider/metadata 累计退款不一致拒绝继续；充值退款余额不足不调用 Provider且余额不为负。
