# PAY-MP-002 Human Release Review Request

```text
CHANGE_ID: CHG-20260812-002
FEATURE_ID: PAY-MP-002
REQUEST_DATE: 2026-08-17
STATUS: awaiting-human-release-review
CURRENT_VERDICT: NO-GO
PRODUCTION_AUTHORIZATION: NOT GRANTED
PAYMENT_RAILS_REQUIRED_VALUE: false
```

## Purpose and boundary

This is a formal request for the responsible release owner to review production
readiness. It records evidence and asks for explicit confirmations; it does not
authorize deployment, production database access, secret changes, Provider
credential activation, migrations, or payment-rail changes. A response to this
document must not be interpreted as approval beyond the exact scope explicitly
written by the responsible owner.

## Evidence currently available

The following evidence is available for the tested scope only:

- BE-214 independent backend re-QA passed with the frozen `EXPORT_FAILED=409`,
  `EXPORT_CONSUMED=410`, `EXPORT_EXPIRED=410`, and `EXPORT_NOT_READY=409`
  semantics; it is local/test evidence, not production evidence.
- FE-210 frontend QA and bounded media-type checks passed in local/test scope.
- Latest bounded local/test E2E passed for the recorded journeys. The E2E report
  retains the residual test Outbox pending state and does not claim a production
  consumer drain.
- PAY-MP-002-v2 contract and D-204-B architecture decisions are recorded. A
  frozen contract is not a production release approval.
- Production Compose, environment template, validator, Caddy configuration, and
  first-deploy runbook exist as static artifacts. No actual production runtime
  or secret source was inspected.
- On 2026-08-18 UTC, an isolated Sandbox provider-level probe using the existing
  test credentials/card created a card token (HTTP `201`), created a `2,001 COP`
  payment (HTTP `201`, payment ID present, `approved/accredited`), and actively
  queried it (HTTP `200`, `approved/accredited`, amount `2,001 COP`). The probe
  did not create a local Checkout Session or claim local Webhook,
  PaymentOrder/Invoice settlement, reconciliation, or duplicate-notification
  evidence.

## Evidence not passed or not supplied

- Order-linked signed webhook, settlement, reconciliation, and duplicate
  notification/idempotency evidence. Provider-level Sandbox create/query is
  now observed, but it is not sufficient to close this gate.
- Approved production Provider credential source, webhook registration, secret
  ownership, and rotation/revocation evidence.
- Complete production environment inventory and proof that runtime values are
  separated from templates/test values.
- DNS, certificate issuance, HTTPS routing, exact CORS origin, and Provider
  webhook URL runtime verification.
- Database backup schedule, immutable retention, restore drill, RPO/RTO, and
  named recovery owner.
- Redis persistence/recovery, Outbox/queue consumer drain, lag alerts, and
  production capacity evidence.
- Production health/readiness observation, logging retention, metrics, alert
  routing, on-call ownership, and incident test.
- Migration preflight/order/rollback policy and an approved migration owner.
- Rollback/kill-switch rehearsal and proof of effective
  `PAYMENT_RAILS_ENABLED=false` from the approved production source.
- Admin bootstrap execution evidence and confirmation that bootstrap passwords
  are cleared after setup.
- Resolution of the `db-role-init` versus `app-super.md` production role
  governance conflict: the Compose service currently executes role-creation SQL,
  while the deployment guidance requires DBA pre-provisioning and read-only
  production startup. The architecture agent does not choose between these
  alternatives.
- Completed human release checklist and release decision.

## Required owner confirmations

The responsible owner must complete each applicable item with evidence links,
owner, timestamp, and notes. An unchecked item keeps the release `NO-GO`.

- [ ] Confirm the current release decision is `NO-GO` and that no production
  deployment, canary, or payment-rail enablement is authorized by this request.
- [ ] Confirm the exact production environment source and secret provider, with
  separation from templates/test values, access ownership, rotation/revocation
  schedule, and recovery procedure.
- [ ] Confirm `admin.eslatin.com.co` and `api.eslatin.com.co` DNS, HTTPS/TLS,
  ACME ownership, certificate renewal, and the exact Provider HTTPS webhook URL.
- [ ] Confirm the deployed CORS allowlist is the approved exact origin and that
  HTTPS, webhook routing, signature verification, and replay behavior were
  checked by an authorized operator.
- [ ] Provide database backup schedule, retention/immutability, restore-drill
  evidence, RPO/RTO, and the named recovery owner.
- [ ] Provide Redis persistence/recovery evidence and Outbox/queue consumer,
  lag, retry, dead-letter, and capacity/alert evidence for production.
- [ ] Approve the production migration policy, preflight/order, backup gate,
  expand/contract compatibility, rollback procedure, and migration owner.
- [ ] Resolve the production `app_super` ownership conflict by recording the
  approved deployment procedure and responsible DBA/owner. No agent may silently
  change Compose or startup behavior during this review.
- [ ] Confirm `/livez` and `/readyz` behavior, logging/retention, metrics,
  alert routes, on-call contacts, and an incident/health-check rehearsal.
- [ ] Confirm the approved production source evaluates
  `PAYMENT_RAILS_ENABLED=false`, and approve a tested rollback/kill-switch
  procedure that does not enable payment rails.
- [ ] Approve Provider production credential ownership, least-privilege scope,
  rotation/revocation, webhook secret/signature verification, and confirmation
  that no sandbox credential is present.
- [ ] Confirm admin bootstrap ownership and that temporary bootstrap passwords
  are cleared/rotated after the initial controlled setup.
- [ ] Confirm remaining BE-205/D-204 runtime, Provider, capacity, and QA gates
  have explicit owners and evidence expectations before any future payment
  enablement decision.
- [ ] Confirm the final human decision and scope in one of these explicit forms:
  `NO-GO`; `readiness review accepted but deployment still not authorized`; or a
  separately named, time-bounded canary approval with owner, environment,
  rollback, and payment-rail scope. This document itself grants no such access.

## Human decision record

```text
DECISION: PENDING
DECISION_OWNER:
DECISION_DATE:
APPROVED_SCOPE:
EXCLUDED_SCOPE:
EVIDENCE_LINKS:
NOTES:
```

## Release rule

Until the owner completes the checklist and records an explicit decision, the
release gate remains `awaiting-human-release-review`; the status must not be
represented as `production-ready` or `GO`. `PAYMENT_RAILS_ENABLED` remains
required to be false, and no agent may perform the prohibited production actions
listed in `RELEASE_READINESS_REVIEW.md`.
