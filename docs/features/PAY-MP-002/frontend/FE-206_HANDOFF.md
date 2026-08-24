---
id: PAY-MP-002-FE-206
change_id: CHG-20260812-002
feature_id: PAY-MP-002
status: implementation-complete-awaiting-independent-frontend-qa
owner: frontend-agent
contract_version: PAY-MP-002-v2
scope: admin-foundation-only
---

# FE-206 Admin foundation handoff

## Scope delivered

- Added a Provider-neutral Admin Payments Operations entry point and six read-only resource routes: refunds, chargebacks, reconciliation, support, rails and audit.
- Added the frozen PAY-MP-002 permission vocabulary, resource `allowed_actions` helper, scope/version/cache foundation, and canonical error-to-i18n mapping.
- Added cursor-page adapters for the six Admin projection shells. Requests use the frozen PAY-MP-002-v1 media type; sensitive/raw Provider fields are not exposed by the projection decoders.
- Added scope, version, safe timeline count, allowed-actions and canonical-error presentation to the foundation shell.
- Platform scope remains `platform:eslatin` with `tenantId: null`; no dummy or selected tenant is fabricated.

## Explicit exclusions

- No backend, migration, contract, production configuration or real payment changes.
- No D-204 risk runtime UI, risk commands or risk parameter display.
- No FE-207+ refund approval, reconciliation decision/export, rail close/reopen, or complete Support workflow.
- No frontend authority for tenant, RBAC, status transitions, amounts or Provider results; `allowed_actions` remains server UX guidance and requests remain server-authorized.

## Verification

- `npx vitest run lib/__tests__/payMp002.test.ts lib/__tests__/payMp002Foundation.test.ts`: 2 files, 11 tests passed.
- `npx tsc --noEmit --pretty false`: passed.
- `git diff --check`: passed.
- Admin webpack build was not run in this focused correction pass because the bounded request required only targeted tests, typecheck and diff validation; independent frontend QA may run the build gate.

This is an implementation handoff only. It does not self-approve independent frontend QA, E2E, production release or real payment.
