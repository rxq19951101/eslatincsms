---
id: PAY-MP-001
change_id: CHG-20260817-PAY-API-GOVERNANCE
task: backend-independent-qa
scope: backend
status: blocked
owner: qa-agent-lovelace
reviewed_at: 2026-08-18
verdict: blocked
---

# PAY-MP-001 后端独立 QA 报告

## STATUS

`STATUS: blocked`

本次 focused recheck 已确认 Mercado Pago Webhook 验签改用 `hmac.compare_digest`，新增回归测试通过，QA-BE-PAY-001 已 `resolved`。指定测试与支付核心回归全部通过；本轮补充复核了 test Compose、Sandbox payment query、真实 Webhook 落库事实及当前工作树源对齐的 PG/Redis 受限检查；QA-BE-PAY-EXT-001 已通过回归验证为 `resolved`，但真实 Provider refund/partial/duplicate/timeout/unknown mutation 仍未验证，整体不得宣称生产通过。

本轮进一步执行了迁移以外的全部 CSMS backend tests 和全部 charger-sim tests。支付相关门禁保持通过，但广义 backend 全套为 `535 passed / 6 failed`；定向复核确认 favorites 站点 404 与两项 UUID boundary 失败稳定存在，pricing modes 的三项失败在定向运行中通过，报告不将广义 backend 全套记为通过。

原始范围已保持：未创建 Agent，未修改业务代码、业务测试、生产配置、数据库结构或测试结果；仅更新本报告。未解决的外部运行时证据缺口没有被伪造成通过。

## Focused recheck

- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-recheck-pycache python3 -m pytest tests/test_payment_merchant_context.py -q`
  - `13 passed, 0 failed, 1 warning, 0.18s`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-recheck-pycache python3 -m pytest tests/test_payment_method_codec.py tests/test_payment_methods.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py tests/test_payment_merchant_context.py tests/test_p0_app_regressions.py tests/test_billing_service_be5.py tests/test_charging_payment_intent.py tests/test_payment_interface_governance.py tests/test_phase4_payment_reliability.py -q`
  - `132 passed, 0 failed, 1 warning, 17.35s`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-recheck-pycache python3 -m compileall -q app/services/mercadopago_service.py tests/test_payment_merchant_context.py`
  - exit `0`
- `git diff --check -- csms/app/services/mercadopago_service.py csms/tests/test_payment_merchant_context.py`
  - exit `0`
- 定向扫描结果：`hmac.compare_digest` 出现在实现和回归测试中；旧 `calculated_hash == hash_v1` 无命中。

### 本轮 backend QA rerun（2026-08-18 UTC）

- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-refund-recheck-2-pycache python3 -m pytest tests/test_payment_merchant_context.py tests/test_payment_refunds_be7.py -q`
  - `21 passed, 0 failed, 1 warning, 1.28s`；QA-BE-PAY-EXT-001 的 JSONDecodeError 与 HTTP 200 非集合响应失败关闭回归通过。
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-core-recheck-2-pycache python3 -m pytest tests/test_payment_method_codec.py tests/test_payment_methods.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py tests/test_payment_merchant_context.py tests/test_p0_app_regressions.py tests/test_billing_service_be5.py tests/test_charging_payment_intent.py tests/test_payment_interface_governance.py tests/test_phase4_payment_reliability.py -q`
  - `135 passed, 0 failed, 1 warning, 17.85s`。
- `docker compose --env-file .env.test.local -f docker-compose.test.yml config --quiet`：exit `0`；`docker compose --env-file .env.test.local -f docker-compose.test.yml ps --all`：CSMS、PostgreSQL、Redis、MQTT healthy；未重启容器，未执行 entrypoint/migration。
- `curl -sS --max-time 15 -w '\nLOCAL_HEALTH_STATUS=%{http_code}\n' http://localhost:8001/health` 与 `curl -sS --max-time 15 -w '\nTUNNEL_HEALTH_STATUS=%{http_code}\n' https://sandbox-api.eslatin.com.co/health`：分别 HTTP `200`；database/redis 为 `ok`，websocket 为 `configured`。
- 本轮未调用真实退款创建/退款 mutation；3DS/hosted return/saved-card CVV、真实 Webhook `X-Signature`/`X-Request-Id`、PG/Redis 业务并发均无新增可验证证据，继续标记 `untested/blocked`。

### Exhaustive local backend QA（2026-08-18 UTC，有界完成）

