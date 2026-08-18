# PAY-MP-002 Production Release-Readiness Review

```text
CHANGE_ID: CHG-20260812-002
FEATURE_ID: PAY-MP-002
REVIEW_DATE: 2026-08-17
SCOPE: read-only production release-readiness audit and human-review preparation
STATUS: awaiting-human-release-review
VERDICT: NO-GO
PRODUCTION_AUTHORIZATION: NO
PAYMENT_RAILS_EFFECTIVE_VALUE: unverified; required value is false
```

## Decision

This review does not authorize a production deployment, production payment canary,
Provider credential activation, or any change to `PAYMENT_RAILS_ENABLED`. The
current gate is `awaiting-human-release-review`, with a release verdict of
`NO-GO`. The remaining items are production evidence, implementation/operations,
Provider, and human-approval gates; they are not silently converted into a
production-ready or `GO` state.

## Evidence boundary

The evidence below is repository documentation and local/test evidence only. No
production database, production environment file, production secret, production
Provider credential, real funds, deployment command, or payment-rail change was
used. The `.env.production.example` file and Compose defaults are templates/static
inputs, not proof of effective production runtime values.

## Minimum gate review

| Gate | Evidence reviewed | Result | Required closure |
|---|---|---|---|
| Product and technical architecture | `PRODUCT_ARCHITECTURE.md`, `TECH_ARCHITECTURE.md`, PAY-MP-002 architecture/ADR records | Architecture and contract direction is recorded; production authorization is separate | Human release review and operational evidence |
| Frozen contract and boundaries | PAY-MP-002-v2 contract and backend/frontend references | Passed for contract scope; no contract change in this review | Implementation and independent QA remain required |
| Backend QA | `qa/BACKEND_QA_REPORT.md`, including BE-214 final independent re-QA | Passed for bounded local/test scope | Production schema, capacity, runtime, and release evidence remain open |
| Frontend QA | `qa/FRONTEND_QA_REPORT.md`, including FE-210 evidence | Passed for local/test scope | Production environment and release evidence remain open |
| Cross-module E2E | `qa/E2E_QA_REPORT.md` latest local/test evidence | Direct-card Provider/Webhook/settlement/idempotency slice passed; overall current E2E remains blocked by dirty baseline and remaining journeys | Clean test baseline, remaining cross-module journeys, production, D-204 runtime, and human gates |
| Provider create/webhook/settlement | Sandbox wallet-top-up and charging-direct Checkout/Card Token/confirm/settlement/Webhook evidence; charging direct used exact `1,011 COP` and same-payment Webhook was idempotent | **Passed for bounded Sandbox slices; not a production release approval** | Remaining reconciliation/operations evidence, production credential/webhook approval, D-204 and human release review |
| Production environment completeness | `docker-compose.prod.yml`, `.env.production.example`, `production-first-deploy.md`, `validate_prod_env.sh` | **Not evidenced**; only template/static checks exist and no real `.env.production` was read | Human-owned environment inventory, approved secret source, and successful non-secret validation evidence |
| Secret separation and rotation | Production template placeholders and environment governance | **Not evidenced**; no runtime secret source, rotation record, or recovery owner was supplied | Confirm secret provider/separation, rotation schedule, access owner, and recovery procedure |
| HTTPS, domains, and Provider webhook URL | Caddyfile, production runbook, HTTPS URL/CORS template values | Static configuration is present; DNS, certificate issuance, runtime HTTPS, and Provider-console webhook URL/signature are **not evidenced** | Human verification of DNS/TLS and exact HTTPS webhook registration/signature path |
| CORS | Template and validator specify exact admin HTTPS origin and reject wildcard | Static check is defined; runtime origin verification is **not evidenced** | Confirm deployed origin and browser/API verification |
| Database backup and restore | Production Compose and deployment documentation | **Not evidenced**; no backup schedule, immutable retention, restore drill, RPO/RTO, or owner | Provide approved backup/restore evidence and named owner |
| Redis, queue, and Outbox | Redis AOF/healthcheck in Compose; no queue/consumer service in production Compose; E2E records residual pending Outbox in test | **Not evidenced** for production durability, consumer drain, lag, or capacity | Provide recovery, consumer/lag, capacity, and failure-recovery evidence |
| Health and readiness | Compose healthchecks, Caddy healthcheck, `/livez`/`/readyz` runbook checks | Static checks/runbook exist; no production runtime observation | Human-confirmed health/readiness checks and failure behavior |
| Logging and alerting | Caddy JSON logs and application monitoring settings | Logging is statically configured; `ENABLE_METRICS=false` in the template and no alert sink/routing/incident test is evidenced | Approve observability settings, alert routes, retention, and on-call test |
| Migrations policy | Production Compose/runbook and repository migration conventions | **Not evidenced**; no production migration preflight, ordering, backup gate, or rollback drill is recorded | Name migration owner and approve expand/contract, preflight, and rollback policy |
| `PAYMENT_RAILS_ENABLED=false` gate | Compose default and `.env.production.example` set false; production validator now explicitly rejects any value other than `false` | **Hard no-go until runtime value is proven false** | Human confirms approved production source and effective false value; no agent may enable it |
| Rollback and kill switch | Payment rail flag is documented; no production rehearsal/effective-value or rollback drill is evidenced | **Not evidenced** | Approve and rehearse rollback/kill-switch procedure while rails remain false |
| Admin bootstrap | `production-first-deploy.md`, `validate_prod_env.sh`, and `app-super.md` | Procedure exists but execution is **not evidenced**; Compose `db-role-init` runs role-creation SQL while `app-super.md` requires DBA pre-provisioning/read-only production startup | Human owner must resolve this deployment-governance conflict and confirm bootstrap-password clearing |
| Provider production credentials | Production template leaves Provider values blank; no approved production credential source or rotation evidence | **Not passed** | Named owner approval, secret injection/rotation evidence, webhook secret/signature verification, and no sandbox values |
| Human release checklist | No completed signed checklist or release decision is recorded | **Not passed** | Complete `HUMAN_RELEASE_REVIEW_REQUEST.md`; keep `NO-GO` until explicit owner decision |

