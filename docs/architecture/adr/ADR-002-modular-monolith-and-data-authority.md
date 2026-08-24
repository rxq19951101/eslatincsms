# ADR-002 — Modular Monolith and Data Authority

- Status: accepted
- Date: 2026-08-12
- Related Change ID: CHG-20260812-001

## Context

CSMS 同时承载 REST、OCPP、支付和后台任务。系统需要在单 VPS 上可运营，同时保持领域边界，并区分持久业务事实与实时协调状态。

## Decision

维持 FastAPI 模块化单体。PostgreSQL 是租户、资产、会话、账单、支付和审计的权威持久事实源；Redis 仅承担实时状态、短期去重、Checkout、限流和分布式协调。App/Admin 只通过 Backend contract 访问事实。

## Reason

当前规模下单体部署更简单，数据库事务清晰；通过显式 service/provider 边界可以控制耦合，同时保留未来拆分可能。

## Alternatives Considered

- 立即拆为 OCPP、Billing、Payment 微服务。
- 使用 Redis 作为在线状态和支付最终事实。
- Frontend 直接调用支付 Provider 和数据库服务。

## Rejected Alternatives

微服务增加运维和分布式一致性成本；Redis 不适合成为账务真相；Frontend 直连破坏密钥、租户和审计边界。

## Consequences

- `main.py` 和集中模型需要持续控制复杂度。
- 新跨域调用必须通过明确 service/contract。
- 将领域拆成独立服务属于 C3，需要新 ADR 和迁移策略。

## Affected Modules

CSMS、PostgreSQL、Redis、App、Admin、部署。
