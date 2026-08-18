---
change_id: CHG-20260812-002
feature_id: PAY-MP-002
status: resolved-product-baseline-approved
created_by: root-main-thread
created_at_utc: 2026-08-13
---

# PRODUCT DECISION REQUEST — PAY-MP-002

## Purpose

PAY-MP-002 is a C3 payment/public-launch closure change. The Product Owner has explicitly approved D-201, D-202, D-203 and D-205～D-210, confirmed the overall product baseline, and moved D-204 to TODO. This request is retained as decision history. Architecture review is authorized for the approved scope; D-204-dependent runtime risk enforcement and real-money rollout remain excluded until separately approved.

## Decision D-203 — charging-time payment/risk route

The decision is now recorded:

- **Option 1 — Keep A1 and add a quantified risk budget:** keep PAY-MP-001 A1, form the final Invoice after charging, then charge the exact amount; do not use Mercado Pago preauthorization, freeze, pre-debit or final capture. Control exposure with approved COP/kWh/time/user/site/platform limits, safe stop and unpaid recovery/D1 re-evaluation.
- **Option 2 — Provider authorization/capture route:** remains an unapproved candidate. It may be researched non-constraintively, but cannot be treated as the current route or a deferred/non-goal.

The explicit user response is recorded in `PRODUCT_APPROVAL.md`: Option 1 is `user-approved` for D-203 only. The user also approved the provider-neutral extensibility principle, not any specific future Provider, routing, fee, split, settlement or implementation design.

## Decision D-204 — risk budget and stop policy (required if Option 1 is selected)

Approve concrete values or state that they are still pending:

| Parameter | Required user decision |
|---|---|
| Single-session maximum COP exposure | `<value and currency>` |
| Single-session maximum energy | `<value kWh>` |
| Single-session maximum duration | `<value and timezone/clock basis>` |
| User/day or rolling-period exposure | `<value and scope>` |
| Site/tenant/day or rolling-period exposure | `<value and scope>` |
| Platform-wide exposure | `<value and scope>` |
| Provider/OCPP/MeterValues unknown or offline buffer | `<value and rule>` |
| Stop trigger and safety margin | `<precise rule>` |
| RemoteStop initiation/confirmation/escalation SLA | `<values>` |
| Unpaid recovery/D1 re-evaluation SLA | `<values>` |

No default values may be inferred. Technical feasibility does not approve these business limits.

## Approved decisions retained

| Decision ID | Approved product scope |
|---|---|
| D-201 | Invoice list/detail, full invoice-level repayment, processing recovery and final D1 re-evaluation. Partial repayment is not approved. |
| D-202 | New card, saved card with CVV and wallet; the server/provider determines actual availability. |
| D-203 | Keep A1: charge the exact final Invoice amount after charging, controlled by a quantified risk budget. Keep a provider-neutral extension seam; no future provider or routing rule is approved. |
| D-205 | `D-205-A`: basic in-App charging history/detail and payment result only; no PDF/download/email receipt and no DIAN electronic invoice. |
| D-206 | `D-206-B`: structured refund/problem cases, two-person controlled full/partial refunds, visible status and proposed 1/3-business-day service targets. |
| D-207 | `D-207-B`: continuous matching plus daily three-way reconciliation, 24-hour temporary timing exception and next-business-day 12:00 Bogotá close. |
| D-208 | `D-208-B`: scoped two-axis emergency control, one-person close, different-person reopen approval, no automatic reopen and no payment-close forced stop of active sessions. |
| D-209 | `D-209-B`: contextual in-App cases, email notification and a staffed emergency route during each public paid site's advertised hours. |
| D-210 | `D-210-B`: R0～R4 staged allowlisted rollout with the proposed R2/R3 limits and explicit Product Owner promotion. |

## Benchmark evidence used for D-205～D-210

The following public material is supporting evidence, not a claim that every competitor exposes the same internal implementation:

