---
id: PAY-MP-001-BE-1
status: done
owner: backend
---

# BE-1 后端交接

STATUS: done

CHANGED_FILES:
- `.env.example`
- `.env.production.example`
- `csms/app/core/config.py`
- `csms/app/core/log_sanitization.py`
- `csms/app/services/mercadopago_service.py`
- `csms/app/services/payment_providers/base.py`
- `csms/app/services/payment_providers/credential_resolver.py`
- `csms/app/services/payment_providers/merchant_context.py`
- `csms/app/services/payment_providers/mercadopago_provider.py`
- `csms/tests/test_logging_security.py`
- `csms/tests/test_payment_merchant_context.py`
- `csms/tests/test_production_config.py`

COMMANDS_RUN:
- `git diff --check`（BE-1 限定文件）
- bundled Python 3 `py_compile`（BE-1 Python 文件）
- MerchantContext、tenant-required 和日志脱敏无依赖 smoke 检查
- `pytest -q tests/test_payment_merchant_context.py tests/test_logging_security.py tests/test_production_config.py tests/test_phase4_payment_reliability.py`

TEST_RESULTS:
- diff check：通过。
- Python 语法编译：通过。
- MerchantContext C1、安全快照、charging tenant-required：通过。
- Card Token/credential handle/client secret 脱敏 smoke：通过。
- pytest：未执行；当前本机 Python 无 pytest/后端依赖，当前 shell 也没有 Docker 命令。该环境限制不是测试通过，必须由后端 QA 记录为阻塞或在具备依赖的测试环境补跑。

CONTRACT_CHANGES:
- HTTP API：无。
- 数据模型/数据库/迁移：无。
- 内部契约：新增 MerchantContext、MerchantAccountResolver、CredentialResolver 和安全 Provider 错误；Mercado Pago Service 改为按 MerchantContext 创建，不再缓存全局 SDK/密钥。
- 配置：Settings 新增现有 Mercado Pago 环境变量的类型化字段；生产环境仅在支付轨开启时强制完整凭证。

RISKS:
- 旧支付/Webhook/退款路由尚未提供可信 tenant，因此保留 C1 平台商户兼容桥；新链路必须显式传 MerchantContext，兼容桥计划在 BE-6 删除。
- 完整 pytest 尚未在当前执行环境运行，不能据此宣称后端 QA 通过。
- `PAYMENT_RAILS_ENABLED` 必须保持关闭。

BACKEND_QA_ENTRY_POINT:
- 优先运行：`cd csms && pytest -q tests/test_payment_merchant_context.py tests/test_logging_security.py tests/test_production_config.py tests/test_phase4_payment_reliability.py`
- 再检查：无 API/数据库写入变化；缺密钥和错误 handle 失败关闭；日志中不存在 Access Token、Card Token、credential handle、Webhook secret 或完整 Provider response。
