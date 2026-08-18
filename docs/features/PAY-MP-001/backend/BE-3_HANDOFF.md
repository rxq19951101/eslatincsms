---
id: PAY-MP-001-BE-3
status: done
owner: backend
---

# BE-3 后端交接

STATUS: done

CHANGED_FILES:
- `csms/app/services/payment_method_codec.py`
- `csms/app/services/payment_methods.py`
- `csms/app/services/payment_providers/base.py`
- `csms/app/services/payment_providers/mercadopago_provider.py`
- `csms/app/services/mercadopago_service.py`
- `csms/app/api/v1/app/payment_methods.py`
- `csms/app/api/v1/app/wallet.py`
- `csms/app/api/v1/__init__.py`
- `csms/app/services/payment_checkout/models.py`
- `csms/app/services/payment_checkout/redis_store.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/tests/test_payment_methods.py`
- `docs/features/PAY-MP-001/STATUS.md`
- `docs/features/PAY-MP-001/backend/TASKS.md`
- `docs/features/PAY-MP-001/backend/BE-3_HANDOFF.md`

COMMANDS_RUN:
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be3-pycache python3 -m py_compile ...`（BE-3 Python 文件及测试）
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be3-pycache python3 -m pytest -q tests/test_payment_methods.py --disable-warnings`
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-be3-pycache python3 -m pytest -q tests/test_payment_methods.py tests/test_payment_merchant_context.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_logging_security.py tests/test_production_config.py --disable-warnings`
- `git diff --check`（BE-3 相关跟踪文件）

TEST_RESULTS:
- BE-3 新增测试：6 passed。
- BE-3 与 BE-1/BE-2 定向回归：45 passed，1 个非失败 warning。
- 覆盖集中 brand/payment_type codec、旧 brand 读取、Customers/Cards Adapter、Customer 复用、首卡默认、默认卡切换、删除后默认卡重选、Provider 已删除幂等、跨用户隔离、API 兼容读取和 hosted save-card Token 单次消费。
- Python 语法编译和 diff check：通过。
- 后端 QA：按项目负责人指示暂停，未执行独立测试库脏数据检查或真实 Mercado Pago sandbox/3DS 验证。

CONTRACT_CHANGES:
- HTTP API：实现冻结契约中的 `GET /api/v1/app/payment-methods`、`PATCH /api/v1/app/payment-methods/{payment_method_id}`、`DELETE /api/v1/app/payment-methods/{payment_method_id}`；写操作要求 `Idempotency-Key`，跨用户/不存在资源统一安全返回 404；未新增契约字段。
- 兼容 API：`GET /api/v1/app/wallet/saved-payment-methods` 改为读取同一 canonical projection，返回兼容旧字段并补充 brand/payment_type，标记弃用。
- Provider：Mercado Pago Adapter 增加 Customers/Cards create/delete，凭证仍只在 merchant-context/provider 边界解析；Provider 404 删除按幂等成功处理。
- 内部状态：保存卡 hosted confirm 成功后发布 `saved_payment_method_id` 并允许 Checkout `ready -> approved`；Card Token 仍加密存储并原子消费，不进入数据库、日志或响应。
- 数据库模型/迁移：无变化；复用 `app_user_payment_methods.payment_method_brand` 保存 `v1:<brand>:<payment_type>`，旧纯 brand 值读取时 `payment_type=null`。
- 配置/开关：无新增生产秘密；`PAYMENT_RAILS_ENABLED` 保持关闭。

RISKS:
- 后端 QA 当前暂停；本交接不代表后端 QA、前端 QA 或 E2E 通过。
- 真实 Mercado Pago Customers/Cards sandbox、Provider 风控和 3DS 尚未执行；当前仅使用安全 fake/provider adapter 测试。
- BE-4/BE-6 仍需消费 direct-card checkout 的一次性 Token；BE-3 只在 `purpose=save_card` 的 hosted confirm 中消费 Token 并创建 Card，未实现后续充电支付意图或最终扣款。
- 无迁移兼容 codec 是当前设计折中；未来如需要独立 payment_type 字段，应通过批准的迁移替换，而不是并行手工拆分。

BACKEND_QA_ENTRY_POINT:
- `cd csms && pytest -q tests/test_payment_methods.py tests/test_payment_merchant_context.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_logging_security.py tests/test_production_config.py`
- 使用隔离测试库核对每个 AppUser 只能读取和修改自己的 payment method；检查默认卡删除后的唯一默认投影、Provider 已删除卡的本地清理、重复 confirm 的单次 Token 消费和 Redis 中不存在明文 Token。
- 使用测试 Provider/Redis 验证 merchant context、credential handle、Card Token、PAN/CVV 和完整 Provider 响应不进入日志、数据库或 API 响应。
