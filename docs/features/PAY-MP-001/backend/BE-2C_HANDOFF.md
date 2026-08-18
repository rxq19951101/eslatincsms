---
id: PAY-MP-001-BE-2C
status: done
owner: backend
---

# BE-2C 后端交接

STATUS: done

CHANGED_FILES:
- `csms/app/api/v1/app/payment_checkout.py`
- `csms/app/core/tenant_middleware.py`
- `csms/app/services/payment_checkout/hosted_page.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/tests/test_checkout_session_api.py`
- `docs/features/PAY-MP-001/STATUS.md`
- `docs/features/PAY-MP-001/backend/TASKS.md`
- `docs/features/PAY-MP-001/backend/BE-2C_HANDOFF.md`

COMMANDS_RUN:
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-pycache python3 -m py_compile ...`（BE-2C Python 文件及测试）
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-pycache python3 -m pytest -q tests/test_checkout_session_api.py`
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-pycache python3 -m pytest -q tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_production_config.py tests/test_logging_security.py`
- `git diff --check`（待最终审查执行）

TEST_RESULTS:
- BE-2C/BE-2B 定向测试：14 passed，1 个非失败 warning。
- BE-2A Store、生产配置与日志安全组合测试：31 passed，1 failed；失败为既有 `tests/test_logging_security.py::test_fake_payment_webhook_signature_and_secret_are_redacted` 访问 `/api/v1/app/wallet/payments/sim-webhook` 得到 404，与本任务新增托管页/confirm 无关，未越权修改。
- Python 语法编译：通过。
- 托管页覆盖：MercadoPago.js CardForm/secure fields、saved-card `cardId` token、CSP、安全头、no-store、Token 不进入 HTML/回跳。
- confirm 覆盖：Token 加密存储、CREATED → READY、单次消费、303 EsLatin Deep Link、重复确认失败。
- 后端 QA：按项目负责人指示暂停，未执行独立链路和测试库脏数据检查。

CONTRACT_CHANGES:
- HTTP API：实现冻结契约中的 `GET /api/v1/app/payments/checkout/{signed_token}` 与 `POST /api/v1/app/payments/checkout/{signed_token}/confirm`；未新增字段、错误码或业务扣款行为。
- 安全：签名页面/confirm 由短期 signed token 认证并加入公开路径白名单；页面设置 CSP、frame-ancestors、Referrer-Policy、Cache-Control、nosniff、X-Frame-Options 和 Permissions-Policy。
- Provider：只创建 MercadoPago.js Card Token 并加密暂存 Redis；未调用 Customers/Cards、PaymentOrder、最终扣款或 Webhook。
- 数据库模型/迁移：无变化。
- 配置：无新增配置字段；继续保持 `PAYMENT_RAILS_ENABLED=false`。

RISKS:
- 浏览器实际加载 Mercado Pago 外部 SDK、真实 sandbox 卡 Token、3DS 和 Provider 网络行为尚未执行；当前仅完成服务/API/页面静态与定向测试。
- 后端 QA 仍按负责人要求暂停；本交接不代表 QA 或 E2E 通过。
- `tests/test_logging_security.py::test_fake_payment_webhook_signature_and_secret_are_redacted` 的 404 未在 BE-2C 范围内修复，需后续恢复 QA 时单独确认。
- BE-3 仍需消费 Redis 中的一次性 Token 并实现 Customers/Cards；BE-2C 不应自行扩展该业务。

BACKEND_QA_ENTRY_POINT:
- `cd csms && pytest -q tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_merchant_context.py tests/test_logging_security.py tests/test_production_config.py`
- 重点检查 signed token 无 JWT 依赖、confirm 重放/并发失败关闭、Redis Token 只可消费一次、页面 CSP 不放行任意脚本、saved-card 只显示 CVV secure field，以及真实测试 Redis 中无明文 Token。