- 全部 CSMS backend tests（排除唯一迁移测试 `tests/test_pay_mp_002_be201_schema.py`）：
  `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-all-backend-pycache python3 -m pytest tests --ignore=tests/test_pay_mp_002_be201_schema.py -q`
  - 收集 `541`；`535 passed, 6 failed, 20 warnings, 142.10s`。支付相关测试、支付核心、退款、Webhook、幂等、金额边界和迁移以外的 backend 覆盖均被执行；本次不执行迁移测试。
  - 失败为非支付的 favorites 站点生命周期 `404 Site not found`、UUID boundary 两项（`CHARGER_NOT_COMMISSIONED` / 缺少 `ocpp_identity`），以及 pricing modes 三项全套运行时的 `TARIFF_NOT_CONFIGURED`。定向复核：
    `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-backend-failures-pycache python3 -m pytest tests/test_app_favorites_api.py::test_favorite_site_lifecycle_is_idempotent_and_personal tests/test_pricing_modes.py tests/test_uuid_boundary_review.py::test_qr_check_uses_ocpp_identity_and_returns_both_ids tests/test_uuid_boundary_review.py::test_string_charge_point_filters_resolve_identity_and_enforce_tenant -q`
    - `3 failed, 5 passed, 1 warning, 4.04s`；pricing modes 定向运行 `5 passed`，因此其余三项属于全套运行中的顺序/共享 fixture 敏感失败，未继续无限重跑。稳定失败为 favorites 404 与 UUID boundary 两项。
- charger-sim 全部测试：在 `charger-sim/` 执行 `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-charger-sim-pycache python3 -m pytest tests -q`，`74 passed, 0 failed, 1 warning, 1.34s`。
- 现有场景脚本：`python3 cli.py scenario list --scenario-dir scenarios/p0` 列出 `9` 个 P0 场景；`python3 cli.py scenario validate scenarios/p0` 对 `9/9` 场景返回 `PASS`。未执行场景 run：现有 run 流程依赖 `seed_sim_e2e.py`/清理脚本及 ownership fake-payment 场景，会写入/改变测试数据库或伪造支付事实；按本 QA 禁止条件标记为 `not executed/blocked`，校验通过不等于旅程执行通过。
- 本地安全并发/降级脚本：`PYTHONPATH=. ENVIRONMENT=test python3 scripts/measure_be211_capacity.py --rows 200 --workers 8 --batch-size 50`；临时 SQLite/fake provider 证据为 `200` 行写入、连接池 bounded（size `4`/workers `8`）、lock probe `busy_timeout_observed`、Redis 不可用时 meter-values fallback fail-closed、provider burst `200/200`（peak fake inflight `8`）、queue lease `200`/DLQ `1`、reconciliation `4` 批且 cursor bounded。输出明确 `real_provider_used=false`、`production_capacity_claim=false`；不能替代真实 PostgreSQL/Redis 业务并发证据。
- 只读 PostgreSQL/Redis 数据事实：
  `docker compose --env-file .env.test.local -f docker-compose.test.yml exec -T db psql -U ocpp_user -d ocpp -Atc "SELECT current_database(), count(*) FROM payment_orders; SELECT count(*) FROM payment_orders WHERE amount < 1000; SELECT count(*) FROM (SELECT idempotency_key FROM payment_orders WHERE idempotency_key IS NOT NULL GROUP BY idempotency_key HAVING count(*) > 1) q; SELECT count(*) FROM payment_webhook_events w LEFT JOIN payment_orders o ON o.id=w.payment_order_id WHERE w.payment_order_id IS NOT NULL AND o.id IS NULL;"`
  - 结果：`ocpp|19`、低于 `1000` 的订单 `5`、重复 idempotency key `0`、孤儿 Webhook order ref `0`。
  `docker compose --env-file .env.test.local -f docker-compose.test.yml exec -T redis redis-cli ping` 返回 `PONG`；`... redis-cli dbsize` 返回 `0`。未执行写事务、flush、重启、迁移或账务伪造插入。
- 安全 mock/contract 覆盖已包含在上述全部 backend suite：hosted page/CSP 与 return URL allowlist、saved-card 所有权/服务端卡事实/CVV-only 页面、next-action/3DS URL 校验、Provider capability redirect contract 均通过对应本地测试；这些是 mock/contract 证据，不是 3DS challenge、真实 hosted return、Secure Fields 或真实 saved-card CVV Provider 证据。

## External gate continuation（2026-08-18 UTC，有界）

### 测试环境与健康度

