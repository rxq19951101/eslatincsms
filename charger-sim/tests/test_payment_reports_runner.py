from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path
import hashlib
import hmac

import httpx

from actors.fake_payment import FakePaymentActor
from reports.redaction import REDACTED, redact
from reports.writers import write_all_reports
from runner import ScenarioRunner
from scenario.schema import validate_scenario_data
from simulator.payment_simulator import get_session_id_by_transaction, simulate_charging_payment


class FakePaymentTests(unittest.IsolatedAsyncioTestCase):
    async def test_integer_transaction_id_is_never_a_session_uuid(self) -> None:
        with self.assertRaises(TypeError):
            await simulate_charging_payment(123, 10, "CP-1")
        with self.assertRaisesRegex(RuntimeError, "cannot be used"):
            await get_session_id_by_transaction(123, "CP-1", "http://localhost")

    async def test_fake_payment_has_no_real_provider_call(self) -> None:
        session_id = str(uuid.uuid4())
        self.assertTrue(await simulate_charging_payment(session_id, 10, "CP-1", status="approved"))
        self.assertFalse(await simulate_charging_payment(session_id, 10, "CP-1", status="rejected"))

    async def test_missing_webhook_path_fails_instead_of_synthesizing_success(self) -> None:
        actor = FakePaymentActor("payment", {"environment": "test"}, "run-1")
        with self.assertRaisesRegex(RuntimeError, "webhook_path is required"):
            await actor.execute(
                "emit_webhook",
                {"session_id": str(uuid.uuid4()), "status": "approved"},
                "payment",
            )
        await actor.close()

    async def test_local_signed_duplicate_and_out_of_order_delivery(self) -> None:
        received = []
        seen = set()
        secret = "unit-only-secret"

        def handler(request: httpx.Request) -> httpx.Response:
            received.append(request)
            payload = json.loads(request.content)
            canonical = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
            expected = "sha256=" + hmac.new(
                secret.encode("utf-8"), canonical, hashlib.sha256
            ).hexdigest()
            self.assertEqual(request.headers["x-sim-signature"], expected)
            self.assertEqual(request.headers["idempotency-key"], payload["event_id"])
            replayed = payload["event_id"] in seen
            seen.add(payload["event_id"])
            return httpx.Response(
                200,
                json={
                    "provider": "fake",
                    "status": payload["status"],
                    "order_status": "approved",
                    "event_id": payload["event_id"],
                    "payment_order_id": payload["payment_order_id"],
                    "session_id": None,
                    "session_payment_status": None,
                    "wallet_balance": "10000.00",
                    "webhook_event_count": 1,
                    "ledger_entry_count": 1,
                    "replayed": replayed,
                },
            )

        actor = FakePaymentActor(
            "payment",
            {
                "environment": "test",
                "base_url": "http://localhost:9000",
                "webhook_path": "/api/v1/app/payments/webhooks/sim",
                "webhook_secret": secret,
            },
            "run-1",
        )
        await actor.client.aclose()
        actor.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await actor.execute(
            "emit_webhook",
            {
                "payment_order_id": str(uuid.uuid4()),
                "statuses": ["approved", "pending"],
                "duplicate": 2,
                "event_id": "stable-event",
            },
            "payment",
        )

        self.assertEqual(result.status, 200)
        self.assertEqual(result.body["delivery_count"], 4)
        self.assertEqual(len(received), 4)
        self.assertEqual(received[0].headers["idempotency-key"], received[1].headers["idempotency-key"])
        self.assertNotEqual(received[1].headers["idempotency-key"], received[2].headers["idempotency-key"])
        self.assertTrue(all(request.headers.get("x-sim-signature", "").startswith("sha256=") for request in received))
        self.assertFalse(result.body["deliveries"][0]["response"]["replayed"])
        self.assertTrue(result.body["deliveries"][1]["response"]["replayed"])
        self.assertEqual(result.body["deliveries"][3]["response"]["ledger_entry_count"], 1)
        await actor.close()

    async def test_payload_requires_exactly_one_uuid_resource_and_secret(self) -> None:
        actor = FakePaymentActor(
            "payment",
            {
                "environment": "test",
                "base_url": "http://localhost:9000",
                "webhook_path": "/api/v1/app/payments/webhooks/sim",
                "webhook_secret": "unit-secret",
            },
            "run-1",
        )
        with self.assertRaisesRegex(ValueError, "exactly one"):
            await actor.execute("emit_webhook", {"status": "approved"}, "missing")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            await actor.execute(
                "emit_webhook",
                {
                    "status": "approved",
                    "session_id": str(uuid.uuid4()),
                    "payment_order_id": str(uuid.uuid4()),
                },
                "both",
            )
        await actor.close()

        unsigned = FakePaymentActor(
            "payment",
            {
                "environment": "development",
                "base_url": "http://localhost:9000",
                "webhook_path": "/api/v1/app/payments/webhooks/sim",
            },
            "run-2",
        )
        with self.assertRaisesRegex(RuntimeError, "SIM_E2E_WEBHOOK_SECRET"):
            await unsigned.execute(
                "emit_webhook",
                {"payment_order_id": str(uuid.uuid4()), "status": "approved"},
                "unsigned",
            )
        await unsigned.close()


