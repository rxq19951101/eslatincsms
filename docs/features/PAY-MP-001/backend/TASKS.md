---
id: PAY-MP-001
status: approved
owner: backend
reviewed_at: 2026-08-12
---

# 后端任务拆分

> 本文件只拆分后端任务。严格一次执行一个实现任务；本轮只交付设计，不修改业务代码。每项实现完成后先交给独立 `qa-agent`（backend scope），后端 QA 暂停期间不得把开发测试标为 QA 通过。

## P0 顺序与门禁

产品文档已 `approved`，共享 API 已 `frozen`，数据库/迁移范围为零。顺序固定为：

1. P0 后端架构评估和技术设计已经按独立 `purpose=save_card` 决策批准。
2. `BE-P0-1`：卡类型 codec、confirm、Provider Card 和 canonical projection；当前 `done-reviewed`，交接见 `BE-P0-1_HANDOFF.md`。
3. BE-P0-1 限定 diff、97 项开发回归和交接已由根主线程只读复核，P0-2 文件所有权已按负责人指令解除阻塞。
4. `BE-P0-2`：Hosted Checkout 动态能力、证件字段、西语页面、saved-card CVV 和安全状态页；当前 `done-review-required`，交接见 `BE-P0-2_HANDOFF.md`。
5. 两项均完成后恢复独立后端 QA；在 QA、前端 QA、E2E 和人工审查完成前保持 `PAYMENT_RAILS_ENABLED=false`。

共享契约已按负责人决定重新冻结。若实现发现 Provider 行为不能支撑已经冻结的单用途 Token 规则，必须停在 `changes-required`，不得自行增加请求字段、迁移或恢复“同时保存”选择。

## BE-P0-1：卡类型契约与 Provider 投影

状态：`done-reviewed`（2026-08-12）。

开发事实：三类卡、旧 codec `null`、new-card 强校验、saved-card 客户端事实拒绝、Provider Card 缺失/未知/冲突失败关闭及 reconciliation hints 已实现；定向与相邻支付回归 97 项通过。独立后端 QA、真实 Mercado Pago sandbox、Redis/PostgreSQL 尚未执行。

### 目标

把 `credit_card | debit_card` 端到端扩展为冻结的 `credit_card | debit_card | prepaid_card`，并删除所有未知卡静默回退信用卡的路径。任务完成后可单独验证，不依赖 Hosted HTML 的视觉实现。

### 文件所有权

- `csms/app/services/payment_method_codec.py`
- `csms/app/api/v1/app/payment_checkout.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/app/services/payment_providers/base.py`
- `csms/app/services/payment_providers/mercadopago_provider.py`
- `csms/app/services/mercadopago_service.py`（仅 Provider Card response 解析）
- `csms/app/services/payment_methods.py`
- `csms/app/services/payment_reconciliation.py`（仅 provider hints/codec 兼容边界）
- `csms/tests/test_payment_methods.py`
- `csms/tests/test_checkout_session_api.py`
- 可新增 `csms/tests/test_payment_method_codec.py`

禁止修改：数据库模型/迁移、`contracts/API.md`、前端/Admin、OCPP/计费状态机、生产密钥和 `PAYMENT_RAILS_ENABLED`。

### 实现任务

1. 把 codec 的唯一受支持集合扩展为三类；保留 `v1:<brand>:<type>` 格式和旧纯 brand `payment_type=null` 读取，不导入/重写历史行。
2. 扩展 `ConfirmCheckoutRequest.payment_type_id` Literal；新卡（包括 `save_card`）要求非空合法 `payment_method_id` + canonical `payment_type_id`；saved-card 的卡事实必须为空并由当前用户服务端投影取得。
3. Provider Card 解析以 Mercado Pago response 的 brand/type 为事实；缺失、未知、非法或冲突时失败关闭。不得使用 `payment_type_id` 或 `credit_card` 作为缺省事实。
4. 确保 `prepaid_card` 通过 PaymentMethodService 保存、默认/删除/列表、Hosted confirm hints、PaymentOrder provider hints 和旧兼容读取完整投影。
5. 保持 AppUser 过滤、Customer/Card 幂等、默认卡选择、敏感字段隔离和 MerchantContext 传递；任何失败不得写半成品本地 projection。