- `docker compose --env-file .env.test.local -f docker-compose.test.yml config --format json`：exit `0`；有效配置为 `ENVIRONMENT=test`、`MERCADOPAGO_ENVIRONMENT=sandbox`、`PAYMENT_RAILS_ENABLED=true`（仅本地 test 注入），`DATABASE_URL`/`REDIS_URL` 均存在；未输出密钥。
- `docker compose --env-file .env.test.local -f docker-compose.test.yml ps --all`：exit `0`；CSMS、PostgreSQL 15、Redis 7、MQTT healthy。未重启既有 CSMS 容器，避免其 entrypoint 自动执行 Alembic migration。
- `curl -sS --max-time 15 -w '\nHTTP_STATUS=%{http_code}\n' http://localhost:8001/health`：HTTP `200`，database/redis/websocket 均 `ok`/`configured`。
- `curl -sS --max-time 15 -w '\nHTTP_STATUS=%{http_code}\n' https://sandbox-api.eslatin.com.co/health`：HTTP `200`，database/redis/websocket 均 `ok`/`configured`。
- `docker compose --env-file .env.test.local -f docker-compose.test.yml build csms`：完成；未启动 entrypoint、未执行迁移。当前工作树 `csms/app/services/mercadopago_service.py` SHA-256 与 one-off test image 均为 `73611e5422d922ded00e3ab60a2bcf319ac7f2450e3e3357033a87e05a1b8762`。

### Sandbox payment / Webhook / reconciliation

- 只读 Provider query：
  `set -a; source /Users/xiaoqingran/eslatincsms/.env.test.local; set +a; for payment_id in 1327898680 1350490277; do curl -sS --max-time 15 -w '\n__HTTP_STATUS__%{http_code}' -H "Authorization: Bearer ${MERCADOPAGO_ACCESS_TOKEN}" "https://api.mercadopago.com/v1/payments/${payment_id}"; done`；另以同形命令查询 `1327896936`。
  - 三个既有真实 Sandbox payment 均 HTTP `200`、`approved`/`accredited`；金额分别为 `10,000 COP`、`10,000 COP`、`89,100 COP`，币种均为 `COP`。本轮没有新建支付或使用伪造支付插入。
- `docker compose --env-file .env.test.local -f docker-compose.test.yml logs --no-color --since 48h csms | rg -i 'mercadopago|webhook|x-signature|request.?id|reconcil' | tail -120`：既有 test 容器日志显示真实 Sandbox create `HTTP 201`，payment IDs `1327896936`、`1350490277`、`1327898680`；对应 `/api/v1/app/payments/webhooks/mercadopago` 返回 HTTP `200`。数据库只读查询确认 3 个 `payment.created` 事件均 `processed=true`、无重复 Provider event ID、无未处理 Mercado Pago event。
- `docker compose ... exec -T db psql ...` 的 Webhook 查询：payload 仅有 provider `id/data/action` 字段；数据库没有保存 `X-Signature` 或 `X-Request-Id` 原始请求头。因此只能证明真实事件到达、主动反查和落库处理，不能证明本轮真实头部验签；真实重复/乱序事件也未得到可独立重放的原始签名头部。
- 历史日志记录 payment `1327898680` 的重复 approved/乱序处理进入 `Duplicate approved payment requires refund or manual review`，随后修复前 `get_refund_facts` 抛出 `JSONDecodeError` 并进入人工复核；该历史事件不改变修复后缺陷状态，也不能判为真实 Provider reconciliation 全通过。

### 3DS / hosted return / saved-card CVV

- test allowlist 已只读确认包含 `eslatin://payment-return,http://localhost:8081/payment-return`；健康检查通过。
- 没有可核验的本轮 3DS challenge、hosted checkout 浏览器 return、Secure Fields tokenization 或 saved-card CVV Provider 证据；既有文档只说明原生深链在本地浏览器展示受限，不能替代 3DS/真实 CVV 证据。以上保持 `untested/blocked`。

### Refund / timeout / unknown

- 修复前历史 one-off adapter 只读证据：
  `docker compose --env-file .env.test.local -f docker-compose.test.yml run --rm --no-deps --entrypoint python csms - <<'PY'`，stdin 脚本导入 `get_mercadopago_service`，对 `('1327896936', '1350490277')` 调用 `service.get_refund_facts(payment_id)` 并捕获异常，最后以 `PY` 结束输入。
  - 修复前历史结果：两个真实 Sandbox payment 均复现 `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`；没有创建退款。该原始证据保留用于说明缺陷起因，不能代表修复后当前状态。
- Provider 只读探测 `GET https://api.mercadopago.com/v1/payments/{payment_id}/refunds` 对 `1327896936`、`1350490277`、`1327898680` 均 HTTP `405` 且空 body；未发送任何退款 mutation。
- QA-BE-PAY-EXT-001 已 resolved；真实全额/部分退款、重复退款、超时/未知状态仍未实际执行 mutation，因此保持 `untested/blocked`。本地 fake Provider 的 refund 回归通过不代表真实资金事实。

### Current-worktree PostgreSQL / Redis / dirty data

