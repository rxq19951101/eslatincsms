---
id: PAY-MP-001-BE-4
status: done
owner: backend
---

# BE-4 后端交接

STATUS: done

CHANGED_FILES:
- `csms/app/services/charging_payment_intent.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/app/api/v1/app/charging.py`
- `csms/app/services/session_service.py`
- `csms/tests/test_charging_payment_intent.py`
- `csms/tests/test_checkout_session_api.py`
- `docs/features/PAY-MP-001/STATUS.md`
- `docs/features/PAY-MP-001/backend/TASKS.md`
- `docs/features/PAY-MP-001/backend/BE-4_HANDOFF.md`

COMMANDS_RUN:
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be4-pycache python3 -m py_compile app/services/charging_payment_intent.py app/services/payment_checkout/service.py app/api/v1/app/charging.py app/services/session_service.py tests/test_charging_payment_intent.py tests/test_checkout_session_api.py`
- `git diff --check -- app/services/charging_payment_intent.py app/services/payment_checkout/service.py app/api/v1/app/charging.py app/services/session_service.py tests/test_charging_payment_intent.py tests/test_checkout_session_api.py`
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be4-pycache python3 -m pytest -q tests/test_charging_payment_intent.py tests/test_checkout_session_api.py -k 'payment_intent or direct_checkout_confirm' --disable-warnings`
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be4-pycache python3 -m pytest -q tests/test_charging_payment_intent.py tests/test_user_charging_flow.py tests/test_ocpp_message_handler.py tests/test_checkout_session_store.py --disable-warnings`
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be4-pycache python3 -m pytest -q tests/test_checkout_session_api.py tests/test_p0_app_regressions.py -k 'start_charging or direct_checkout or checkout or remote_start' --disable-warnings`
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be4-pycache python3 -m pytest -q tests/test_charging_payment_intent.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_user_charging_flow.py --disable-warnings`

TEST_RESULTS:
- BE-4 定向范围：7 passed，覆盖 Intent 创建、用户/租户/桩/connector 归属、余额为零的 direct-card 启动、过期、RemoteStart 拒绝回退、重放和 StartTransaction 单次绑定。
- 架构复核回归：新增 Order 已提交但 Redis `update_record` 失败后的恢复测试；恢复通过可信 `checkout_session_id` 和用户/桩/租户/connector 过滤找回同一 Intent，未重复创建 Order。相关 BE-4/Checkout/Store/用户充电定向集合：34 passed。
- Checkout/P0 定向回归：19 passed。
- 充电/OCPP/Checkout Store 组合回归：23 passed，1 failed；既有 `tests/test_ocpp_message_handler.py::TestOCPPMessageHandler::test_handle_start_transaction` 使用未 commissioned fixture，实际返回 `CHARGER_NOT_COMMISSIONED`/`Rejected`，测试断言未允许 `Rejected`。该失败发生在 BE-4 Intent 查找之前，与本次改动无关，未静默修改。
- Python 语法编译和 scoped diff check：通过。
- 后端 QA：按项目负责人要求暂停；未执行独立测试库脏数据检查、真实 Provider sandbox 或生产验证。

CONTRACT_CHANGES:
- HTTP API：实现冻结 `POST /api/v1/app/charging/start` 的 `settlement_method` 与 `payment_intent_id` 请求字段；未新增字段、错误码或迁移。旧请求默认 `wallet` 保持兼容。
- 内部状态：新增版本化 `schema_version=1` 的 Charging Payment Intent 安全 JSON，复用 `Order.pre_authorization` 和 `Order.session_id`；状态覆盖 `ready → start_requested → bound`，RemoteStart 失败可回 `ready`，过期为 `expired`。
- Checkout：`charging_direct` hosted confirm 后创建持久 Order Intent，并在 checkout 查询结果发布 `payment_intent_id`；Card Token 仍只留在既有加密 Redis Token 仓库，BE-6 负责最终支付消费。
- 数据库/迁移：无模型字段变化、无迁移、无生产数据库操作。
- 配置：`PAYMENT_RAILS_ENABLED` 未修改，继续保持关闭。

RISKS:
- 后端 QA 仍暂停；本交接不代表后端 QA、前端 QA、E2E 或生产验收通过。
- OCPP 组合回归保留 1 个既有 fixture/断言失败，需后端 QA 恢复后按现有测试责任单独确认。
- 同一进程内通过 ChargePoint 行锁和 Intent 状态防止并发重复 RemoteStart；多进程 PostgreSQL 锁语义需要后端 QA 在真实数据库验证。SQLite 测试库不提供完整 `FOR UPDATE` 语义。
- 既有全局 HTTPException handler 仍负责 legacy API envelope；BE-4 未改动全局异常基础设施。
- BE-5/BE-6 尚未实现最终 Invoice/PaymentOrder/Provider 扣款和 D1 全局欠费收敛；不得开启支付轨或把本交接视为完整支付链路完成。

BACKEND_QA_ENTRY_POINT:
- `cd csms && pytest -q tests/test_charging_payment_intent.py tests/test_checkout_session_api.py tests/test_user_charging_flow.py tests/test_ocpp_message_handler.py tests/test_checkout_session_store.py`
- 在隔离 PostgreSQL/Redis 中验证 ChargePoint 行锁下的双请求竞争、不同 connector/tenant/user 归属、Intent 过期、StartTransaction 重放及 Order/Session/Intent 数量和状态。
- 检查 `orders.pre_authorization` 与 Redis 中不含 PAN、CVV、明文 Card Token、Access Token、credential handle 或完整 Provider response。
