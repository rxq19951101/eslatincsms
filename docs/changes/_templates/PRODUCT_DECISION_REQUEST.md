---
template: PRODUCT_DECISION_REQUEST
change_id: <CHANGE_ID>
status: awaiting-user-approval
created_by: product-agent-<nickname>
created_at_utc: <YYYY-MM-DDTHH:MM:SSZ>
---

# PRODUCT DECISION REQUEST — <CHANGE_ID>

## Purpose

This document requests an explicit Product Owner decision. It is not an approval record. All options below remain `draft`/`proposed` until the user names the selected option.

## Decision(s) requiring user approval

| Decision ID | Question requiring a decision | Option A | Option B | Recommendation (non-binding) |
|---|---|---|---|---|
| <D-XXX> | <precise question> | <option> | <option> | <recommendation or none> |

## Consequences and scope

- User-visible behavior:
- Money/risk/settlement impact:
- Permission/tenant/operations impact:
- External integration or legal/compliance impact:
- Included scope if approved:
- Explicitly excluded scope:

## Required response

The user must reply with the exact option and decision IDs, for example: `批准 D-XXX 选择方案 A，并批准 D-YYY 的参数为 ...`.

Replies that do not identify a specific option/decision do not change the state. Silence, recommendations, technical feasibility, historical decisions, “继续/推进/ok/确认” and ambiguous replies are not approval.

## Gate state

- Current state: `awaiting-user-approval`
- Next allowed state: `user-approved` only after an explicit user response
- Architecture review: blocked until `PRODUCT_APPROVAL.md` exists and covers these decisions
- Implementation: blocked

## Handoff

```text
STATUS: awaiting-user-approval

CHANGED_FILES:
- <files containing draft analysis only>

COMMANDS_RUN:
- <commands>

TEST_RESULTS:
- Not applicable; no business code changed

CONTRACT_CHANGES:
- None; no contract freeze permitted

RISKS:
- User decision is required for <decision IDs>
```