### 独立验收

- codec 单元覆盖三类、旧纯 brand、未知 v1 type、非法 label 和无猜测。
- fake Provider 返回 credit/debit/prepaid 时，保存卡与 API 投影准确；缺失/未知 type 时无本地卡记录且返回安全 Provider 错误。
- Checkout confirm 三类通过；空 type、未知 type、空 payment method、错误 installments、`save_card` 空 hint 和 saved-card 客户端覆盖均拒绝。
- 跨用户 payment method 仍为 404 等价安全错误；Redis/DB/log/redirect 不出现 PAN、CVV、证件资料或明文 Card Token。
- 相关回归至少覆盖 `test_payment_methods.py`、`test_checkout_session_api.py`、`test_payment_reconciliation_be6.py` 的 saved-card/provider-hints 路径。

### 交接要求

交接必须列出：修改文件、命令和测试结果、无 API/数据库/迁移变化、三类卡 fixture、旧 codec fixture、失败关闭证据、未执行的真实 sandbox/Redis/PostgreSQL/QA 项。BE-P0-2 不得在 BE-P0-1 交接前开始。

## BE-P0-2：Mercado Pago Colombia Hosted Checkout P0

状态：`done-review-required`（2026-08-12）。

### 目标

在 P0-1 canonical card capability 之上，交付首次新卡证件信息、动态证件类型、BIN 自动识别、全西语紧凑移动页、saved-card CVV 流程和会话错误恢复。实现和开发回归已完成，等待根主线程只读复核。

### 文件所有权

- `csms/app/services/payment_checkout/hosted_page.py`
- `csms/app/services/payment_checkout/service.py`
- `csms/app/api/v1/app/payment_checkout.py`
- `csms/tests/test_checkout_session_api.py`
- 可新增 Hosted renderer/service contract 测试文件

禁止修改：`contracts/API.md`、数据库模型/迁移、App/Admin、Provider 业务之外的计费/OCPP、真实密钥、前端托管页替代实现。

### 实现任务

1. New-card 页面加载 Provider identification types capability，动态渲染“Tipo de documento”和“Número de documento”；加载失败、空返回或结构非法时不渲染可提交表单/保持确认禁用。证件值只进入 MercadoPago.js tokenization。
2. Secure Fields 的 `binChange` 每次先清空旧识别结果，再调用 BIN/provider capability；只读展示 brand、issuer 和三类 payment type。无 BIN、失败、未知、冲突或 `prepaid_card` 不被 Provider 明确支持时，显示西语可行动错误且不得确认。
3. 移除 `CC` hidden select、`credit_card` 默认值、卡种/银行/分期手工控件、内部 purpose 和英文用户文案；固定 Spanish CTA/说明，`charging_direct` 只描述结束后按准确金额扣款。
4. Saved-card 页面只读取当前用户服务端的 Card ID/codec projection，显示 brand/type/尾号并重新采集 CVV；不生成新卡号、有效期、姓名或证件字段 DOM，confirm 不接收客户端卡事实。
5. 把 GET Hosted error 映射成不含 Secure Fields 的西语全页：签名/缺失/过期 404、已确认 409、暂不可用 503。confirm 继续冻结 JSON envelope；状态页只能使用安全 return allowlist。
6. 保持 `save_card` 在创建时冻结；`purpose=save_card` 固定 `true`，所有其他 purpose 固定 `false`。单次 direct-card 页面不显示保存选择，Token 只留给最终支付；服务端拒绝任何 `charging_direct + save_card=true`，刷新/重试/回跳不得改变用途。
7. 保留既有 CSP、no-store、Deep Link/next-action allowlist，并补充 HTML/日志/Redis/错误追踪敏感字段断言。

### 独立验收