- 当前源 one-off command：
  `docker compose --env-file .env.test.local -f docker-compose.test.yml run --rm --no-deps --entrypoint python csms - <<'PY'`，stdin 脚本执行 Redis `SET NX` 12 并发、TTL/删除后重领/过期、PostgreSQL read-only counts 和 `pg_try_advisory_lock` exclusion，最后以 `PY` 结束输入。
  - Redis 12-way `SET NX`：`1` winner；claim TTL `5s`；删除后 value `None`；reclaim `True`；1.3s TTL expiry 后 value `None`。
  - PostgreSQL：health `('ocpp', False)`；below-minimum PaymentOrder `5`；duplicate payment idempotency key `0`；orphan Webhook order ref `0`；advisory lock `True/False`，one winner。
- 只读脏数据扫描：PaymentOrder 共 `19`；状态 `error:13/approved:4/created:2`；duplicate idempotency/external reference、Webhook/Wallet/ChargingSession 孤儿引用、Invoice duplicate session/order ref 均 `0`。另有 `5` 条 `<1,000 COP` 的 `charging/error/unpaid` 历史订单（`267.30`、`48.60`、`48.60`、`48.60`、`291.60`），均无对应钱包入账或 paid Invoice；这是需清理/处置的脏数据风险，QA 未修改。
- 该 one-off 证明当前源与 test PG/Redis 的受限连接、Redis 幂等锁/TTL/键丢失重领和 PostgreSQL advisory-lock 基础能力；未执行会修改业务账务的真实并发 settlement、数据库写事务、Redis 重启/flush 或迁移，因此完整业务并发/Redis 服务级丢失恢复仍为 `blocked`。

## 验证对象与环境指纹

- Feature：`PAY-MP-001`；Change：`CHG-20260817-PAY-API-GOVERNANCE`
- 固定逻辑角色：`qa-agent`，运行实例：`qa-agent-lovelace`；scope：`backend`
- 依据：`TECH_ARCHITECTURE.md`、`QA_STRATEGY.md`、`BACKEND_BOUNDARIES.md`、`STATUS.md`、`BE-P0-2_HANDOFF.md`、`TASKS.md`、冻结契约、ADR-004
- OS/test platform：Darwin；Python `3.9.6`；pytest `8.3.3`
- 依赖：FastAPI `0.115.2`、Pydantic `2.9.2`、SQLAlchemy `2.0.35`、Redis `5.0.8`、Mercado Pago SDK installed
- Git：branch `webDev`；HEAD `e169bffe834356016b9a9b9a20b76d88fe93b711`；工作树含负责人已有大量未提交/未跟踪改动，本 QA 未回退或清理
- `.env.test.local` 存在；批准的 `docker-compose.test.yml` config 校验通过；未读取或输出密钥
- Docker `28.5.1`；Compose `v2.40.3-desktop.1`
- test Compose 当前报告 CSMS、PostgreSQL 15、Redis 7、MQTT healthy；本轮仅 build 当前 CSMS 镜像并用 `--entrypoint python` one-off 执行，未重启既有 CSMS 容器，避免自动迁移
- 有效 test 注入为 `ENVIRONMENT=test`、`MERCADOPAGO_ENVIRONMENT=sandbox`、`PAYMENT_RAILS_ENABLED=true`；本 QA 未改变配置，生产开关仍须保持 `false`
- 反复出现非阻塞 warning：urllib3 因 Python 3.9 LibreSSL `2.8.3` 发出 `NotOpenSSLWarning`

## 初次 QA COMMANDS_RUN / TEST_RESULTS（修复前基线）

以下命令均在 `csms/` 执行，除非另有说明。

1. `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-pycache python3 -m pytest tests/test_payment_method_codec.py tests/test_payment_methods.py tests/test_checkout_session_api.py tests/test_checkout_session_store.py tests/test_payment_reconciliation_be6.py tests/test_payment_refunds_be7.py tests/test_payment_merchant_context.py tests/test_p0_app_regressions.py -q`
   - `113 passed, 0 failed, 1 warning, 12.93s`
2. `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-pycache python3 -m pytest tests/test_payment_interface_governance.py tests/test_billing_service_be5.py tests/test_charging_payment_intent.py tests/test_payment_provider_capabilities_be204.py tests/test_phase4_payment_reliability.py tests/test_production_config.py -q`
   - `32 passed, 0 failed, 1 warning, 5.34s`
3. `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-pycache python3 -m pytest tests/test_logging_security.py tests/test_db_write_p0.py tests/test_ocpp_device_security.py tests/test_ocpp_message_handler.py tests/test_meter_telemetry_service.py tests/test_multitenant_isolation.py tests/test_multitenant_complete.py tests/test_database_models.py tests/test_database_queries.py -q`
   - `75 passed, 0 failed, 1 warning, 9.15s`
4. `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-pycache python3 -m pytest tests/test_sim_e2e_p0.py tests/test_user_charging_flow.py tests/test_phase3_charging_domain.py -q`
   - `29 passed, 0 failed, 1 warning, 6.32s`
5. `PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-pycache python3 -m compileall -q app`
   - exit `0`；缓存写入 `/private/tmp/eslatin-qa-pycache`
