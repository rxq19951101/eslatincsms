---
id: PAY-MP-001-BE-2A
status: done
owner: backend
---

# BE-2A 后端交接

STATUS: done

CHANGED_FILES:
- `.env.example`
- `.env.production.example`
- `csms/app/core/config.py`
- `csms/app/services/payment_checkout/__init__.py`
- `csms/app/services/payment_checkout/models.py`
- `csms/app/services/payment_checkout/crypto.py`
- `csms/app/services/payment_checkout/redis_store.py`
- `csms/tests/test_checkout_session_store.py`

COMMANDS_RUN:
- bundled Python 3 `py_compile`（BE-2A Python 文件）
- `git diff --check`（BE-2A 与 PAY-MP-001 文档）
- 使用真实 cryptography/Fernet、stub Redis/config 的加密仓库 smoke

TEST_RESULTS:
- Python 语法编译：通过。
- diff check：通过。
- 加密 Checkout Session 保存/读取：通过。
- CREATED → READY compare-and-set 状态迁移：通过。
- Card Token 密文不含明文、首次原子消费成功、第二次消费失败：通过。
- `csms/tests/test_checkout_session_store.py` 已覆盖幂等复用/冲突、篡改、过期、Redis 故障、非法状态迁移和敏感字段拒绝；当前环境缺 pytest/完整后端依赖，因此该 pytest 文件未执行。
- 后端 QA：按项目负责人指示暂停，未介入。

CONTRACT_CHANGES:
- HTTP API：无。
- 数据库模型/迁移：无。
- 内部契约：新增版本化 CheckoutSessionRecord、显式状态机、独立 PaymentTokenCipher、失败关闭 Redis Store 和安全异常。
- 配置：新增 `CHECKOUT_SESSION_TTL_SECONDS` 与 `PAYMENT_TOKEN_ENCRYPTION_KEY`；不生成生产默认密钥。

RISKS:
- 当前 Redis Store 只提供基础设施；BE-2B 接入 API 时必须从认证上下文构造 app_user_id，并验证 return URL、purpose、金额和业务目标。
- Redis 幂等索引只保存请求指纹和 opaque id；业务请求规范化规则由 BE-2B 固化。
- 状态和 Card Token 使用同一独立支付 Token Fernet 密钥；不得复用设备 `ENCRYPTION_KEY`。
- 完整 pytest 尚未运行；这是已知工程测试缺口，后端 QA 又处于项目负责人暂停状态。
- `PAYMENT_RAILS_ENABLED` 保持关闭。

BACKEND_QA_ENTRY_POINT:
- QA 恢复后运行：`cd csms && pytest -q tests/test_checkout_session_store.py tests/test_payment_merchant_context.py tests/test_logging_security.py tests/test_production_config.py`
- 检查 Redis 中只存在密文状态、哈希幂等键和密文 Card Token；重复消费、篡改与 Redis 故障全部失败关闭。
