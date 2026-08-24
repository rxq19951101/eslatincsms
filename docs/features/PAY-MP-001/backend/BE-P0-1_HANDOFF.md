# BE-P0-1 后端交接

STATUS: done

CHANGED_FILES:

- `csms/app/services/payment_method_codec.py`
- `csms/app/api/v1/app/payment_checkout.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/app/services/payment_providers/base.py`
- `csms/app/services/payment_providers/mercadopago_provider.py`
- `csms/app/services/payment_reconciliation.py`
- `csms/tests/test_payment_method_codec.py`
- `csms/tests/test_payment_methods.py`
- `csms/tests/test_checkout_session_api.py`
- `csms/tests/test_payment_reconciliation_be6.py`
- `docs/features/PAY-MP-001/STATUS.md`
- `docs/features/PAY-MP-001/backend/TASKS.md`
- `docs/features/PAY-MP-001/backend/BE-P0-1_HANDOFF.md`

COMMANDS_RUN:

- `python3 -m pytest tests/test_payment_methods.py tests/test_checkout_session_api.py tests/test_payment_reconciliation_be6.py -q`（修改前基线）
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-be-p0-1-pycache python3 -m compileall -q ...`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-be-p0-1-pycache python3 -m pytest tests/test_payment_method_codec.py tests/test_payment_methods.py tests/test_checkout_session_api.py tests/test_payment_reconciliation_be6.py -q`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-be-p0-1-pycache python3 -m pytest tests/test_payment_merchant_context.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py tests/test_p0_app_regressions.py -q`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-be-p0-1-pycache python3 -m pytest tests/test_payment_method_codec.py tests/test_payment_methods.py tests/test_checkout_session_api.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py tests/test_payment_merchant_context.py tests/test_p0_app_regressions.py -q`
- 对授权文件执行限定 `rg`、尾随空格检查和 `git diff --check`。

TEST_RESULTS:

- 修改前基线：34 passed。
- 最终定向与相邻支付回归：97 passed，1 个既有 warning；无失败。
- codec fixture：`credit_card`、`debit_card`、`prepaid_card` 均可 v1 编解码；旧纯 brand 和未知 v1 type 均读取为 `payment_type=null`，不猜测、不重写。
- confirm fixture：三类 new-card 均通过；空/未知类型、空 payment method、错误 installments、`save_card` 空 hint 均在 Token 写入前拒绝。
- saved-card fixture：客户端提交 brand/type/issuer 任一覆盖均拒绝，Checkout 仍为 `created`，Redis 中没有 Card Token。
- Provider fixture：三类 Mercado Pago Card 响应均准确投影；brand/type 缺失、未知或与请求 hint 冲突时抛安全 Provider 错误。
- persistence fixture：无效 Provider Card 不创建本地 `AppUserPaymentMethod`；prepaid 保存、列表和 canonical API 投影准确。
- reconciliation fixture：prepaid provider hints 可下传；缺失/未知 type 失败关闭；BE-6/BE-7、MerchantContext 与 P0 App 相邻回归通过。

CONTRACT_CHANGES:

- 无共享 API 字段、路径、状态或错误码变化；只按已冻结契约把现有 `payment_type_id`/`payment_type` 枚举实现扩展为 `credit_card | debit_card | prepaid_card`。
- 无数据库模型、迁移、历史导入或数据重写。
- 无前端/Admin、OCPP/计费状态机、生产配置、真实凭证或 `PAYMENT_RAILS_ENABLED` 变化。
- 新写入 payment method 继续使用现有 `v1:<brand>:<type>` codec；旧记录继续兼容读取为 `payment_type=null`。

RISKS:

- 未执行真实 Mercado Pago sandbox、3DS、真实 Redis/PostgreSQL 并发或独立 `qa-agent` backend scope 回归；后端 QA 仍为 `paused-by-owner`，因此本交接不代表 QA 或生产上线通过。
- `BE-P0-2` 尚未开始；Hosted HTML 中动态证件类型、BIN 三类展示、西语紧凑页面和安全状态页仍由该任务交付。
- `MercadoPagoService` 的旧底层兼容默认仍存在，但所有当前应用支付调用都必须经过 `MercadoPagoProvider`；Provider 现已在调用底层 SDK 前拒绝空/非法 payment method，测试证明该默认在 P0 应用链路不可达。后续若新增直接调用底层 service 的业务入口，必须同样失败关闭。
- 工作区原有大量未提交和未跟踪改动已保留；本任务未回退、覆盖或清理无关内容。