6. `git diff --check`
   - exit `0`
7. `rg -n "checkout-sessions|webhooks/(mercadopago|sim)|create-(wompi|mercadopago)|pay-(wompi|mercadopago)|wallet/payments/webhook|wallet/payments/sim-webhook|payment_type_id|save_card" app/api app/services contracts`
   - canonical Checkout/Webhook 实现存在；历史 create/status handlers 仍在源码中但挂在 `legacy_router`，公共路由测试确认未注册
8. `docker compose --env-file .env.test.local -f docker-compose.test.yml config --quiet`
   - exit `0`
9. `docker compose --env-file .env.test.local -f docker-compose.test.yml ps --all`
   - exit `0`；CSMS、PostgreSQL、Redis、MQTT healthy；本轮未 `up`、`build`、`exec` 或写入容器/数据库
10. 内联 Python Mercado Pago 验签 smoke（修复前，虚构 secret/data，仅调用本地 SDK 构造）
    - 修复前结果：合法签名 `True`、篡改签名 `False`、缺失 `ts` `False`；源码检查 `uses_hmac_compare_digest=False`、`uses_plain_equality=True`

## 回归矩阵

| 验收域 | 结果 | 证据 |
|---|---|---|
| Codec 三类卡、legacy brand、未知 v1 type、非法 label、无猜测 | passed | `test_payment_method_codec.py` |
| `prepaid_card` 保存/默认/删除/列表/Provider hints | passed | `test_payment_methods.py`、`test_payment_reconciliation_be6.py` |
| New-card/saved-card confirm、用途矩阵、token 单次消费 | passed | checkout API/store/payment-method suites |
| Canonical App routes 与旧路由不注册 | passed | `test_payment_interface_governance.py` + route scan |
| 认证、跨用户 payment method、tenant/merchant 归属 | passed | merchant-context、payment-method、multitenant suites |
| Checkout/Confirm/Query 状态、幂等、重复提交、过期/失败关闭 | passed | checkout API/store、phase4 reliability |
| PaymentOrder 状态迁移、approved/declined/processing 乱序、重复 approved | passed | `test_payment_reconciliation_be6.py`、`test_charging_payment_intent.py` |
| Decimal、付费最低 `1,000.00 COP`、免费 `0 COP` | passed | `test_billing_service_be5.py`、merchant-context suite |
| 钱包/direct-card/Invoice/PaymentOrder/ChargingSession 一致性 | passed（SQLite/fake Provider） | billing/reconciliation/SIM suites |
| SIM Webhook 签名错误、重复事件、ledger 幂等、production 禁用 | passed | `test_sim_e2e_p0.py` |
| Provider Webhook 乱序、金额/币种/商户不匹配失败关闭 | passed（fake Provider） | `test_payment_reconciliation_be6.py` |
| Mercado Pago `X-Signature` 合法/篡改/格式边界 | passed（recheck） | `test_payment_merchant_context.py` 13 passed；实现使用 `hmac.compare_digest` |
| OCPP 与支付/账务边界、RemoteStart/StartTransaction/MeterValues/StopTransaction | passed（本地模拟/SQLite） | charging intent、OCPP、meter、user-flow suites |
| 重复/孤儿 OCPP 事件、脏数据和跨租户边界 | passed（本地模拟/SQLite） | SIM、database、multitenant suites |
| 审计/敏感日志、PAN/CVV/token/credential 脱敏 | passed（自动化/静态） | `test_logging_security.py`、merchant-context suite |
| Python 编译/API 静态/whitespace | passed | `compileall`、route scan、`git diff --check` |
| 迁移以外全部 CSMS backend tests | blocked / non-clean | `541` collected；`535 passed, 6 failed`；定向复核后稳定失败为 favorites 404 与两项 UUID boundary |
| charger-sim 全部 tests / P0 场景 schema validation | passed | `74 passed`；`9/9` 场景 validation PASS；场景 run 因禁止写入/伪造支付未执行 |

## 缺陷与复现

### QA-BE-PAY-001 — Mercado Pago Webhook 验签不是常量时间比较（resolved）

- 严重性：`P1 / security gate`；状态：`resolved`
- 修复位置：`csms/app/services/mercadopago_service.py:535`
- 修复事实：实现现在调用 `hmac.compare_digest(calculated_hash, hash_v1)`，旧的普通字符串比较已无命中。
- 回归证据：`test_mercadopago_webhook_signature_uses_constant_time_comparison` monkeypatch `hmac.compare_digest` 并断言实际调用；`test_payment_merchant_context.py` 13 passed，支付核心回归 132 passed。
- 仍未完全验证：真实 Mercado Pago `X-Signature`/`X-Request-Id` 头部验签、3DS、退款和完整 PostgreSQL/Redis 业务并发；这些保持 `untested/blocked`，不影响本缺陷已 resolved 的判断。