- Tesla exposes charging history and downloadable charging invoices, and gives users a Pay Now path for unpaid charging balances; unpaid balances may prevent new charging. See [Tesla Supercharging support](https://www.tesla.com/support/charging/supercharging).
- Electrify America exposes charge history, date filtering and receipt sharing; it also distinguishes the final actual charge from a temporary authorization hold and publishes an emergency support route for charger failures. See [Electrify America mobile FAQ](https://www.electrifyamerica.com/mobile-faq/).
- ChargePoint exposes station-owner Analytics, Financial and Logs reports, filtering and CSV export. See [ChargePoint reporting](https://docs.chargepoint.com/cpdocs-sec/content/3-dc/express-250/omg/reporting.htm).
- Mercado Pago documents signed Webhooks followed by authoritative resource queries, full/partial refunds with idempotency, and All Transactions reports for reconciliation. See [Mercado Pago Webhooks](https://www.mercadopago.com.co/developers/es/docs/checkout-api-payments/additional-content/your-integrations/notifications/webhooks), [refunds/cancellations](https://www.mercadopago.com.co/developers/es/docs/checkout-api-payments/payment-management/cancellations-and-refunds) and [transaction reports](https://www.mercadopago.com.co/developers/es/docs/reports/account-money/panel).
- A charging/payment receipt and a Colombian DIAN electronic tax invoice are different product/compliance deliverables. D-205 therefore does not silently promise a DIAN tax invoice; that requires a separate legal/tax decision and verified issuer/integration process. See [DIAN electronic invoicing](https://www.dian.gov.co/impuestos/factura-electronica/Paginas/default.aspx).

## Decision D-205 — history, receipt and tax-document boundary

### Product problem

Users need one place to understand what happened during charging, what was billed, whether money moved, whether a refund changed the result, and what evidence can be shared with support. A charging session, Invoice, Payment, Refund and Chargeback are related facts, but are not interchangeable statuses.

### Candidate options

| Option | Scope | Advantages | Trade-offs |
|---|---|---|---|
| **D-205-A — Basic history** | Charging list/detail and in-app payment result only; no downloadable document or email delivery. | Lowest initial effort. | Weak evidence and support experience; users cannot preserve/share a stable receipt; below the public-launch experience of the referenced networks. |
| **D-205-B — Unified activity + commercial receipt** **(recommended)** | Unified history/detail, explicit financial timeline, downloadable commercial charging/payment receipt, email resend and refund correction records. It is clearly labelled as a commercial receipt, not automatically as a DIAN tax invoice. | Gives users and support a complete evidence path without making an unverified tax promise; aligns with Tesla/Electrify America history and receipt patterns. | Requires stable projections/PDF generation and approved issuer wording; DIAN invoice remains a separate compliance workstream. |
| **D-205-C — B plus DIAN electronic invoice in P0** | Everything in B plus requesting/generating/delivering a compliant Colombian electronic tax invoice. | Strongest fiscal experience. | Adds legal/tax identity, numbering, issuer, tax, DIAN integration, correction-note and retention dependencies; may delay the first paid launch. |

### D-205-A approved scope

1. App provides a basic charging history list and charging detail.
2. Detail shows station, charger/connector, start/end, delivered kWh, frozen tariff, final COP amount and current payment result where available.
3. The history distinguishes at least charging in progress/completed, payment processing/paid/unpaid, refund/partial refund/refunded and dispute states when those facts affect the record.
4. The record is restored from server facts across refresh/login/device changes and provides the D-209 support entry.
5. P0 does not generate a receipt document, PDF, download, email copy, monthly statement or DIAN electronic invoice.

### Unselected D-205-B product flow retained for future reference

1. App adds `Actividad` with `Cargas` and `Pagos y reembolsos` views; both point to the same server facts rather than duplicated local records.
2. A charge detail shows station, charger/connector, start/end, delivered kWh, frozen tariff, subtotal/tax/fees/discounts when applicable, final COP amount and non-sensitive references.
3. A financial timeline distinguishes `En curso`, `Por pagar`, `Pago en proceso`, `Pagado`, `Reembolso en proceso`, `Reembolso parcial`, `Reembolsado`, `En disputa` and `Requiere ayuda`.
4. A final settled transaction exposes `Ver comprobante`, `Descargar PDF` and `Enviar por correo`. Processing, unpaid and disputed records expose status/recovery/support instead of a misleading final receipt.
5. The commercial receipt contains the approved EsLatin collecting-entity name, receipt reference, charging/Invoice/payment references, timestamps, station/connector, energy, tariff snapshot, gross/adjustment/net COP amounts and payment brand/last four digits where allowed. It never contains PAN, CVV, identity number, card token or Provider secret.
6. A later refund does not overwrite the original receipt. The user sees the original evidence plus a linked full/partial refund adjustment and the new net amount.
7. Admin/support can search the same non-sensitive references and resend the same versioned document; support cannot edit financial facts.
8. P0 Spanish is the source language. Empty, loading, offline, processing, failed and recovered states must be explicit.

### D-205-B boundaries

- P0 document name is `Comprobante de carga y pago` (commercial charging/payment receipt), not `Factura electrónica` unless D-205-C is separately approved and legally validated.
- Email is a delivery copy; the server history remains the source of truth.
- Monthly statements, bulk export and advanced filters are P1; basic date/status filtering belongs to B.
- If the Product Owner chooses C, finance/legal must additionally approve issuer legal name/NIT, tax treatment, buyer identity rules, numbering, corrections/credit notes, DIAN Provider and retention before implementation.

### Decision result

`D-205-A` is `user-approved`. `D-205-B` and `D-205-C` are not approved.

## Decision D-206 — cancellations, refunds and chargeback/dispute experience

### Product problem

The product must distinguish: a payment that never completed and can be cancelled; money that was captured and must be refunded; a Provider chargeback/dispute; and a support complaint that has not yet changed any financial fact.

### Candidate options

| Option | Scope | Advantages | Trade-offs |
|---|---|---|---|
| **D-206-A — Support-only/manual** | User sends an email; operations handles Provider actions outside a structured App/Admin flow. | Fastest to launch. | Poor status transparency, higher duplicate-refund and audit risk, weak D1 recovery/re-block behavior. |
| **D-206-B — Structured request + controlled operator refund** **(recommended)** | User opens a contextual refund/problem request; Admin triages evidence; authorized operators issue idempotent full/partial refunds; App tracks status. | Strong public-launch balance of user clarity, financial control and operational feasibility. | Requires support case, refund workflow, permissions, audit and SLA ownership. |
| **D-206-C — Automatic rule-engine refunds** | Automatically approves refunds for configured technical/quality conditions, with manual exceptions. | Fastest user outcome at scale. | Highest fraud/accounting risk and rule complexity; not suitable before enough production evidence exists. |

### Proposed D-206-B product flow

1. From a charge/payment detail the user selects `Reportar un problema` and a reason: no energy delivered, charging interrupted, amount incorrect, duplicate charge, paid but still unpaid/D1 blocked, refund delayed, unrecognized charge or other.
2. The server first classifies the money state:
   - no approved/captured payment: cancellation/expiration, not a refund;
   - approved payment: eligible refund review;
   - processing/unknown: status investigation, with no second debit/refund attempt;
   - Provider chargeback/dispute: separate dispute case, not a user-created refund.
3. App immediately returns a case reference and `Recibido`; it does not promise approval before evidence review.
4. Support can inspect and classify but cannot directly mutate Invoice/Payment or mark a refund complete.
5. In P0, every manual money refund uses two-person control: one authorized operator proposes the exact full/partial amount and reason; a different finance/payment approver authorizes it. Provider calls are idempotent and cumulative refunds cannot exceed paid amount.
6. Refunds return to the original payment instrument. No cash, wallet conversion or alternate-card refund is promised in P0.
7. User states are `Solicitud recibida`, `En revisión`, `Aprobada`, `En proceso con el proveedor`, `Reembolso parcial`, `Reembolsada`, `Rechazada` and `Requiere intervención`; bank/issuer completion time is shown as externally dependent.
8. Refund reason determines billing impact:
   - duplicate payment: refund the duplicate while the valid Invoice remains paid; D1 stays clear;
   - confirmed no/incorrect service: create an authorized billing adjustment and refund; the adjusted Invoice must not create artificial debt;
   - unresolved chargeback or unpaid valid service: D1 is re-evaluated and may block, with a recovery/support path;
   - goodwill compensation is not implemented as a hidden Invoice refund in P0; it requires a later credit/benefit policy.
9. Provider insufficient balance, unknown response or timeout keeps the refund in processing/manual intervention and alerts finance; it never displays `Reembolsada` without authoritative confirmation.
10. Chargeback evidence and fraud detail remain internal. App shows a safe dispute status, amount impact and support entry.

### Proposed service levels for D-206-B

- Immediate automatic receipt and case reference.
- First human response within **1 business day**.
- Approve/reject target within **3 business days**, excluding time waiting for user/Provider evidence.
- Provider/bank credit timing is displayed separately and is not promised as EsLatin processing time.

### Decision result

`D-206-B` is `user-approved`, including two-person manual refund control and the proposed 1/3-business-day service levels. `D-206-A/C` are not approved.

## Decision D-207 — reconciliation model and completion criterion

### Product problem

Webhook success does not prove that EsLatin's Invoice, Provider transaction, fees/refunds/chargebacks, released balance and actual received funds all agree. Public paid charging needs a repeatable financial close, not only logs.

### Candidate options

| Option | Scope | Advantages | Trade-offs |
|---|---|---|---|
| **D-207-A — Manual Provider report reconciliation** | Finance downloads Mercado Pago reports and compares totals manually. | Lowest implementation effort. | Slow, weak per-transaction traceability, hard to scale and easy to miss duplicate/tenant/fee differences. |
| **D-207-B — Hybrid event + daily three-way reconciliation** **(recommended)** | Continuous transaction matching plus a daily close across EsLatin facts, Mercado Pago facts/reports and released/received funds; manual review only for typed exceptions. | Strong P0 control with a practical manual fallback; supports future Providers behind a neutral reconciliation model. | Requires exception queue, roles, evidence, scheduled close and operational ownership. |
| **D-207-C — Real-time accounting/ERP ledger** | Full double-entry/ERP integration, settlement automation and accounting close. | Best long-term finance automation. | Too broad for first public launch and tightly coupled to later C2 split settlement/accounting choices. |

### Proposed D-207-B product model

1. **Continuous match:** every Payment/Refund/Chargeback event is matched to User, tenant context, ChargingSession, immutable Invoice, PaymentOrder/Payment and Provider reference. Webhook is acknowledged, signature-validated and followed by authoritative Provider query.
2. **Daily three-way close:** reconcile the prior Bogotá business day across:
   - EsLatin gross Invoice/payment/refund/chargeback facts;
   - Mercado Pago transaction/report status, fee, net and release facts;
   - Mercado Pago available/released amount and bank/account receipt evidence when available.
3. Match dimensions include reference, amount, currency, merchant, tenant context, status, fee, refund, chargeback, release and net amount. The Provider payload is evidence, not the App/Admin public contract.
4. Admin provides a summary, transaction detail, exception queue, assignee, severity, evidence/notes, safe re-query/replay actions and CSV export. It does not allow arbitrary editing of paid/refunded states.
5. Exception states are `Pendiente de coincidencia`, `Coincide`, `Diferencia`, `Investigando`, `Riesgo aceptado temporalmente` and `Resuelto`.
6. Amount/currency/merchant/tenant mismatch, duplicate approval/debit, cross-user link and unexplained missing money can never be accepted as routine timing risk; they block expansion until resolved.
7. Temporary risk acceptance is allowed only for documented timing/fee/release differences, requires finance approver plus platform approver, names an owner and expires within **24 hours**. Expiry without resolution reopens the release block.
8. The prior day close is due by **12:00 America/Bogota on the next business day**. Internal timestamps remain UTC.
9. Completion means every item is matched or has a still-valid, explicitly authorized temporary timing exception; unexplained monetary variance is zero. A known open exception is visible, owned and time-bounded, never silently ignored.
10. Ordinary tenant Admins cannot close platform reconciliation. Future C2 tenant settlement reports are outside this P0 decision.

### Decision result

`D-207-B` is `user-approved`, including 24-hour temporary timing exceptions and next-business-day 12:00 Bogotá close. `D-207-A/C` are not approved.

## Decision D-208 — emergency close and safe recovery

### Product problem

An outage, duplicate-charge incident, security event, Provider failure or unexplained financial mismatch needs a fast way to stop new exposure without deleting facts, losing Webhooks or abruptly corrupting active charging sessions.

Public competitor material rarely exposes internal kill-switch design. The following is EsLatin's proposed safety control derived from its post-charge risk and reconciliation needs, not a claim that a named competitor uses the same control.

### Candidate options

| Option | Scope | Advantages | Trade-offs |
|---|---|---|---|
| **D-208-A — One global switch** | Stop all new paid charging and payment intake together. | Simple and fast. | Excessive blast radius; cannot keep wallet/recovery available when only one Provider is affected. |
| **D-208-B — Scoped two-axis emergency control** **(recommended)** | Separately close paid-charging admission and selected payment rails/scopes; preserve in-flight convergence and recovery services. | Limits new exposure with the smallest practical blast radius and supports future Providers. | Requires clearer RBAC, scope preview, state persistence and reopen checklist. |
| **D-208-C — B plus automatic circuit breaker** | Automated closure from error/risk thresholds in addition to manual control. | Fastest incident containment at scale. | False-positive and recovery complexity; requires stable production baselines and is better as P1 after observing real traffic. |

### Proposed D-208-B control behavior

1. Two independent control axes:
   - **Charging admission:** stop new paid charging starts in platform, tenant or site scope;
   - **Payment rail:** stop new card/save-card/direct/recovery attempts for a selected Provider/rail, while unaffected wallet or future Provider rails may remain available if explicitly healthy.
2. Webhook receipt, Provider queries, status convergence, Invoice finalization, refunds, reconciliation, history and support remain active while a rail is closed.
3. Active charging sessions are not automatically terminated by a payment emergency close. They continue to a safe final fact unless the separately approved D-204 risk-stop policy commands RemoteStop.
4. Closing a scope requires one authorized platform incident operator, a mandatory reason, incident reference, scope preview and confirmation. Speed is prioritized during containment.
5. Reopening requires a different authorized approver and a checklist confirming Provider health, Webhook/query health, reconciliation status, duplicate-risk check, D1 behavior and support readiness. There is no automatic expiry or automatic reopen.
6. Ordinary tenant administrators cannot operate the platform/provider switch. They may see an availability status and request platform assistance; tenant/site execution rights remain platform operations in P0.
7. Every close/reopen records actor, role, scope, reason, previous/new state, approval, timestamp and verification result.
8. App/Admin show a safe localized message such as `Pagos temporalmente no disponibles` or `No se pueden iniciar nuevas cargas pagadas`; they do not expose Provider secrets or misleadingly mark chargers offline.
9. A rollback means closing new admission while preserving/reconciling data. It never means deleting payments, reverting database history or discarding active-session facts.

### Decision result

`D-208-B` is `user-approved`, including one-person close, different-person reopen approval, no automatic reopen and no forced stop of active sessions outside D-204. `D-208-A/C` are not approved.

## Decision D-209 — contextual user support and operational case handling

### Product problem

Payment and charging failures are expensive to diagnose if users must copy technical IDs into email. At the same time, payment support must not collect PAN, CVV, identity documents or Provider secrets. Charging safety incidents also need a faster path than ordinary financial email.

### Candidate options

| Option | Scope | Advantages | Trade-offs |
|---|---|---|---|
| **D-209-A — Email link only** | Open `support@eslatin.com.co`; user manually describes the issue. | Minimal initial work. | Poor context, no case status, slow emergency response, higher sensitive-data collection risk. |
| **D-209-B — Contextual in-App case + email + site emergency route** **(recommended)** | Open a structured case from the relevant object, track status in App, notify by email, and expose a configured urgent site channel for stuck/unsafe charging. | Strong traceability and safer public-launch UX without requiring a full external CRM. | Requires case workflow, staffing/SLA and an emergency contact per public site or limited operating hours. |
| **D-209-C — Full omnichannel CRM** | B plus WhatsApp/SMS/chatbot/telephony CRM synchronization. | Best scale and channel coverage. | Adds vendors, consent, routing and operational complexity; not required for the first paid launch. |

### Proposed D-209-B product flow

1. `Ayuda` is available from active charging, D1 block, Invoice, Payment, Refund, Chargeback/dispute and receipt details.
2. The case automatically carries only safe context: user/case reference, object references, station/charger/connector, timestamps, visible status, amount/energy summary, app version and user-selected category. It never carries full card data, CVV, identity number, token or secret.
3. Categories route to different queues: cannot stop/unplug or safety issue; charging did not start/ended unexpectedly; no energy/incorrect energy; payment pending/failed; duplicate/incorrect amount; paid but D1 blocked; refund; receipt; unrecognized charge; other.
4. User states are `Recibido`, `Asignado`, `Esperando tu respuesta`, `En investigación`, `Resuelto` and `Cerrado`, with a visible case reference and conversation history.
5. `support@eslatin.com.co` receives/returns case notifications, but email text cannot replace the authoritative App/Admin case state.
6. A public paid site must publish a live emergency contact for cannot-stop/cable-stuck/safety cases. If EsLatin cannot staff 24/7, that site may operate paid charging only during declared staffed support hours; email alone is not accepted as an emergency route.
7. Proposed financial-support SLA follows D-206: first human response in 1 business day and target decision in 3 business days. Emergency contact availability follows the site's published charging hours.
8. Support agents can add notes/public replies and initiate a typed refund/reconciliation request, but cannot manually mark an Invoice paid, clear D1 or edit financial facts.
9. Photos are optional for physical charger/site issues and follow data/privacy limits; payment evidence must not request card images or identity documents through ordinary case attachments.
10. WhatsApp/SMS/chatbot and full CRM integration are P1 unless separately approved.

### Decision result

`D-209-B` is `user-approved`, including the rule that a public paid site needs a staffed emergency channel during its advertised operating hours. The actual phone/provider remains a later operational configuration and is not inferred here. `D-209-A/C` are not approved.

## Decision D-210 — production rollout level and GO/NO-GO policy

### Product problem

Passing one payment screen or one sandbox transaction is not enough to expose public users and real money. The release policy must combine PAY-MP-001 payment security with PAY-MP-002 recovery, receipt, refund, reconciliation, emergency control and support.

### Candidate options

| Option | Scope | Advantages | Trade-offs |
|---|---|---|---|
| **D-210-A — Direct public launch after one full gate** | Wait until every P0 condition passes, then enable all intended public users/sites at once. | Simple release state. | No controlled real-money learning phase; incident blast radius is larger. |
| **D-210-B — Staged allowlisted rollout** **(recommended)** | Sandbox → dark production readiness → internal real-money pilot → closed beta → public launch, with explicit entry/exit and rollback gates. | Best way to validate real Provider/device/money behavior while limiting exposure. | Requires allowlist, staffed pilot, daily review and deliberate promotion decisions. |
| **D-210-C — Internal pilot only** | Keep real-money access permanently restricted until a later Change. | Lowest public risk. | Does not deliver the requested public production capability. |

### Proposed D-210-B stages

| Stage | Exposure | Proposed exit evidence |
|---|---|---|
| **R0 — Sandbox/local** | No production money. Test new card, saved card+CVV, wallet, D1 recovery, duplicate/replay, refund, chargeback modeling, signed Webhook, Provider unknown and OCPP start/stop failures. | Backend/frontend/E2E evidence passes; no unresolved P0 defect; production credentials remain off. |
| **R1 — Production dark readiness** | Production deployment/configuration exists but paid rail/admission remains closed to users. | Credential/secrets review, signed production Webhook/query test, monitoring/alerts, backups, RBAC/audit, reconciliation, refund, support and D-208 drills pass. |
| **R2 — Internal real-money pilot** | Allowlist only; one approved site and the two pilot chargers; **maximum 10 users**, **minimum 20 completed paid sessions**, **minimum 7 consecutive days**, only during staffed support hours. | 100% session→Invoice→payment traceability; zero duplicate/overcharge/cross-tenant incident; zero unexplained monetary variance; D1 recovery, refund and emergency-close drills pass. |
| **R3 — Closed beta** | Invite-only; **maximum 50 users**, approved sites only; **minimum 100 completed paid sessions** and **14 consecutive days**. | Same zero-tolerance controls remain true; daily reconciliation closes on time; support/refund SLA is met; no open severity-0/1 incident. |
| **R4 — Public launch** | Public access only to approved sites/chargers and currently healthy payment rails. | Explicit Product Owner GO after reviewing R3 evidence; no automatic promotion. |

### Mandatory GO/NO-GO rules for D-210-B

- D-204 must be explicitly approved and its limits/stop behavior verified before any real-money R2 session. Approving D-210 does not approve D-204 values.
- The selected D-205～D-209 scopes and PAY-MP-001 production minimums must be implemented and independently verified before their dependent stage.
- Required zero-tolerance conditions: duplicate charge, overcharge, unauthorized/cross-tenant access, unexplained monetary variance and payment-success-without-traceable-Invoice.
- Every stage needs backend QA, frontend QA, E2E evidence and manual Product Owner promotion. Success in one transaction or one UI page is not a GO.
- Any zero-tolerance event, failed reconciliation close, unavailable emergency support, signature/authentication failure or inability to stop new exposure triggers D-208 closure and blocks promotion.
- Rollback preserves all payment, Invoice, charging, refund and audit facts; active sessions converge safely and affected users receive status/support guidance.
- D-210 approval is a release-policy approval only. It does not authorize deployment, production credentials, opening payment rails or public launch.

### Decision result

`D-210-B` is `user-approved`, including the proposed R2/R3 user/session/day limits. `D-210-A/C` are not approved. This does not authorize deployment, a production rail opening or promotion to any stage.

## Deferred TODO

D-204 remains unresolved by explicit Product Owner choice. The concrete COP/kWh/time/user/site/platform limits, unknown/offline buffer, stop trigger/margin, RemoteStop SLA and unpaid-recovery/D1 SLA must be decided before BE-205 runtime risk enforcement or any real-money rollout. No default may be inferred during architecture review.

## Gate state

- Current state: `resolved-product-baseline-approved`
- Product baseline update: completed for the approved scope; D-204 explicitly deferred to TODO
- Final architecture review: authorized for the approved scope
- Contract freeze and implementation: blocked
- Production configuration: unchanged and not authorized