## Blocking findings

## New bounded local capacity observation — 2026-08-18 UTC

`csms/scripts/measure_be211_capacity.py --rows 200 --workers 8 --batch-size 50`
completed against the local/test-only harness. It observed bounded pool
checkouts, lock wait behavior, deterministic queue lease/DLQ handling,
reconciliation cursor batching, and fail-closed persistence fallback when Redis
was unavailable. The measurement explicitly reported
`production_capacity_claim=false` and used synthetic SQLite/fake Provider
calls; it is supporting evidence only and does not close D-204/BE-205,
PostgreSQL/Redis production capacity, alerting, or release gates.

## New bounded Sandbox Provider evidence — 2026-08-18 UTC

Using the existing `.env.test.local` Sandbox credentials and the approved test
card only (no production credentials or production account), an isolated
provider-level probe completed:

- Card token creation: HTTP `201`; token was created and was not written to the
  repository or printed.
- Payment creation: HTTP `201`; Provider payment ID was present; status
  `approved`, status detail `accredited`; amount `2,001 COP`.
- Active payment query: HTTP `200`; Provider payment ID was present; status
  `approved`, status detail `accredited`; amount `2,001 COP`.

This closes only the provider create/query observation. It does **not** prove
that the local Checkout Session is linked to the Provider payment, that a
signed Mercado Pago Webhook reaches the canonical local endpoint, that
PaymentOrder/Invoice settlement and reconciliation are correct, or that a
duplicate notification is idempotent. Those remain release blockers.

### Order-linked wallet top-up continuation

The subsequent local/test run closed the wallet-top-up slice: Checkout Session
creation/query returned `200`, test Card Token creation returned `201`, hosted
confirmation returned `303`, and the Session became `approved` with a local
PaymentOrder. A valid Mercado Pago signature for that Provider payment was
accepted twice (`200`, `200`); the handler actively queried Sandbox and the
read-only database check showed `2` Webhook events and exactly `1` wallet
ledger entry. Wallet readback was `2001.0 COP` without a duplicate top-up.

