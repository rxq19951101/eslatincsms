---
id: PAY-MP-002-FE-209A
change_id: CHG-20260812-002
feature_id: PAY-MP-002
status: done-awaiting-independent-frontend-qa
owner: frontend-agent
contract_version: PAY-MP-002-v2
scope: admin-chargeback-read-and-audit-adapter-boundary
---

# FE-209A Admin read-only handoff

## Delivered

- Added ChargebackCase read-only list/detail presentation with server filters for status and deadline range, cursor pagination, canonical status including `unknown`, deadline, hold/funds state, safe references, version, `allowed_actions`, and safe timeline.
- Chargeback requests use the existing Admin tenant header path; cache keys remain scope-specific and platform scope does not fabricate a tenant.
- Added explicit ChargebackCase response decoding and sensitive/unknown-field filtering; no Provider raw evidence is rendered.
- Preserved the frozen AuditEvent adapter boundary with server filter/cursor parameters and recursive safe-metadata filtering. No AuditEvent UI or mock projection was added.

## Historical blocker and correction

- The original handoff stopped Audit UI expansion because the backend AuditEvent projection was not yet evidenced. BE-212 subsequently supplied the frozen `/api/v1/admin/audit-events` projection and independent backend QA closed that dependency.
- The fresh FE-209A blocker was frontend-only: `safeObject` did not normalize all sensitive key naming variants or recurse into nested objects/arrays.

## Explicit exclusions

- No FE-207 RefundCase approval workflow.
- No SupportCase operation/event workflow, FE-210 rail work, backend, migration, frozen contract, production configuration, or real payment changes.

## Verification

- `npx vitest run lib/__tests__/payMp002.test.ts lib/__tests__/payMp002Foundation.test.ts lib/__tests__/payMp002Chargeback.test.ts`: 3 files, 13 tests passed.
- `npx tsc --noEmit --pretty false`: passed.
- `npx next build --webpack`: passed; 18/18 static pages generated.
- `git diff --check`: passed.

## FE-209A sensitive-boundary correction

- `safeObject` now normalizes keys by removing separators and lowercasing before rejecting PAN/PANNumber/CVV/token/secret/credential and raw/provider payload variants.
- Sanitization recurses through nested objects and arrays, retaining only safe scalar and safe nested values.
- Targeted fixtures cover snake_case, camelCase, acronym/uppercase variants and nested arrays/objects; no raw Provider payload content is returned.

Status is `done-awaiting-independent-frontend-qa`; fresh independent QA must re-run the FE-209A sensitive-boundary probe.