- New-card HTML 动态调用 identification types；无硬编码 `CC`，证件字段可见且只在页面内存中使用。
- BIN state 覆盖 credit/debit/prepaid、清空、失败、未知、冲突；类型/品牌/issuer 只读，确认按钮在 capability 未 ready 时 disabled。
- Saved-card HTML 只有 CVV Secure Field；显示 brand/type/尾号；不出现新卡/证件字段。
- 全页面 `lang=es`，用户可见静态文案为西语，不出现 `charging_direct`、`save_card`、Provider 原始错误或英语字段标签；紧凑高度/窄屏单列/aria/live/loading 具备测试语义。
- 404/409/503 HTML 状态页不包含可提交卡字段、Token、签名 URL、用户/商户秘密，并提供安全返回/重新开始动作。
- 重复 confirm、Redis 故障、过期、已确认、Provider capability 故障和 303 Deep Link 均保持冻结 HTTP/error 语义。

### 已冻结的 Token 用途

- `purpose=save_card` 的 new-card Token 仅用于 Customers/Cards 关联，成功后返回 `saved_payment_method_id`。
- `purpose=charging_direct` 的 new-card Token 仅用于当前充电结束后的最终支付，固定 `save_card=false`。
- `wallet_top_up` 和 `unpaid_charge` 同样不得附带保存卡；需要保存时必须先走独立 `save_card` Checkout。
- 每个 Token 只按 Checkout 冻结的 purpose 消费一次，不静默改变 purpose，也不在单次支付页提供保存开关。

### 交接要求

交接必须列出 Hosted HTML 相关文件、定向测试和回归命令；逐项说明证件资料/Token 未进入 API/Redis/DB/log/Deep Link 的证据；说明真实 Mercado Pago sandbox、视觉可访问性、Redis/PostgreSQL 并发和后端 QA 尚未执行的范围。

## 既有 BE-1..BE-7 基线（保留，不在本轮重开）

| 任务 | 当前事实 | 与 P0 的关系 |
|---|---|---|
| BE-1 | MerchantContext/credential resolver 已实现；后端 QA 暂停 | P0 复用，不改 C1/C2 边界 |
| BE-2A/2B/2C | 加密 Redis、签名 URL、Hosted confirm/303 已实现并有定向测试 | P0-2 在其上修正能力和状态页，不回退安全边界 |
| BE-3 | Customers/Cards、默认/删除、用户隔离、旧 codec 读取已实现 | P0-1 扩展 codec/type，保持接口和迁移零变化 |
| BE-4 | Charging Payment Intent 与 StartTransaction 绑定已实现 | P0 只更新 provider hint/type，不改 Intent 状态机 |
| BE-5 | Invoice 权威金额与 wallet/direct/free 分支已实现 | P0 不改金额/结算分支 |
| BE-6 | Provider reconcile、Webhook、D1、状态投影已实现 | P0 只修 card type/hint 兼容，保留失败关闭 |
| BE-7 | 欠费服务能力和退款已实现，App 欠费体验延期 | P0 不新增欠费契约，不改退款/迁移 |

既有交接中的测试通过数、SQLite/fake Provider 限制、真实 sandbox/3DS/PostgreSQL 未验证和后端 QA 暂停事实全部保留；它们不是 P0 QA 证据。

## P0 完成门禁

- P0-1、P0-2 各有独立交接和测试证据，且无冻结契约偏差。
- `prepaid_card` 从 Provider response 到 API/支付提示完整投影；旧值仍为 null；未知类型始终失败关闭。
- Hosted 证件资料、PAN、有效期、CVV、Card Token、Access Token、credential handle 和完整 Provider response 未进入 EsLatin 持久化、日志或响应。
- 无数据库迁移、历史导入、生产开关变化；所有相关数据按用户/租户/商户上下文隔离。
- 后端 QA 恢复后完成真实 Mercado Pago sandbox、Redis/PostgreSQL、隐私和 Hosted error/视觉可访问性验收；在此之前不标记 QA 通过、不进入前端实现生产门禁。
