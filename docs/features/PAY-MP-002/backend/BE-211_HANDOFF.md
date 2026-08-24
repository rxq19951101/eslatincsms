# PAY-MP-002 / BE-211 backend handoff

## Scope and gate

This handoff covers local/test-only compatibility checks, deterministic test-data cleanup boundaries, bounded synthetic capacity measurements, and inputs for independent backend QA and later E2E. It does not create or modify a migration, import historical data, operate a production database, call a real Provider, change frontend code, or enter D-204/BE-205 risk runtime.

The measurement output is an engineering observation from temporary SQLite and deterministic fakes. It is not a PostgreSQL, production-TPS, p95, or release-capacity claim.

## Reproducible commands

Run from `csms/`:

```text
python3 -m pytest -q tests/test_pay_mp_002_be211_compatibility.py
python3 -m pytest -q tests/test_cleanup_sim_e2e.py tests/test_pay_mp_002_be201_schema.py
python3 scripts/measure_be211_capacity.py --rows 200 --workers 8 --batch-size 50
python3 -m compileall -q -f app tests scripts/measure_be211_capacity.py
git diff --check
```

The measurement script is disabled when `ENVIRONMENT=production`. It uses a temporary local SQLite file, a bounded local connection-pool checkout probe, a bounded fake Provider burst, and a failing Redis double. It emits JSON containing database write rate/index-plan evidence, a lock wait probe, pool checkout wait, queue lease/retry/DLQ counts, bounded fake-provider in-flight count, MeterValues fallback behavior, and cursor-bounded reconciliation throughput.

## Compatibility evidence

- Empty local schema: `Base.metadata.create_all` creates the current model schema, and a second invocation is non-destructive.
- Current test schema: repeated `create_all` leaves an existing Tenant fact intact.
- No historical import or guessed backfill is performed. Existing BE-201 migration compatibility remains covered by its independent PostgreSQL QA evidence; BE-211 does not add another migration path.
- Cleanup is deterministic and allowlist-based. `cleanup_sim_e2e` refuses environments outside development/test and only permits `--apply` for approved local PostgreSQL/Compose hosts. A tenant-wide or email-wide delete is not used.
- Runtime rollback/disable evidence remains the BE-210 boundary: close/unknown applies only to matching new payment/admission entries; Webhook/query/refund/chargeback/reconciliation/history/support and OCPP StopTransaction continue to converge; unknown states fail closed; no payment-close RemoteStop is introduced.

## Contract and regression input

The independent QA handoff should run and retain exact results for:

- P001 default `/app/transactions` bare-array/offset/legacy-number golden behavior and P002 vendor `Accept` cursor/decimal-string envelope/detail golden behavior.
- OCPP idempotency/StartTransaction/MeterValues fallback/StopTransaction convergence and Webhook signature/replay/active-query paths.
- Admin route/permission/HTTP/error/sort and reconciliation CSV lifecycle contracts, plus SupportCase and rail-control scope/approval behavior.
- BE-201 typed schema ownership, currency/status/immutability and Outbox tenant/platform `scope_type/scope_ref` constraints.
- BE-202 through BE-210 key paths: Recovery idempotency and provider transaction boundary; FinancialEligibility/D1 re-block; provider-neutral P001 compatibility; history projections; refund/chargeback; three-way reconciliation lease/retry/DLQ; SupportCase/RBAC; dual-axis rail control.

Unknown, processing, mismatch, failed-health, or missing-fact states must remain explicit and fail closed; no fixture may turn an unknown state into a pass by assumption.

## E2E fixture contract input

The later E2E agent may use only local/test deterministic fixtures:

| Fixture | Required facts | Required assertions |
|---|---|---|
| unpaid recovery | one tenant, one AppUser, one owned Session/Invoice, no guessed history | D1 blocked; recovery references immutable Invoice and exact COP amount |
| wallet/card recovery | wallet, fake Provider, one idempotency key, one duplicate/replay | one allocation winner; unknown/retryable stays unresolved; no real Provider |
| OCPP convergence | pre-registered test ChargePoint, Start/Meter/Stop messages, replay key | StopTransaction and final MeterValues remain authority; rail close does not stop an active session |
| Admin operations | tenant and platform actors, separate approval actors, scoped typed facts | cross-tenant resources are hidden; close/reopen/refund/temporary exception require frozen permissions and actor separation |
| dirty-data safety | deterministic SIM-E2E IDs plus unrelated prefixed rows | dry-run changes nothing; apply removes only allowlisted references; production guard rejects |

E2E must verify UI, API, database, async/outbox state, permission/tenant facts, and recovery after unknown status. It must not publish, use real funds, or alter production configuration.

## Residual risks and next gate

