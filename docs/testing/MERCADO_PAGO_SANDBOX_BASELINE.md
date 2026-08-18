# Mercado Pago Sandbox 测试基线

状态：ACTIVE

## 目的

本文件定义 EsLatin 本地 Mercado Pago Sandbox 测试资料的固定位置、使用范围和变更门禁。它不是生产配置，也不保存密码、Access Token、Webhook Secret 或完整测试卡号。

## 本地配置

- 配置文件：`.env.test.local`
- Git 状态：已被 `.gitignore` 忽略
- 使用范围：本地 Docker Compose / Mercado Pago Sandbox
- 禁止范围：生产环境、真实支付、真实银行卡、生产 Webhook

## 测试账号索引

- 国家：Colombia
- Seller：EsLatin Vendedor，User ID `3155420482`
- Buyer：EsLatin Comprador，User ID `3154276041`
- 测试账号用户名和密码只保存在本地 `.env.test.local`，不得写入 Git、Notion 或公开文档。

## 测试卡索引

测试卡完整号码只保存在本地 `.env.test.local`，不得同步到 Notebook。当前卡类型包括 Mastercard、Visa 和 Visa Débito；有效期为 `11/30`，CVV 为 `123`，成功场景持卡人标识为 `APRO`。

## 变更规则

以下内容必须经过 Product Owner 明确批准后才能修改：

- Seller / Buyer 测试账号
- 测试国家
- Public Key
- 测试卡目录
- Sandbox / production 环境边界
- Webhook 配置来源

Access Token、Webhook Secret、支付加密密钥和签名密钥必须继续使用本地 secret 注入，不得写入本基线文档。

## 测试流程要求

1. 使用 `ENVIRONMENT=test` 的本地 Compose。
2. 使用 Mercado Pago Sandbox 测试凭据。
3. 通过真实 Sandbox Checkout 创建支付。
4. 通过公网 HTTPS Webhook 接收 Mercado Pago 通知。
5. 通过数据库、Admin 和 Mercado Pago Sandbox 结果进行交叉验证。
6. 不通过直接插入支付成功状态替代 Sandbox 主流程。

## Sandbox 金额兼容性记录

当前 Mercado Pago Colombia Sandbox 的官方 `APRO` 测试卡存在以下已验证行为：

- `1,000.00 COP`：Provider 返回 HTTP 400 / code `2072`（`Invalid value for transaction_amount`）。
- `1,010.00 COP`：重复测试均返回 HTTP 400 / code `2072`。
- `1,011.00 COP`：重复测试均返回 HTTP 201 / `approved` / `accredited`。
- `10,000.00 COP`：同一 Public Key、Access Token、测试卡和请求结构返回 HTTP 201 / `approved`。

这项结果已纳入 EsLatin 的产品金额规则：付费充电最低收费为 `1,011 COP`，免费模式仍为 `0 COP`；本地 Sandbox 的完整 Provider 链路回归必须使用不少于 `1,011 COP` 的测试金额。禁止在后端把用户实际金额静默放大到测试金额。

本记录由 2026-08-18 的直连 Sandbox 边界验证产生；若 Mercado Pago 更新 Sandbox 规则，需重新验证并经 Product Owner 批准后更新本节和产品基线。

## 2026-08-18 完整 Checkout 回归

- 本地测试 Compose 已重建并加载金额序列化修复；未执行数据库迁移。
- 新建 `wallet_top_up`、`10,000.00 COP` Checkout，使用全新的 Sandbox Card Token 提交。
- Provider：HTTP `201`，状态 `approved`；金额诊断为 JSON `float`。
- Checkout：`approved`；PaymentOrder：`approved`，Provider Payment ID 已写入。
- Webhook：`payment.created` 返回 HTTP `200`，事件 `processed=true`。
- 钱包：仅生成 1 笔 `top_up` 入账，金额 `10,000.00 COP`；重复计数为 1。
- 稳定 Tunnel：`https://sandbox-api.eslatin.com.co/health` 返回 HTTP `200`，数据库、Redis、WebSocket 均正常。
- 浏览器在提交后保持“Procesando…”是本地浏览器无法处理 `eslatin://payment-return` 深链导致的展示限制；服务端状态和账务已完成，不构成 Provider 失败。

## Web 回跳测试

- 本地 Web 测试回跳：`http://localhost:8081/payment-return`。
- App 原生回跳仍使用：`eslatin://payment-return`。
- 后端只接受显式配置在 `CHECKOUT_RETURN_URL_ALLOWLIST` 中的地址；生产环境的 Web 回跳必须使用 HTTPS。
- Web 回跳页仍通过 Checkout Session 状态接口读取服务端事实，URL 中的 `status` 只作为导航提示，不作为账务依据。