This is still **partial** for release purposes. The tested purpose was
`wallet_top_up`, not `charging_direct`; Invoice exact-amount settlement,
charging allocation/reconciliation, and clean no-unpaid-balance charging E2E
remain open.

### Direct-card runtime continuation — 2026-08-18 UTC (closed)

A fresh verified zero-balance local AppUser completed the direct-card journey
after the existing test Compose was rebuilt and restarted. The entrypoint's
existing `alembic upgrade head` completed successfully without adding migration
files. The final Invoice/Provider amount was exactly `1,011 COP`, Provider status
was approved, and the PaymentOrder, Invoice and Session were paid/completed. The
automatic signed Webhook returned `200` and the corrected reconciliation path
logged an idempotent same-payment observation without `duplicate_approved` or
`refund_required`. Focused reconciliation regression: `13 passed`.

### Latest full backend regression — 2026-08-18

The existing test Compose was rebuilt and restarted using the registered test
entry. Its existing `alembic upgrade head` startup step completed successfully.
The full backend regression then completed once:

```text
Command: cd csms && python3 -m pytest -q
Result: 559 passed, 5 skipped, 20 warnings in 143.35s
```

This is local/test evidence only. It closes the current backend regression and
direct-card runtime slice, but does not close production credentials, DNS/TLS,
backup/restore, production Redis/Outbox, capacity/alerting, rollback, or human
release review. Production remains `NO-GO` and `PAYMENT_RAILS_ENABLED=false`.

| ID | Finding | Classification |
|---|---|---|
| PRD-001 | Sandbox wallet-top-up and charging-direct order-linked signed Webhook, exact Invoice settlement and same-payment idempotency are evidenced; full production reconciliation/operations remain open | Provider/release evidence gate |
| PRD-002 | No actual production environment or approved runtime secret/rotation evidence was inspected | Human/operations gate |
| PRD-003 | Database backup/restore, migration policy execution, rollback, and kill-switch rehearsal are unproven | Operations gate |
| PRD-004 | Production Redis/Outbox consumer drain, lag/capacity, alerting, and recovery evidence are unproven | Implementation/operations QA gate |
| PRD-005 | `docker-compose.prod.yml` role initialization conflicts with the production `app-super.md` DBA pre-provision/read-only rule | Governance/deployment decision required |
| PRD-006 | The required effective `PAYMENT_RAILS_ENABLED=false` value is not runtime-proven; the validator now enforces fail-closed validation but has not been run against the real production environment | Hard safety gate |
| PRD-007 | Human release checklist, production credential approval, and release decision are absent | Human approval gate |

D-204/BE-205 runtime and capacity gaps remain implementation/QA/release gates.
They are not treated as a new product decision or as permission to invent risk
behavior. The approved D-204 window and contract do not by themselves authorize
production operation.

## Production actions explicitly prohibited for this task

- Do not read or connect to a production database, Redis instance, Provider account, or secret store.
- Do not run production Compose `config`/`up`, deploy, migrate, bootstrap admin, or alter roles.
- Do not create, rotate, copy, or validate real production secrets or credentials.
- Do not configure DNS/TLS, Provider-console webhooks, payment credentials, or real funds.
- Do not set or infer `PAYMENT_RAILS_ENABLED=true`; do not run a payment canary.
- Do not execute backup/restore, rollback, kill-switch, or production traffic tests.

## Required human release decision

The formal questions, evidence requests, ownership fields, and explicit decision
options are recorded in
[`HUMAN_RELEASE_REVIEW_REQUEST.md`](./HUMAN_RELEASE_REVIEW_REQUEST.md). Until the
responsible owner completes that review and records a permitted decision, the
release remains `awaiting-human-release-review` and `NO-GO`.

## Scope and safety confirmation

- Only release-readiness documentation is in scope for this review.
- No business code, database, migration, deployment file, production config, secret, or payment rail was changed.
- No production command or production-connected test was executed.
- Local/test QA and E2E passes are retained as bounded evidence and are not promoted to production evidence.
