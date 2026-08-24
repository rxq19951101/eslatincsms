---
id: PAY-MP-001-BE-2B
status: done
owner: backend
---

# BE-2B 后端交接

STATUS: done

CHANGED_FILES:
- `.env.example`
- `.env.production.example`
- `docker-compose.prod.yml`
- `csms/app/core/config.py`
- `csms/app/core/log_sanitization.py`
- `csms/app/core/tenant_middleware.py`
- `csms/app/api/v1/__init__.py`
- `csms/app/api/v1/app/payment_checkout.py`
- `csms/app/services/payment_checkout/__init__.py`
- `csms/app/services/payment_checkout/redis_store.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/app/services/payment_checkout/signing.py`
- `csms/tests/test_checkout_session_api.py`
- `csms/tests/test_checkout_session_store.py`
- `csms/tests/test_production_config.py`
- `csms/tests/test_logging_security.py`
- `docs/features/PAY-MP-001/backend/BE-2B_HANDOFF.md`

COMMANDS_RUN:
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-pycache python3 -m py_compile ...`（BE-2B Python 文件）
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-pycache python3 -m pytest -q tests/test_checkout_session_api.py`
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-pycache python3 -m pytest -q tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_production_config.py tests/test_user_flow.py::test_device_registration_requires_admin_auth tests/test_user_flow.py::test_order_list_requires_admin_auth`
- `PYTHONPYCACHEPREFIX=/tmp/pay-mp-pycache python3 -m pytest -q tests/test_logging_security.py::test_payment_credentials_and_card_tokens_are_explicitly_redacted tests/test_logging_security.py::test_api_logging_recursively_redacts_nested_values_and_prefixes`
- `git diff --check -- ...`（BE-2B 已跟踪文件）
- `rg -n '[[:blank:]]+$' ...`（BE-2B 新增文件尾随空白检查）
- 尝试包含 `tests/test_payment_merchant_context.py` 的支付组合测试；宿主 Python 3.9 在收集既有 BE-1 `MerchantContext | None` 注解时失败，未执行到测试体。

TEST_RESULTS:
- BE-2B/BE-2A Store/生产配置及共享认证兼容定向测试：24 passed，1 个非失败 warning。
- 支付敏感信息日志定向测试：2 passed。
- Python 语法编译：通过。
- scoped `git diff --check`：通过。
- BE-2B 新增文件尾随空白检查：通过（无匹配）。
- 创建 API 覆盖：严格请求模型、UUID v4 幂等键、Decimal 字符串、目的/目标组合、return URL 白名单、支付轨开关，以及未认证/无效 AppUser/校验失败的冻结错误体。
- 服务覆盖：同请求幂等复用、冲突 409、重放优先读取原有效会话、用户隔离、保存卡归属、可信桩/枪口/租户/当前 PAID 价格推导、FREE 定价拒绝、ChargePoint-Site 与 unpaid Invoice-Session 租户一致性失败关闭。
- 安全覆盖：HMAC URL 篡改/过期、签名载荷最小化、签名 URL 路径日志脱敏、Redis 密文、商户快照无 credential handle、next-action HTTPS/Host 白名单、恶意 PAN 额外字段拒绝。
- 后端 QA：按项目负责人指示继续暂停，未执行独立 QA 或测试库脏数据检查。

CONTRACT_CHANGES:
- HTTP API：按冻结契约新增 `POST /api/v1/app/payments/checkout-sessions` 与 `GET /api/v1/app/payments/checkout-sessions/{checkout_session_id}`；未实现 BE-2C HTML/confirm。
- 冻结错误体：checkout create/query 路径的未认证、无效认证和路由依赖 `HTTPException` 均稳定返回 `{detail:{code,message}}`；未修改全局异常处理，其他 API 的既有认证错误体保持不变。
- 公共字段：无未批准变更；金额输入要求十进制字符串，币种固定 COP，结果 ID 初始为空并由后续 confirm 填充。
- 内部契约：BE-2A Store 新增按 AppUser + 哈希幂等键预读有效会话；新增 CheckoutSessionService 与短期 HMAC URL signer。
- 配置：新增 `PUBLIC_API_BASE_URL` Settings 映射、`CHECKOUT_SIGNING_KEY`、return URL/next-action Host 白名单及可配置钱包充值技术边界；生产支付轨开启时校验 HTTPS、Fernet key 和签名 key。
- 数据库模型/迁移：无变化。
- 前端：无变化。

RISKS:
- `PAYMENT_RAILS_ENABLED` 保持 false；未开启支付轨、未部署生产。
- BE-2B 返回的托管 checkout URL 在 BE-2C 完成前没有 HTML/confirm 处理端点，这是任务拆分预期，不可用于真实支付。
- 宿主只有 Python 3.9，项目容器目标为 Python 3.11；既有 BE-1 `mercadopago_service.py` 在 3.9 收集时触发 PEP 604 运行期注解错误，因此 `test_payment_merchant_context.py` 和依赖旧支付路由的完整日志测试无法在本机完整执行。当前环境没有 Docker，未能改用项目 3.11 容器复核；未越权修改 BE-1 文件。
- 钱包充值默认上下限采用现有 `Numeric(10,2)` 可表达的技术范围 `0.01..99999999.99 COP`，均可通过服务端配置收紧；未擅自增加产品金额限制。
- 后端 QA 和测试库数据完整性检查仍按负责人指示暂停；本交接不代表 QA 或 E2E 通过。

BACKEND_QA_ENTRY_POINT:
- QA 恢复后优先运行：`cd csms && pytest -q tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_merchant_context.py tests/test_logging_security.py tests/test_production_config.py`
- 使用隔离 Redis 验证状态/幂等索引均为密文或哈希，不含邮箱、Card Token、credential handle；验证同用户复用、跨用户 404、同键冲突 409、TTL 过期和 Redis 故障失败关闭。
- 使用测试数据库验证 charging_direct 的 ChargePoint/EVSE/tenant/pricing 全部服务端推导且仅接受 `PricingMode.PAID`，ChargePoint-Site 租户不一致失败关闭；验证 unpaid_charge 金额只来自当前用户同租户 pending Invoice，Invoice-Session 租户不一致失败关闭，且 BE-2B 不产生 Order、PaymentOrder、Payment、钱包流水或模型变化。
