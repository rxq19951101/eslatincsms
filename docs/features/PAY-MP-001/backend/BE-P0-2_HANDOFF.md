# BE-P0-2 后端交接

STATUS: done

CHANGED_FILES:

- `csms/app/services/payment_checkout/hosted_page.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/app/api/v1/app/payment_checkout.py`
- `csms/tests/test_checkout_session_api.py`
- `docs/features/PAY-MP-001/STATUS.md`
- `docs/features/PAY-MP-001/backend/TASKS.md`
- `docs/features/PAY-MP-001/backend/BE-P0-2_HANDOFF.md`

COMMANDS_RUN:

- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-be-p0-2-pycache python3 -m compileall -q app/services/payment_checkout/hosted_page.py app/services/payment_checkout/service.py app/api/v1/app/payment_checkout.py`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-be-p0-2-pycache python3 -m pytest tests/test_checkout_session_api.py -q`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-be-p0-2-pycache python3 -m pytest tests/test_payment_method_codec.py tests/test_payment_methods.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py tests/test_payment_merchant_context.py tests/test_p0_app_regressions.py -q`
- 分别渲染 new-card 与 saved-card 页面并把 nonce 内联脚本交给 `node --check -`。
- 对授权文件执行敏感字段、旧英文/默认卡类型、隐藏控件、日志调用和尾随空格限定扫描。

TEST_RESULTS:

- Python 编译检查通过。
- Checkout 定向回归：29 passed，0 failed。
- 最终定向与相邻支付回归：108 passed，0 failed，1 个既有 LibreSSL warning。
- new-card 与 saved-card 两种渲染脚本均通过 Node 语法检查。
- 新卡页面动态调用 `getIdentificationTypes`，严格校验非空 Provider 列表并把数据类型、最小长度和最大长度只保留在页面内存；空、非法或加载失败时保持确认禁用。
- BIN 每次变化先清除旧事实；Provider 卡能力只有唯一且完整的 `credit_card | debit_card | prepaid_card` 候选时才允许继续，brand/type/issuer 只读展示，未知、缺失、非法和冲突均失败关闭。
- 托管页为全西语紧凑响应式布局，Secure Fields 固定高度；不显示内部 purpose、手工卡类型/issuer/分期控件或 Provider 原始错误。
- saved-card 页面只显示服务端 brand/type/尾号投影并创建 CVV Secure Field；HTML 不包含卡号、有效期、姓名或证件字段。
- Checkout 创建在读取幂等状态和写 Redis 前冻结单用途矩阵：只有 `save_card + new_card + save_card=true` 合法，其他 purpose 固定 `false`；冲突返回现有 400 `CHECKOUT_REQUEST_INVALID`。
- GET 签名/会话缺失、已提交和不可用分别返回 404/409/503 西语安全状态页；页面不加载 Mercado Pago SDK、不含卡表单、签名 Token 或原始错误，并只使用配置 allowlist 中的 EsLatin Deep Link。
- confirm 严格模型拒绝证件字段并返回 422；证件类型/号码仅在 Hosted 页面内存中传给 MercadoPago.js，不进入 confirm JSON、Checkout Redis state、数据库、日志、分析、审计或 Deep Link。

CONTRACT_CHANGES:

- 无冻结 API 路径、请求字段、响应字段、状态或错误码变化。
- 后端内部 `HostedCheckoutPage` 增加 saved-card canonical payment type 和已校验 return URL，只用于安全渲染。
- 无数据库模型、迁移、历史导入、数据重写或生产配置变化。
- 无 App/Admin、OCPP、计费、C1/C2、D1、退款或欠费 UI 范围变化。
- `PAYMENT_RAILS_ENABLED` 保持关闭。

RISKS:

- 未执行真实 Mercado Pago Colombia sandbox，因此 `getIdentificationTypes`、BIN response、Secure Fields tokenization、Provider 卡片识别和 3DS 的真实运行时返回仍需独立后端 QA 验证；页面遇到任何未识别结构会失败关闭。
- 未执行真实浏览器移动端视觉/键盘/屏幕阅读器测试；开发测试只验证 HTML/CSS/ARIA contract 和 JavaScript 语法。
- 浏览器隐藏手动 303 的 `Location` 时，页面使用已由服务端 allowlist 校验的 return URL 回跳并标记 `processing`，由 App 按既有查询链路恢复真实状态；该分支仍需 WebView/外部浏览器人工验证。
- 未执行真实 Redis/PostgreSQL 并发、隐私代理抓包或脏数据检查；后端 QA 仍为 `paused-by-owner`，本交接不代表 QA、E2E 或生产上线通过。
- 工作区已有大量未提交和未跟踪改动均已保留；本任务未回退、覆盖或清理无关文件。
