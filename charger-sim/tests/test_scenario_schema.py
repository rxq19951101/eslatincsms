from __future__ import annotations

import unittest
from pathlib import Path
import re

import yaml

from scenario.loader import discover_scenarios, load_scenario
from scenario.schema import ScenarioValidationError, validate_scenario_data
from scenario.seed import SeedContractError, normalize_seed
from scenario.variables import build_environment, resolve_value


def base_scenario() -> dict:
    return {
        "schema_version": "1.0",
        "scenario": {"id": "unit-scenario"},
        "environment": {"admin_password": "${ADMIN_PASSWORD}"},
        "actors": {
            "admin": {
                "type": "admin",
                "base_url": "http://localhost:9000",
                "password": "${admin_password}",
            }
        },
        "steps": [
            {
                "id": "login",
                "actor": "admin",
                "action": "login",
                "with": {"username": "admin", "password": "${admin_password}"},
                "expect": {"status": 200},
                "save": {"user_id": "body.user.id"},
                "timeout": 2,
                "retry": 1,
            },
            {
                "id": "assert-user",
                "actor": "system",
                "action": "assert",
                "with": {"actual": "${user_id}"},
                "depends_on": ["login"],
            },
        ],
        "reports": {},
    }


class ScenarioSchemaTests(unittest.TestCase):
    def test_valid_dsl_10_fields(self) -> None:
        document = validate_scenario_data(base_scenario())
        self.assertEqual(document.schema_version, "1.0")
        self.assertEqual(document.steps[0].retry, 1)
        self.assertEqual(document.steps[0].save["user_id"], "body.user.id")

    def test_unknown_action_is_rejected(self) -> None:
        data = base_scenario()
        data["steps"][0]["action"] = "drop_database"
        with self.assertRaisesRegex(ScenarioValidationError, "unknown"):
            validate_scenario_data(data)

    def test_duplicate_step_id_is_rejected(self) -> None:
        data = base_scenario()
        data["steps"][1]["id"] = "login"
        with self.assertRaisesRegex(ScenarioValidationError, "duplicate step id"):
            validate_scenario_data(data)

    def test_undefined_variable_is_rejected(self) -> None:
        data = base_scenario()
        data["steps"][1]["with"] = {"actual": "${never_saved}"}
        with self.assertRaisesRegex(ScenarioValidationError, "undefined variable"):
            validate_scenario_data(data)

    def test_literal_secret_is_rejected(self) -> None:
        data = base_scenario()
        data["actors"]["admin"]["password"] = "literal"
        with self.assertRaisesRegex(ScenarioValidationError, "literal secrets"):
            validate_scenario_data(data)

    def test_invalid_ocpp_identity_is_rejected(self) -> None:
        data = base_scenario()
        data["actors"]["charger"] = {
            "type": "charger",
            "ws": "ws://localhost:9000/ocpp",
            "ocpp_identity": "bad identity",
        }
        with self.assertRaisesRegex(ScenarioValidationError, "ocpp_identity is invalid"):
            validate_scenario_data(data)

    def test_all_p0_examples_validate(self) -> None:
        root = Path(__file__).resolve().parents[1] / "scenarios" / "p0"
        paths = discover_scenarios([root])
        self.assertGreaterEqual(len(paths), 8)
        self.assertTrue(all(load_scenario(path).id.startswith("p0-") for path in paths))

    def test_seed_root_is_a_declared_runtime_input(self) -> None:
        data = base_scenario()
        data["actors"]["admin"]["tenant_id"] = "${seed.tenant_id}"
        validate_scenario_data(data)

    def test_seed_normalization_extracts_qr_without_printing_it(self) -> None:
        seed = normalize_seed(
            {
                "schema_version": "1.0",
                "environment": "test",
                "qr": {"payload": "qr:server-controlled-token"},
            }
        )
        self.assertEqual(seed["qr"]["token"], "server-controlled-token")
        with self.assertRaises(SeedContractError):
            normalize_seed({"schema_version": "1.0", "environment": "production"})

    def test_seed_11_fixtures_are_normalized_to_stable_scenario_aliases(self) -> None:
        seed = normalize_seed(
            {
                "schema_version": "1.1",
                "environment": "development",
                "fixtures": {
                    "admins": {
                        "operator": {"username": "operator"},
                        "readonly": {"username": "reader"},
                    },
                    "app_users": {
                        "funded": {"email": "funded@example.test"},
                        "low_balance": {"email": "low@example.test"},
                        "other": {"email": "other@example.test"},
                    },
                    "tenants": {
                        "tenant_a": {"id": "tenant-a"},
                        "tenant_b": {"id": "tenant-b"},
                    },
                    "charge_points": {
                        "primary": {"id": "cp-a", "ocpp_identity": "CP-A"},
                        "other": {"id": "cp-other", "ocpp_identity": "CP-OTHER"},
                        "tenant_b": {"id": "cp-b", "ocpp_identity": "CP-B"},
                    },
                    "qrs": {
                        "primary": {"payload": "qr:primary-server-token"},
                        "other": {"payload": "qr:other-server-token"},
                        "tenant_b": {"payload": "qr:tenant-b-server-token"},
                    },
                    "ownership_session": {"id": "session-id"},
                    "fake_top_up_order": {"id": "order-id"},
                    "fault_alert": {"id": "alert-id"},
                },
            }
        )
        self.assertEqual(seed["readonly_admin"]["username"], "reader")
        self.assertEqual(seed["low_balance_app_user"]["email"], "low@example.test")
        self.assertEqual(seed["tenant_b"]["charge_point"]["id"], "cp-b")
        self.assertEqual(seed["other_qr"]["token"], "other-server-token")
        self.assertEqual(seed["fake_top_up_order"]["id"], "order-id")

    def test_seed_11_rejects_incomplete_fixture_contract(self) -> None:
        with self.assertRaisesRegex(SeedContractError, "fixtures.tenants"):
            normalize_seed(
                {"schema_version": "1.1", "environment": "test", "fixtures": {}}
            )

    def test_all_p0_runtime_inputs_resolve_from_seed_and_four_secrets(self) -> None:
        seed = normalize_seed(
            {
                "schema_version": "1.1",
                "environment": "test",
                "fixtures": {
                    "tenants": {
                        "tenant_a": {"id": "tenant-a"},
                        "tenant_b": {"id": "tenant-b"},
                    },
                    "admins": {
                        "operator": {"username": "operator"},
                        "readonly": {"username": "readonly"},
                    },
                    "app_users": {
                        "funded": {"email": "funded@example.test"},
                        "low_balance": {"email": "low@example.test"},
                        "other": {"email": "other@example.test"},
                    },
                    "charge_points": {
                        "primary": {"id": "cp-a", "ocpp_identity": "SIM-CP-A"},
                        "other": {"id": "cp-other", "ocpp_identity": "SIM-CP-OTHER"},
                        "tenant_b": {"id": "cp-b", "ocpp_identity": "SIM-CP-B"},
                    },
                    "qrs": {
                        "primary": {"payload": "qr:primary-token-value"},
                        "other": {"payload": "qr:other-token-value"},
                        "tenant_b": {"payload": "qr:tenant-b-token-value"},
                    },
                    "ownership_session": {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "payment_order_id": "22222222-2222-2222-2222-222222222222",
                    },
                    "fake_top_up_order": {
                        "id": "33333333-3333-3333-3333-333333333333"
                    },
                    "fault_alert": {"id": "44444444-4444-4444-4444-444444444444"},
                },
            }
        )
        process_environment = {
            "SIM_API_BASE": "http://localhost:9000",
            "SIM_OCPP_WS": "ws://localhost:9000/ocpp",
            "SIM_E2E_ADMIN_PASSWORD": "env-admin-password",
            "SIM_E2E_APP_PASSWORD": "env-app-password",
            "SIM_E2E_READONLY_PASSWORD": "env-readonly-password",
            "SIM_E2E_WEBHOOK_SECRET": "env-webhook-secret",
        }
        root = Path(__file__).resolve().parents[1] / "scenarios" / "p0"
        for path in discover_scenarios([root]):
            document = load_scenario(path)
            values = build_environment(
                document.environment,
                process_environment,
                {"seed": seed, "run_id": "run", "scenario_id": document.id},
            )
            for actor in document.actors.values():
                resolve_value(actor.config, values)

    def test_p0_files_freeze_qa_invariants_without_manual_runtime_ids(self) -> None:
        root = Path(__file__).resolve().parents[1] / "scenarios" / "p0"
        data = {
            path.stem: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in root.glob("*.yml")
        }
        self.assertEqual(len(data), 9)
        rendered = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.yml"))
        self.assertNotIn("SIM_ALERT_ID", rendered)
        self.assertNotIn("SIM_SESSION_UUID", rendered)
        env_references = set(re.findall(r"\$\{(SIM_[A-Z0-9_]+)\}", rendered))
        self.assertEqual(
            env_references,
            {
                "SIM_API_BASE",
                "SIM_OCPP_WS",
                "SIM_E2E_ADMIN_PASSWORD",
                "SIM_E2E_APP_PASSWORD",
                "SIM_E2E_READONLY_PASSWORD",
                "SIM_E2E_WEBHOOK_SECRET",
            },
        )

        low_step = next(
            step for step in data["low_balance"]["steps"] if step["id"] == "start-denied"
        )
        self.assertEqual(low_step["expect"]["status"], 402)
        self.assertEqual(
            low_step["expect"]["body.error.details.0.code"], "INSUFFICIENT_BALANCE"
        )
        fault_step = next(
            step for step in data["fault_alert"]["steps"] if step["id"] == "discover-deduplicated-alert"
        )
        self.assertEqual(fault_step["expect"]["body"]["count"], 1)
        self.assertEqual(fault_step["save"]["alert_id"], "body.0.id")
        payment_step = next(
            step
            for step in data["ownership_fake_payment"]["steps"]
            if step["id"] == "approved-first-and-replay"
        )
        self.assertEqual(
            payment_step["with"]["payment_order_id"],
            "${seed.fake_top_up_order.id}",
        )
        self.assertEqual(
            payment_step["expect"]["body.deliveries.1.response.ledger_entry_count"],
            1,
        )
        self.assertTrue(
            payment_step["expect"]["body.deliveries.1.response.replayed"]
        )
        acceptance_steps = {
            step["id"]: step for step in data["real_device_acceptance"]["steps"]
        }
        self.assertEqual(
            acceptance_steps["authenticated-connect"]["with"]["ocpp_secret"],
            "${device_secret}",
        )
        self.assertTrue(
            acceptance_steps["acceptance-report"]["expect"]["body.passed"]
        )
        self.assertEqual(
            acceptance_steps["commission"]["expect"]["body.commissioning_status"],
            "commissioned",
        )


if __name__ == "__main__":
    unittest.main()
