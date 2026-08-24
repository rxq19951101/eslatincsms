# ADR-004 — Mercado Pago Hosted Payment Boundary

- Status: accepted
- Date: 2026-08-12
- Related Change ID: PAY-MP-001

## Context

App 需要支持哥伦比亚新卡单次消费、保存卡、钱包充值和充电后实际金额扣款。Mercado Pago tokenization 可能要求证件、BIN、CVV 和 3DS，平台必须减少 PCI/敏感数据范围，并防止重复扣款。

## Decision

Backend 提供同源签名 Hosted Checkout，浏览器使用 MercadoPago.js Secure Fields。PAN、有效期、CVV、证件和原始 card token 不进入 App、常规 API、数据库或日志。新卡直接充电固定 `save_card=false`；保存卡只通过独立 `purpose=save_card`；已保存卡使用时重新采集 CVV。Provider adapter 和 reconciliation 是外部支付事实边界，Webhook 必须验签并主动反查。

## Reason

该边界满足产品体验，同时最小化敏感数据、集中幂等和状态机，并允许将来替换/增加 Provider。

## Alternatives Considered

- App 自建卡表单并将卡数据发送 Backend。
- 直接跳 Mercado Pago 通用支付链接。
- 单次支付同时由用户勾选保存卡。
- 仅依赖 Webhook payload 更新支付。

## Rejected Alternatives

自建卡表单扩大敏感范围；通用链接难以支撑充电状态机和保存卡；混合单次/保存用途增加授权歧义；只信 Webhook 无法防伪造、乱序和金额/商户不匹配。

## Consequences

- Hosted HTML/SDK 需要浏览器、sandbox 和 3DS 独立测试。
- App 只管理非敏感 session 引用和恢复状态。
- 生产支付总门禁在 QA/E2E/人工审查前保持关闭。
- C2 多商户分账需要新 ADR，不得在 merchant resolver 中静默启用。

## Affected Modules

App payment/charging、payment checkout、provider adapter、reconciliation、wallet、billing、deployment config。