class ReportTests(unittest.TestCase):
    def test_sensitive_values_are_redacted(self) -> None:
        card_number = "4060" + " 4914" + " 4768" + " 0666"
        value = {
            "password": "literal",
            "headers": {"Authorization": "Bearer abc.def.ghi"},
            "card": card_number,
            "error": "request failed: https://local.test/check?qr_token=top-secret-value",
            "qr": "qr:server-assigned-full-token",
            "payment_signature": "signature-value",
            "payment_headers": {"X-Sim-Signature": "sha256=must-not-leak"},
        }
        output = redact(value)
        self.assertEqual(output["password"], REDACTED)
        self.assertNotIn("abc.def.ghi", json.dumps(output))
        self.assertNotIn(card_number, json.dumps(output))
        self.assertNotIn("top-secret-value", json.dumps(output))
        self.assertNotIn("server-assigned-full-token", json.dumps(output))
        self.assertNotIn("signature-value", json.dumps(output))
        self.assertNotIn("must-not-leak", json.dumps(output))

    def test_all_written_report_formats_exclude_runtime_secrets(self) -> None:
        forbidden = {
            "password-value",
            "full-qr-token-value",
            "sha256=full-signature-value",
            "eyJabcdefgh.ijklmnop.qrstuvwx",
        }
        data = {
            "run_id": "run-redaction",
            "scenario_id": "redaction",
            "outcome": "FAIL",
            "steps": [
                {
                    "step_id": "payment",
                    "actor": "payment",
                    "action": "emit_webhook",
                    "start": "start",
                    "end": "end",
                    "duration_seconds": 0,
                    "outcome": "FAIL",
                    "error": (
                        "Bearer eyJabcdefgh.ijklmnop.qrstuvwx "
                        "qr:full-qr-token-value signature=sha256=full-signature-value"
                    ),
                    "result": {
                        "password": "password-value",
                        "headers": {"X-Sim-Signature": "sha256=full-signature-value"},
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_all_reports(data, Path(temp_dir))
            rendered = "\n".join(
                Path(path).read_text(encoding="utf-8") for path in paths.values()
            )
        for secret in forbidden:
            self.assertNotIn(secret, rendered)


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_writes_json_junit_and_timeline_with_run_id(self) -> None:
        document = validate_scenario_data(
            {
                "schema_version": "1.0",
                "scenario": {"id": "runner-unit"},
                "environment": {},
                "actors": {},
                "steps": [
                    {
                        "id": "assert",
                        "actor": "system",
                        "action": "assert",
                        "with": {"actual": "${run_id}", "equals": "${run_id}"},
                    },
                ],
                "reports": {},
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await ScenarioRunner(document, report_dir=Path(temp_dir), process_environment={}).run()
            self.assertEqual(result.outcome, "PASS")
            self.assertEqual(len(result.run_id), 36)
            self.assertEqual(set(result.reports), {"json", "junit", "timeline"})
            self.assertTrue(all(Path(path).exists() for path in result.reports.values()))

    async def test_missing_environment_is_blocked_and_reported(self) -> None:
        document = validate_scenario_data(
            {
                "schema_version": "1.0",
                "scenario": {"id": "blocked-unit"},
                "environment": {"password": "${REQUIRED_PASSWORD}"},
                "actors": {},
                "steps": [{"id": "noop", "actor": "system", "action": "sleep", "with": {"seconds": 0}}],
                "reports": {},
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await ScenarioRunner(document, report_dir=Path(temp_dir), process_environment={}).run()
            self.assertEqual(result.outcome, "BLOCKED")
            self.assertEqual(result.steps[0].outcome, "BLOCKED")
            self.assertTrue(all(Path(path).exists() for path in result.reports.values()))


if __name__ == "__main__":
    unittest.main()