### QA-BE-PAY-EXT-001 — Sandbox refund facts 查询稳定失败关闭（resolved；真实 Provider 仍未重测）

- 状态：`resolved`。修复后，SDK 抛出 `json.JSONDecodeError` 会被转换为稳定结果 `success=false, error=mercadopago_refund_query_failed, retryable=true`；不会向上层泄漏 parser 异常。
- 非集合响应边界：当 SDK 返回 HTTP `200` 但 `response` 不是退款集合（例如 HTML/string）时，返回 `success=false, error=mercadopago_refund_response_invalid, retryable=false`；不会把 malformed body 解释成 `refunded_amount=0`。
- 精确回归命令：`PYTHONPYCACHEPREFIX=/private/tmp/eslatin-qa-refund-recheck-pycache python3 -m pytest tests/test_payment_merchant_context.py tests/test_payment_refunds_be7.py -q`。
- 历史结果：`20 passed, 0 failed, 1 warning, 1.16s`。新增 `test_mercadopago_refund_query_converts_non_json_sdk_response_to_safe_failure` 断言 JSONDecodeError 稳定失败且日志不泄漏原始 parser message；`test_mercadopago_refund_query_rejects_non_collection_success_body` 断言 HTTP 200 非集合响应稳定失败；BE7 partial/cumulative refund、provider timeout fail-closed 回归均通过。本轮同一范围复核为 `21 passed, 0 failed, 1 warning, 1.28s`。
- 证据边界：本次未执行真实退款 mutation；真实 Sandbox refund/partial refund/duplicate refund/timeout/unknown 仍为 `untested/blocked`，本缺陷 resolved 不等同于真实资金闭环通过。

## 数据事实、架构符合性与未测面

- `Invoice` 是金额权威；本地测试证明 direct-card 使用 Invoice 金额、最低金额为 `1,000.00 COP`、不写钱包流水；wallet top-up/charge ledger 幂等。
- `PaymentOrder`、`PaymentWebhookEvent`、`ChargingSession` 的重复、乱序、金额/币种/商户不匹配路径在 SQLite/fake Provider 证据下失败关闭；真实 Sandbox Webhook 事件已落库并 processed；历史一次重复 approved reconciliation 曾因修复前 refund facts 异常进入人工复核，QA-BE-PAY-EXT-001 当前已 resolved；Redis 未被用作最终账务事实。
- App 不信任客户端 `tenant_id`；MerchantContext、operator tenant、Provider account ref 由服务端事实解析；跨用户 payment method 不可见。
- OCPP handler 未直接调用 Provider；充电用量、StopTransaction 和账务由各自 owner/service 交接，符合技术架构、后端边界和 ADR-004。
- canonical App 入口和 Provider-specific Webhook 路径符合 `CHG-20260817-PAY-API-GOVERNANCE`；历史实现保留为未注册代码符合治理说明。
- 本轮未改 API contract、数据库模型、Alembic migration、事件 schema、OCPP、生产配置或支付开关。工作树已有的 P002 migration 文件属于其他改动，未由本 QA 编辑。
- coupling level：`C2`；本轮未引入新耦合、循环依赖或架构变更。QA-BE-PAY-001 已 resolved，未发现新的架构偏差。

未测/blocked：

1. 真实 Mercado Pago Colombia Sandbox：创建/主动 query 已由既有 test-container 日志和本轮 Provider `GET` 复核部分证明；原始 `X-Signature`/`X-Request-Id` 未持久化，无法独立证明真实头部验签；一次真实重复 approved reconciliation 进入人工复核。
2. 3DS challenge/return、Secure Fields tokenization、saved-card CVV、动态 identification types/BIN 的真实 Provider 行为：untested。
3. 真实 Mercado Pago refund/partial refund/timeout/duplicate refund：仍为 `untested/blocked`，本轮没有退款 mutation；QA-BE-PAY-EXT-001 已 resolved。本地 refund/fake Provider 回归不代表资金事实。
4. 当前未提交工作树与 PostgreSQL/Redis 的完整业务并发、数据库写事务、Redis 服务级重启/丢失恢复：blocked。已完成只读连通性/脏数据扫描、Redis NX/TTL/键删除重领、PG advisory-lock，以及临时 SQLite/fake provider 的受限容量/降级脚本；这些不能证明真实 PG/Redis 业务并发。5 条低于最低金额的 error/unpaid 历史订单仍需 owner 处置。
5. 浏览器/WebView、视觉、可访问性、真实网络隐私抓包：不属于 backend-only 本轮。
6. `STATUS.md` 当前记录 `backend_qa: blocked-current-recheck`、`e2e_qa: not-started`，而 `E2E_QA_REPORT.md` 另有历史 `passed` 文本；该文档状态漂移不能作为本轮 backend PASS 或生产放行证据。