- PostgreSQL lock behavior, production connection-pool sizing, real Redis/queue infrastructure, real Provider rate limits, and production capacity remain unproven.
- The script's SQLite lock result is not interchangeable with PostgreSQL lock-wait behavior.
- Frontend QA, cross-module E2E, human release review, and production launch gates remain separate.
- `PAYMENT_RAILS_ENABLED` must remain `false`; D-204/BE-205 remains blocked.

```text
STATUS: done-awaiting-independent-backend-qa
TASK: PAY-MP-002 / BE-211
OWNER: backend-agent
CHANGED_FILES:
- csms/tests/test_pay_mp_002_be211_compatibility.py
- csms/scripts/measure_be211_capacity.py
- docs/features/PAY-MP-002/backend/BE-211_HANDOFF.md
- docs/features/PAY-MP-002/backend/TASKS.md
- docs/features/PAY-MP-002/STATUS.md
CONTRACT_CHANGES: none
MIGRATION_CHANGES: none
PRODUCTION_CHANGES: none
NEXT_ALLOWED_TASK: independent backend QA; then frontend QA/E2E only after the applicable gates pass
```

## E2E remediation handoff — 2026-08-14

```text
STATUS: done-awaiting-independent-e2e-rerun
OWNER: backend-agent-<nickname>
TASK: PAY-MP-002 / CHG-20260812-002 / E2E remediation
SCOPE: local/test support files only

CHANGED_FILES:
- csms/tests/test_sim_e2e_p0.py
- docker-compose.test.yml
- docs/features/PAY-MP-002/backend/BE-211_HANDOFF.md

PRESERVED_RELEVANT_EXISTING_CHANGES:
- csms/tests/conftest.py sample_commercial_charge_point fixture reused unchanged
- sample_charge_point remains draft for explicit CHARGER_NOT_COMMISSIONED rejection tests
- docs/features/PAY-MP-002/qa/E2E_QA_REPORT.md was not modified
- production Compose files, frontend, migrations, frozen contract, payment/OCPP business code were not modified

FIXED:
- StartTransaction replay now uses the existing commissioned commercial fixture, including its valid test tariff; the draft fixture remains isolated for negative commissioning coverage.
- docker-compose.test.yml now supplies CORS_ORIGINS as a JSON array string accepted by Pydantic settings.
- No substitute MQTT image or MQTT bypass was introduced.

COMMANDS_RUN:
- `python3 -m pytest -q tests/test_sim_e2e_p0.py::test_unique_id_replay_returns_first_transaction_result`
- `python3 -m pytest -q tests/test_ocpp_message_handler.py::TestOCPPMessageHandler::test_handle_start_transaction tests/test_ocpp_message_handler.py::TestOCPPMessageHandler::test_handle_start_transaction_rejects_uncommissioned_charger tests/test_meter_telemetry_service.py::test_meter_values_use_redis_and_minute_database_sample`
- `python3 -m pytest -q tests/test_sim_e2e_p0.py tests/test_cleanup_sim_e2e.py`
- `python3 -m pytest -q tests/test_ocpp_message_handler.py tests/test_phase3_charging_domain.py tests/test_db_write_p0.py tests/test_meter_telemetry_service.py tests/test_user_charging_flow.py`
- `PYTHONPYCACHEPREFIX=/private/tmp/eslatin_compile_cache_pay_mp_002_e2e_remediation python3 -m compileall -q -f app tests`
- `docker compose -f docker-compose.test.yml config`
- `git diff --check`
- bounded Docker image/stack inspection attempted; daemon did not respond and no stack mutation was performed

TEST_RESULTS:
- replay target: `1 passed`
- commissioning success/rejection and telemetry regression: `3 passed`
- SIM-E2E plus cleanup: `26 passed, 1 warning`
- related backend regression: `23 passed, 1 warning`
- compile: passed
- Compose config: passed; CORS_ORIGINS rendered as valid JSON
- Docker-backed runtime: not verified because the local Docker daemon did not respond; no alternate image or MQTT bypass used

CONTRACT_CHANGES:
- none; PAY-MP-002-v1 remains frozen
MIGRATION_CHANGES: none
PRODUCTION_CHANGES: none

ARCHITECTURE_COMPLIANCE:
- C0 test-support correction within the existing backend test owner boundary; production commissioning/tariff gates remain unchanged.
- No API, database, event, tenant, payment, OCPP, frontend, production Compose, or architecture change.

RISKS:
- Independent e2e-agent should rerun the Compose-backed journey matrix when the Docker daemon/test images are available; this handoff does not close the cross-module E2E gate.
- Production remains NO-GO and PAYMENT_RAILS_ENABLED remains false.
```
