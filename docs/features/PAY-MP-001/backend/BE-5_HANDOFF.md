---
id: PAY-MP-001-BE-5
status: done
owner: backend
---

# BE-5 后端交接

STATUS: done

CHANGED_FILES:
- `csms/app/services/billing_service.py`
- `csms/app/api/v1/app/charging.py`
- `csms/tests/test_billing_service_be5.py`
- `docs/features/PAY-MP-001/STATUS.md`
- `docs/features/PAY-MP-001/backend/TASKS.md`
- `docs/features/PAY-MP-001/backend/BE-5_HANDOFF.md`

COMMANDS_RUN:
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be5-pycache python3 -m py_compile app/services/billing_service.py app/api/v1/app/charging.py tests/test_billing_service_be5.py`
- `python3 -m pytest -q tests/test_billing_service_be5.py --disable-warnings`
- `python3 -m pytest -q tests/test_pricing_modes.py tests/test_p0_app_regressions.py -k 'settle or settlement or pricing' --disable-warnings`
- `python3 -m pytest -q tests/test_user_charging_flow.py tests/test_pricing_modes.py tests/test_p0_app_regressions.py --disable-warnings`
- `python3 -m pytest -q tests/test_database_models.py tests/test_phase4_payment_reliability.py tests/test_production_config.py --disable-warnings`
- `git diff --check -- csms/app/services/billing_service.py csms/app/api/v1/app/charging.py csms/tests/test_billing_service_be5.py`
- `rg -n '^PAYMENT_RAILS_ENABLED|payment_rails_enabled' .env.example .env.production.example csms/app/core/config.py`

TEST_RESULTS:
- BE-5 新增定向测试：5 passed。
- 定价/P0 结算回归：6 passed，覆盖价格快照、免费会话和既有钱包流水链路。
- 充电用户流程、定价和 P0 回归：23 passed。
- 数据模型、支付可靠性和生产配置回归：19 passed。
- Python 语法编译和 scoped diff check：通过。
- `PAYMENT_RAILS_ENABLED` 仍为 `false`，Settings 默认值仍为 `False`。
- 覆盖：余额不足不截断且不建 Payment/钱包流水、足额边界一次性全额扣款、direct-card 无钱包写入且 PaymentOrder 金额等于 Invoice、approved direct-card 收敛、free/0 COP 审计 Payment、free 无 Provider PaymentOrder、重复 settle 和单 Session 唯一 Invoice。
- 后端 QA：按项目负责人要求暂停；未执行独立测试库脏数据检查或真实 Mercado Pago sandbox/Provider 链路验收。

CONTRACT_CHANGES:
- HTTP API：未新增字段；`POST /api/v1/app/charging/settle` 响应补齐冻结契约已有的 `settlement_method`、`payment_status`、`payment_order_id` 和 `next_action` 字段。
- 结算内部行为：Invoice 按 `uq_invoices_session` 幂等创建并作为金额权威；wallet、direct_card、free 使用独立结算分支。
- direct-card：只创建一笔稳定幂等、金额等于 Invoice 的 `PaymentOrder`，不创建 `AppWalletTransaction`；已批准 PaymentOrder 才创建 completed `Payment` 并支付 Invoice/Session。
- free：只允许 0 COP，创建内部 0 COP 审计 `Payment`，不创建 Provider `PaymentOrder` 或钱包流水。
- 数据库模型/迁移：无变化，无新增迁移。
- 配置/生产：未开启支付轨，未操作生产环境或生产数据库。

RISKS:
- BE-5 按任务边界只负责在最终 Invoice 后准备 direct-card PaymentOrder，并对已批准订单做幂等收敛；一次性 Card Token 消费、Provider 创建、processing/action_required/declined/expired 的完整异步反查和 Webhook 收敛属于 BE-6，当前未实现或未声称完成。
- SQLite 测试库不提供完整 PostgreSQL `FOR UPDATE` 并发语义；代码保留 Session 锁、PaymentOrder 幂等键和 `uq_invoices_session` 唯一冲突回读路径，需后端 QA 恢复后在隔离 PostgreSQL 中验证真实并发。
- 后端 QA 按负责人要求暂停；本交接不代表后端 QA、前端 QA 或 E2E 通过。
- 工作区存在其他未提交改动；本任务未回退、覆盖或清理无关文件。

BACKEND_QA_ENTRY_POINT:
- 恢复后在隔离 PostgreSQL/Redis 测试环境运行 `cd csms && pytest -q tests/test_billing_service_be5.py tests/test_pricing_modes.py tests/test_p0_app_regressions.py tests/test_user_charging_flow.py tests/test_database_models.py tests/test_phase4_payment_reliability.py`。
- 使用独立测试库验证同一 Session 并发 settle 仅有一张 Invoice；余额不足无余额/Payment/钱包流水副作用；direct-card 无钱包写入且 PaymentOrder/Invoice/Payment 金额、状态和租户一致；free 仅有 0 COP 审计 Payment。