## RISKS / VERDICT

- QA-BE-PAY-001 已 resolved；focused recheck 不再发现该验签缺陷。
- SQLite/fake Provider 不能证明真实 Provider 资金闭环、签名格式兼容或 PostgreSQL/Redis 并发行为。
- 工作树 baseline 非干净；结果属于当前工作树快照，不等于 Git HEAD。
- `PAYMENT_RAILS_ENABLED` 必须继续保持 `false`；本轮没有生产部署、生产数据库、真实资金或密钥操作。

`VERDICT: blocked`

## QA continuation checkpoint — 2026-08-18 UTC

本节是当前复测终态；前文历史证据全部保留。后端 QA 已从负责人暂停状态恢复到本地/测试范围复测，但整体仍为 `blocked`，没有将本地全量绿色解释为生产或真实资金通过。

### Fresh local/test evidence

- CSMS 迁移以外完整回归：`558 passed, 5 skipped, 20 warnings`。
- PRC-MODE-001 五类 P0 定价门禁：`tests/test_pricing_mode_qa.py`，`9 passed`；定价/计费/支付意图联合回归：`28 passed`。
- App/Admin/charger-sim 既有本轮证据：App `43 suites / 188 passed`，Admin `36 files / 186 passed`，charger-sim `74 passed`。
- Test Compose 使用既有 `.env.test.local` + `docker-compose.test.yml`；未创建新的环境文件或 Compose 文件，未执行迁移。

### Fresh Sandbox Provider evidence

- 只使用 `.env.test.local` 的 Sandbox 凭证和测试卡；未打印或写入凭证、Card Token 或完整 Provider ID。
- Card Token 创建 HTTP `201`。
- Provider payment create HTTP `201`，Provider payment ID 存在，状态 `approved`，状态详情 `accredited`，金额 `2,001 COP`。
- Provider payment query HTTP `200`，状态和状态详情仍为 `approved/accredited`，金额 `2,001 COP`。
- 该探测未创建本地 Checkout Session/PaymentOrder，也未伪造本地支付事实；因此不关闭真实订单关联 Webhook、签名验签、Invoice/PaymentOrder 结算、对账、重复通知、3DS 或退款 mutation 门禁。

### Implementation correction observed during QA

- `csms/app/api/v1/sites.py` 的站点定价写入已修正为向 UUID 字段传入 UUID 对象，不再传入字符串；该 C1 修复无数据库模型或迁移变化，并由定价门禁与完整后端回归覆盖。
- 新增的 QA 证据文件为 `csms/tests/test_pricing_mode_qa.py`，只覆盖 P0 定价门禁，不改变 Provider 或账务行为。

### Current gate

`STATUS: blocked`

Remaining blockers: order-linked signed Webhook and duplicate notification; real settlement/reconciliation/refund/3DS; PostgreSQL/Redis business concurrency and recovery; D-204/BE-205 production-like runtime and capacity; frontend independent QA; formal cross-module E2E; production DNS/TLS/secrets/backup/alerts/rollback; and human release review. `PAYMENT_RAILS_ENABLED` production safety gate remains closed.

原因：QA-BE-PAY-001 与 QA-BE-PAY-EXT-001 均已 resolved，focused payment recheck 通过；但广义 backend 全套仍有稳定的 favorites/UUID boundary 失败，且真实签名头部、3DS、完整 PG/Redis 业务并发及 Provider refund/partial/duplicate/timeout/unknown mutation 未闭环。不得以历史 JSONDecodeError 证据、历史 E2E 文档、数据库插入伪造支付结果或本地测试全绿替代这些证据；不得声称生产通过。

## SELF_CHECK（2026-08-18 UTC）

1. 原始目标：在不改业务代码、迁移、生产配置、数据库事实或测试结果的前提下，完成当前工作树的 PAY-MP-001 backend QA，并只更新本报告。
2. 当前活动：已执行支付 focused/core 回归、迁移以外全部 CSMS backend、全部 charger-sim、场景校验、test Compose/health、只读 PostgreSQL/Redis 与本地 SQLite/fake 并发/降级检查；当前只做终态整理。
3. 直接推进原始任务：是；所有测试与环境操作均限于本地/test 或只读 Sandbox query，未执行真实 refund mutation、seed、迁移、生产命令或伪造支付插入。
4. 新证据：退款缺陷保持 resolved；支付核心 `135 passed`；CSMS backend 全套 `535 passed/6 failed`，定向确认 favorites/UUID 稳定失败；charger-sim `74 passed`；P0 场景 `9/9` 校验通过；外部真实退款/3DS/原始签名头部/完整 PG-Redis 业务并发仍缺证据。
5. 未重复无限评估：pricing modes 全套失败已做一次定向复核并通过，未继续重跑；其余稳定失败与外部缺口已有足够门禁证据。
6. 范围与治理：未超出 qa-agent/backend scope；仅本报告发生修改；未创建其他 Agent；未改变用户已有工作树改动。
7. 障碍分类：稳定的非支付 backend 测试失败；真实 Provider 与 PG/Redis 业务证据缺失；另外运行时 `monitor`/`convergence-check` 受现有 `.codex/runtime/.orchestrator.lock` 的 `Operation not permitted` 阻塞，未绕过治理锁。
8. 最小下一动作：由 owner 处理稳定 backend 失败，并在有批准的测试凭证/可重放签名/安全测试数据后补真实 Provider refund/3DS/Webhook 与 PG/Redis 业务并发证据；本 QA 终态为 `blocked`。

