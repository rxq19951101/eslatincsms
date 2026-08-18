---
change_id: CHG-20260812-002
feature_id: PAY-MP-002
status: user-approved
approved_by: product-owner-user
approved_at_utc: 2026-08-13
source: explicit-user-response-required
---

# PRODUCT APPROVAL — PAY-MP-002

This is the effective product approval record. D-201, D-202, D-203, D-204-B and D-205～D-210 are explicitly approved. D-204-B is product-approved and now enters a separate architecture review; BE-205 runtime enforcement, its validation evidence and every real-money rollout remain blocked until that review and QA gates are complete.

## User approval record

- Exact user response (verbatim): “批准 D-201、D-202；D-204 暂不批准，保持待定；D-205～D-210 保持待定。”
- Latest exact user response (verbatim): “D-205 A, D-206-B, D-207-B, D-208-B,D-209-B, D-210-B 批准”
- Final product-baseline response (verbatim): “产品已确认，D-204放入todo，进行代码架构审核，如遇block 向我人工确认”
- Prior explicit approval retained: “先确认方案1，后续会接其他支付平台，留拓展空间”
- Decision IDs approved in the latest response: D-205, D-206, D-207, D-208, D-209, D-210
- Decision IDs approved cumulatively: D-201, D-202, D-203, D-205, D-206, D-207, D-208, D-209, D-210
- Selected option(s): D-201 full bill-level recovery; D-202 new card, saved card with CVV and wallet, subject to server/provider availability; D-203 Option 1 — Keep A1 and add a quantified risk budget; D-205-A; D-206-B; D-207-B; D-208-B; D-209-B; D-210-B
- Numeric/business parameters approved: D-204-B — single-session cap 200,000 COP / 100 kWh / 180 minutes (first limit wins); user open-unpaid exposure cap 250,000 COP; site periodic exposure cap 1,000,000 COP; platform total exposure cap 5,000,000 COP; site/platform periodic window is rolling 24 hours using UTC timestamps, with no midnight reset; active reservations and unresolved exposure count, while released/settled exposure does not count; MeterValues degradation after 120 seconds and automatic stop after 300 seconds; offline/unknown additional exposure 15,000 COP or 5 minutes (first limit wins); Provider unknown uses automatic status reconciliation for up to 24 hours without duplicate charge, then automatic debt/account freeze; RemoteStop starts within 10 seconds with up to three automatic retries; StopTransaction confirmation target 5 minutes; recovery checks within 15 minutes and final resolution within 24 hours; routine cases are automated and manual handling is limited to physical stop failure, material payment-ledger mismatch or unresolved status after 24 hours.
- Scope approved: D-201 provides invoice list/detail, full bill-level repayment, processing/recovery state and D1 re-evaluation; D-202 allows new card, saved card with CVV and wallet subject to server/provider availability; D-203 adopts post-charge exact-Invoice settlement and keeps a provider-neutral extension seam; D-205-A provides basic in-App charging history/detail and payment result only, without downloadable/email receipt or DIAN invoice; D-206-B provides structured refund/problem cases, two-person controlled full/partial refunds and the proposed 1/3-business-day service targets; D-207-B provides continuous matching plus daily three-way reconciliation, 24-hour temporary timing exceptions and next-business-day 12:00 Bogotá close; D-208-B provides scoped two-axis emergency control with one-person close, different-person reopen approval and no automatic reopen; D-209-B provides contextual in-App cases, email notification and a staffed emergency route during advertised paid-site hours; D-210-B provides the R0～R4 staged allowlisted rollout with the proposed R2/R3 limits and explicit Product Owner promotion.
- Scope explicitly not approved: D-205-B/C, downloadable/PDF/email receipt and DIAN electronic invoice; D-206-A/C; D-207-A/C; D-208-A/C; D-209-A/C; D-210-A/C; any specific future provider, routing rule, fee rule, split settlement, technical implementation, deployment or production GO.
- Approved by: Product Owner (user)
- Approval timestamp (UTC): 2026-08-13

## Transition authorization

- Previous state: `awaiting-user-approval`
- D-201 state: `user-approved`
- D-202 state: `user-approved`
- D-203 state: `user-approved`
- D-204 state: `user-approved` (`D-204-B`; product baseline updated; architecture review required before BE-205 implementation)
- D-205 state: `user-approved` (`D-205-A`)
- D-206 state: `user-approved` (`D-206-B`)
- D-207 state: `user-approved` (`D-207-B`)
- D-208 state: `user-approved` (`D-208-B`)
- D-209 state: `user-approved` (`D-209-B`)
- D-210 state: `user-approved` (`D-210-B`)
- Overall product state: `product-baseline-updated`
- Authorized only by explicit user responses: YES, for D-201, D-202, D-203, D-204-B and D-205～D-210
- Product baseline update: complete for D-204-B product behavior; architecture/contract/implementation/QA gates remain separate
- Final architecture review may start: YES
- Implementation may start: NO

## D-204-B approval addendum

- Exact user response (verbatim): “批准 D-204-B”
- Approval timestamp (UTC): 2026-08-15
- Exact window approval response (verbatim): “批准 D-204-B 窗口方案 A”
- Window approval timestamp (UTC): 2026-08-15
- Approved window semantics: site and platform use the same rolling 24-hour window based on UTC timestamps; no calendar-midnight reset; active reservations and unresolved exposure are included; released and settled exposure is excluded.
- Product state transition: `awaiting-user-approval` → `user-approved` → `product-baseline-updated` → `architecture-review`
- Approved operating principle: automate normal payment-unknown, device-stop and recovery paths; reserve human handling for physical stop failure, material ledger mismatch or unresolved Provider status after 24 hours.
- This approval does not approve database schema, API fields, risk-ledger implementation, OCPP worker implementation, deployment, production configuration or production payment enablement.
