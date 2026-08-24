---
id: PAY-MP-002-FE-208
change_id: CHG-20260812-002
feature_id: PAY-MP-002
status: implementation-complete-awaiting-independent-frontend-qa
owner: frontend-agent
contract_version: PAY-MP-002-v2
scope: admin-reconciliation-and-csv-only
---

# FE-208 Admin reconciliation and CSV handoff

## Delivered

- Added typed Admin adapters for ReconciliationRun detail, Item/Exception cursor pages, resolution intent, temporary acceptance request/decision, and ReconciliationExport.
- Added a reconciliation Admin shell showing run status/version, source watermarks, safe summary, item/exception cursor pages, and server `allowed_actions`.
- Resolution actions remain server intents and carry `expected_version` plus `Idempotency-Key`; the UI never sets `matched` directly and never compares actors locally.
- Added CSV lifecycle presentation for `queued → generating → ready → downloaded`, with independent `failed`/`expired` states, canonical error mapping, audit reference, `text/csv` presentation, server-provided same-origin ready path, and a single-use filename/download link.
- Tenant scope is included in cache keys and confirmed reconciliation request context; platform scope remains tenantless.

## Explicit exclusions

- No FE-207 RefundCase approval work.
- No FE-209 Support/Chargeback/Audit workflow and no FE-210 rail workflow.
- No backend, migration, frozen contract, production configuration, mock projection, or real payment changes.
- No direct reconciliation status mutation or client-side approval authority.

## Verification

- `npx vitest run lib/__tests__/payMp002.test.ts lib/__tests__/payMp002Foundation.test.ts lib/__tests__/payMp002Reconciliation.test.ts`: 3 files, 15 tests passed.
- `npx tsc --noEmit --pretty false`: passed.
- `npx next build --webpack`: passed; 18/18 static pages generated and `/payments-operations` plus dynamic resource route compiled.
- `git diff --check`: passed.

This is an implementation handoff only. Independent frontend QA, E2E, production release and real payment remain pending.

## FE-208 QA correction handoff

- Corrected `createResolutionIntent`, `requestTemporaryAcceptance`, and `decideTemporaryAcceptance` to decode their frozen `ResolutionIntentProjection` or `TemporaryAcceptanceRequestProjection` response shapes instead of `ReconciliationExceptionProjection`.
- Added explicit frontend projection types and allowlisted decoder tests covering intent/request identifiers, reason/status/actor/timestamp fields, and unknown or sensitive response fields.
- No backend, migration, frozen contract, production configuration, FE-207, FE-209, or FE-210 changes were made.

Verification for this correction is recorded below; independent frontend QA must re-run after handoff.

- `npx vitest run lib/__tests__/payMp002.test.ts lib/__tests__/payMp002Foundation.test.ts lib/__tests__/payMp002Reconciliation.test.ts`: 3 files, 15 tests passed.
- `npx tsc --noEmit --pretty false`: passed.
- `npx next build --webpack`: passed; 18/18 static pages generated.
- `git diff --check`: passed.