## 统一交接

STATUS: blocked

CHANGED_FILES:
- `docs/features/PAY-MP-001/qa/BACKEND_QA_REPORT.md`

COMMANDS_RUN:
- 见上文 `Focused recheck`、`External gate continuation`；仅使用批准的 test Compose/Sandbox，未执行生产命令、迁移或支付/账务伪造插入

TEST_RESULTS:
- 本轮 focused recheck：21 项通过；支付核心回归 135 项通过；QA-BE-PAY-001、QA-BE-PAY-EXT-001 resolved
- 迁移以外全部 CSMS backend：541 collected，535 passed，6 failed，20 warnings；定向复核 3 failed / 5 passed，稳定失败为 favorites 站点 404 与两项 UUID boundary；pricing modes 定向 5 passed
- charger-sim：74 passed；P0 场景 validation：9/9 PASS；场景执行未运行（禁止 seed/清理写入与 fake payment）
- 本地 SQLite/fake BE-211：200 rows、8 workers、bounded pool/lock/fallback/queue/reconciliation checks completed；`real_provider_used=false`、`production_capacity_claim=false`
- Sandbox：3 个既有 payment query HTTP 200/approved；3 个真实 Webhook 事件 processed=true；真实 header 验签不可由持久化证据证明；QA-BE-PAY-EXT-001 已 resolved（历史 JSONDecodeError 证据保留），真实 refund 生命周期 mutation 仍未测
- source-aligned datastore：Redis NX/TTL/reclaim 与 PG advisory-lock/只读一致性检查通过；完整业务写并发 blocked；5 条低于最低金额的 error/unpaid 脏订单记录

CONTRACT_CHANGES:
- 无 API、公开类型、数据库、迁移或事件契约变化

ARCHITECTURE_COMPLIANCE:
- C2；canonical Checkout/Provider Webhook/tenant/Invoice/OCPP 边界符合；无本 QA 引入的架构漂移；QA-BE-PAY-001 resolved

RISKS:
- QA-BE-PAY-EXT-001 已 resolved；本轮广义 backend 全套仍有 favorites 404 与两项 UUID boundary 稳定失败；真实 `X-Signature`/`X-Request-Id`、3DS、Provider refund/partial/duplicate/timeout/unknown mutation 和完整业务 PG/Redis 并发证据缺失；5 条低于 1,000 COP 的历史 error/unpaid 订单需 owner 处置；test `PAYMENT_RAILS_ENABLED=true` 仅为本地测试注入，生产 `false` 保持不变

## 当前治理预授权后的运行态复核（2026-08-18）

- 依据 `AGENTS.md` 与 `docs/qa/QA_STRATEGY.md` 的 Sandbox QA 预授权，本轮允许在本地测试 Compose 和 Mercado Pago Sandbox 执行只读 Provider、Webhook、数据库和健康检查；未新增环境/Compose 文件，未执行迁移，未修改生产配置。
- App 自动化 `188 passed`，Admin 自动化 `186 passed`，CSMS 迁移以外完整回归 `548 passed, 5 skipped`。
- 本地健康 `8001/health=200`，测试 Compose config 校验通过，Admin `3002=200`；公网 `sandbox-api.eslatin.com.co/health=530`，公网 Tunnel 当前不可用。
- 3 个既有 Sandbox payment 只读查询均 HTTP `200` 且 `approved/accredited`；当前测试库聚合为 PaymentOrder `19`、低于最低金额历史订单 `5`、重复幂等键 `0`、孤儿 Webhook `0`、Mercado Pago 重复 Provider event `0`、已处理 Mercado Pago Webhook `4`。
- 新增确认的脏数据阻塞：`app_wallet_transactions` 中存在 `1` 条 `top_up` 关联 PaymentOrder 状态为 `created`（非 `approved`），金额 `10,000 COP`。本轮未清理或改写，故继续 `STATUS: blocked`；必须先定位该历史流水来源并按人工指示处置，再复测钱包账务闭环。
