---
id: PAY-MP-001-BE-6
status: done
owner: backend
---

# BE-6 后端交接

STATUS: done

CHANGED_FILES:
- `csms/app/services/payment_reconciliation.py`
- `csms/app/services/billing_service.py`
- `csms/app/services/payment_providers/base.py`
- `csms/app/services/payment_providers/mercadopago_provider.py`
- `csms/app/services/mercadopago_service.py`
- `csms/app/api/v1/app/payments.py`
- `csms/app/api/v1/app/charging.py`
- `csms/app/api/v1/admin/payments.py`
- `csms/tests/test_payment_reconciliation_be6.py`
- `docs/features/PAY-MP-001/STATUS.md`
- `docs/features/PAY-MP-001/backend/TASKS.md`
- `docs/features/PAY-MP-001/backend/BE-6_HANDOFF.md`

COMMANDS_RUN:
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be6-pycache python3 -m py_compile app/services/payment_reconciliation.py app/services/payment_providers/base.py app/services/payment_providers/mercadopago_provider.py app/services/mercadopago_service.py app/services/billing_service.py app/api/v1/app/charging.py app/api/v1/app/payments.py app/api/v1/admin/payments.py`
- `python3 -m pytest -q tests/test_payment_reconciliation_be6.py --disable-warnings`
- `python3 -m pytest -q tests/test_payment_reconciliation_be6.py tests/test_billing_service_be5.py tests/test_charging_payment_intent.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_methods.py tests/test_payment_merchant_context.py tests/test_production_config.py tests/test_logging_security.py --disable-warnings`
- `git diff --check --`（BE-6 相关实现与测试文件）
- `rg -n '^PAYMENT_RAILS_ENABLED|payment_rails_enabled' .env.example .env.production.example csms/app/core/config.py`

TEST_RESULTS:
- BE-6 定向测试：10 passed。
- BE-5 结算、Charging Payment Intent、Checkout Session/Redis、支付方式、MerchantContext、生产配置和日志安全组合回归：68 passed，1 个非失败 warning。
- 覆盖：Invoice 准确金额和 direct-card PaymentOrder 一致、一次性 Card Token 消费、Provider 状态投影、Action Required URL 白名单、统一 reconcile、Webhook 事实校验所需的商户/金额/币种/归属保护、乱序状态不回退、首个 approved 获胜与后续 approved 异常标记、全局 D1 事实门禁。
- 后端 QA：按项目负责人要求暂停；未执行独立后端 QA、测试库脏数据检查、真实 Mercado Pago sandbox/3DS 或生产验证。

CONTRACT_CHANGES:
- HTTP API：未新增路径、请求字段或错误码；支付状态响应补齐冻结契约已有的 purpose/status_detail/invoice/session/next_action 投影字段。
- Provider：Mercado Pago Provider 增加安全状态反查、签名校验和安全 next-action 提取；Webhook 改为先按订单快照解析 MerchantContext，再验签和主动反查。
- 业务：统一 `PaymentReconciliationService` 负责 direct-card Token 消费、Provider 创建、Webhook/状态/管理员对账收敛；approved 只在 Invoice 未入账时创建 Payment，重复 approved 写入非敏感异常摘要，不重复入账。
- D1：充电启动和充电状态检查依据跨租户 Invoice/ChargingSession 事实查询欠费，不依赖 `AppUser.has_unpaid_charges`，不按站点缩小范围。
- 数据库/迁移：无模型字段变化、无迁移；Webhook 只保存精简事件信封，不保存原始 Provider 响应。
- 敏感数据：PAN、CVV、Card Token、Access Token、credential handle 和完整 Provider 响应未写入数据库或日志；Card Token 仍只从加密 Redis 单次消费。
- 配置：`PAYMENT_RAILS_ENABLED` 未修改，继续保持关闭。

RISKS:
- 后端 QA 继续暂停；本交接不代表后端 QA、前端 QA、E2E 或生产验收通过。
- 真实 Mercado Pago provider、3DS、Webhook 网络签名和 PostgreSQL 并发锁语义尚未在本地验证；当前测试使用隔离 SQLite 与 fake Provider。
- BE-5 为兼容既有测试/旧数据保留了缺少 checkout/token 关联的 direct-card prepare-only 订单；BE-6 不会对缺少可信 checkout 关联的订单猜测卡数据或发起扣款，BE-7 应为欠费重试创建新的完整支付尝试。
- 重复 approved 当前进入 `settlement_exception=duplicate_approved` 非敏感异常摘要和高优先级日志，自动退款属于 BE-7 范围。

BACKEND_QA_ENTRY_POINT:
- 恢复后运行上述 68-test 定向集合，并在隔离 PostgreSQL/Redis 中验证 Webhook 验签、重放/乱序、金额/币种/merchant snapshot/tenant/session 归属不匹配、同 Invoice 多 PaymentOrder 竞争、Redis Token 原子消费及无重复 Payment/钱包流水。
- 重点核对 `PaymentWebhookEvent.payload` 仅含 provider/event 最小信封；订单 metadata 只含 merchant safe snapshot、Invoice/Session/tenant/purpose 和状态摘要。
