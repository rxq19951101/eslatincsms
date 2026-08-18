---
id: PAY-MP-002-FE-210
change_id: CHG-20260812-002
feature_id: PAY-MP-002
status: done-awaiting-independent-frontend-qa
owner: frontend-agent
contract_version: PAY-MP-002-v2
scope: admin-dual-axis-runtime-rail-workspace
---

# FE-210 Admin runtime rail handoff

## Delivered

- Added explicit Admin adapters for the frozen RuntimeRailControl and RailReopenRequest projections, including allowlisted fields, canonical status normalization, actor/scope/version/UTC fields, and sensitive/unknown field exclusion.
- Added close, reopen-request, and reopen-decision intents for the frozen endpoint paths with idempotency keys and expected versions.
- Added a Provider-neutral Admin workspace with separate `paid_admission` and `payment_creation` sections. Actions are gated by both fixed permissions and server-provided `allowed_actions`; the UI does not infer authority or actor separation.
- Added safe handling for `unknown` rail state and server rejection of failed/unknown health checks; no client-side auto-recovery is performed.
- Displayed the boundary that rail close does not stop Webhook/query/refund/chargeback/reconciliation/history/support or active OCPP sessions.

## Explicit exclusions

- No D-204 risk runtime UI.
- No FE-207 RefundCase approval workflow or complete SupportCase workflow.
- No backend, migration, frozen contract, production configuration, Provider, or real payment changes.

## Verification

- `npx vitest run lib/__tests__/payMp002.test.ts lib/__tests__/payMp002Foundation.test.ts lib/__tests__/payMp002Rail.test.ts lib/__tests__/payMp002Reconciliation.test.ts lib/__tests__/payMp002Chargeback.test.ts`: 5 files, 20 tests passed.
- `npx tsc --noEmit --pretty false`: passed.
- `npx next build --webpack`: passed; 18/18 static pages generated. Existing warning: invalid `--localstorage-file` path from the environment.
- `git diff --check`: passed.

## Contract and architecture

- Contract changes: none. Frozen PAY-MP-002-v2 RuntimeRailControl endpoint/projection semantics remain unchanged; P001/P002, Hosted boundary, Decimal/UTC and canonical errors remain untouched.
- Runtime rail close remains an operational control only. It does not stop convergence or active OCPP sessions.
- Platform scope is displayed as `platform:eslatin`; the UI does not fabricate a tenant scope. Tenant cache keys remain scope-isolated.

Status is `done-awaiting-independent-frontend-qa`; this is an implementation handoff, not an independent QA approval.

## E2E media-type boundary correction

- Fixed the shared Admin API client response parser to recognize `application/json` and any valid `type/subtype` whose subtype is `json` or ends in `+json`, including the frozen `application/vnd.eslatin.pay-mp-002.v1+json` response with parameters.
- Added an API-client regression using a real Audit cursor projection envelope. No reconciliation or CSV fixture was added or changed.
- Contract, P001/P002 compatibility, backend, migration, production configuration, and QA reports were not modified.

Status remains `done-awaiting-independent-frontend-qa`; this correction is not an independent QA approval.
