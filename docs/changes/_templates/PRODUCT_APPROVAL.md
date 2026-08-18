---
template: PRODUCT_APPROVAL
change_id: <CHANGE_ID>
status: pending | partial-user-approved | user-approved
approved_by: null
approved_at_utc: null
source: explicit-user-response-required
---

# PRODUCT APPROVAL — <CHANGE_ID>

This file must remain `pending` until the Product Owner explicitly selects an option by decision ID. It may be `partial-user-approved` when only some decision IDs are approved; the overall Change remains `awaiting-user-approval` until all required major decisions are covered. Do not fill it from an Agent recommendation, silence, technical feasibility, historical decision, “继续/推进/ok/确认”, or an ambiguous reply.

## User approval record

- Exact user response (verbatim):
- Decision IDs approved:
- Selected option(s):
- Numeric/business parameters approved:
- Scope approved:
- Scope explicitly not approved:
- Approved by:
- Approval timestamp (UTC):

## Transition authorization

- Previous state: `awaiting-user-approval`
- New state: `user-approved`
- Overall Change state after this record: `awaiting-user-approval` if any required decision remains uncovered
- Authorized only by the explicit user response above: YES | NO
- Product baseline may be updated only after all required fields are complete: YES | NO
- Architecture review may start only after baseline update and this record is verified: YES | NO

## Validation

- The response names an exact option/decision ID: YES | NO
- The record covers every decision required by the request: YES | NO
- Unapproved options remain draft/proposed: YES | NO
- No implementation or production configuration was authorized by implication: YES | NO
