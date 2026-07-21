from __future__ import annotations

import unittest
from unittest.mock import Mock, patch
import argparse
import tempfile
from pathlib import Path

import cli
import smoke_test


class CLIContractTests(unittest.TestCase):
    def test_run_one_accepts_distinct_identity_and_serial(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "run-one",
                "--ws",
                "ws://localhost:9000/ocpp",
                "--ocpp-identity",
                "CP-WS-123",
                "--serial-number",
                "SERIAL-BOOT-456",
                "--connector-id",
                "1",
            ]
        )
        self.assertEqual(args.ocpp_identity, "CP-WS-123")
        self.assertEqual(args.serial_number, "SERIAL-BOOT-456")

    def test_qr_sources_require_one_server_value_per_connector(self) -> None:
        with self.assertRaisesRegex(ValueError, "Pre-register the charger in Admin"):
            cli.resolve_qr_sources([1], None, None)
        with self.assertRaisesRegex(ValueError, "exactly one --qr-token"):
            cli.resolve_qr_sources([1, 2], ["only-one"], None)

    def test_smoke_defaults_cover_distinct_identity_and_serial(self) -> None:
        args = smoke_test.build_parser().parse_args([])
        self.assertNotEqual(args.ocpp_identity, args.serial_number)

    @patch("smoke_test.requests.post")
    def test_smoke_remote_control_uses_frozen_snake_case_contract(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"success": True}
        post.return_value = response
        headers = {"Authorization": "Bearer test"}

        smoke_test.call_remote_start(
            "http://localhost:9000", "CP-OCPP-001", "TAG-1", 2, headers
        )
        self.assertEqual(
            post.call_args.kwargs["json"],
            {
                "charge_point_id": "CP-OCPP-001",
                "id_tag": "TAG-1",
                "connector_id": 2,
            },
        )

        smoke_test.call_remote_stop(
            "http://localhost:9000", "CP-OCPP-001", 456, headers
        )
        self.assertEqual(
            post.call_args.kwargs["json"],
            {"charge_point_id": "CP-OCPP-001", "transaction_id": 456},
        )

    def test_smoke_http_failure_preserves_validation_body(self) -> None:
        response = Mock(status_code=422, text='{"detail":"field required"}')
        response.raise_for_status.side_effect = smoke_test.requests.HTTPError("422")

        with self.assertRaisesRegex(RuntimeError, "field required"):
            smoke_test.require_successful_response(response, "remote-start")

    def test_scenario_subcommands_are_available(self) -> None:
        parser = cli.build_parser()
        self.assertEqual(parser.parse_args(["scenario", "list"]).scenario_cmd, "list")
        self.assertEqual(
            parser.parse_args(["scenario", "validate", "scenarios/p0"]).scenario_cmd,
            "validate",
        )


class ScenarioCLIExitTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_scenario_exits_nonzero_and_still_writes_reports(self) -> None:
        content = """\
schema_version: "1.0"
scenario: {id: cli-failure}
environment: {}
actors: {}
steps:
  - id: fail
    actor: system
    action: assert
    with: {actual: 1, equals: 2}
reports: {}
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "failure.yml"
            scenario_path.write_text(content, encoding="utf-8")
            args = argparse.Namespace(path=str(scenario_path), report_dir=temp_dir)
            with self.assertRaisesRegex(SystemExit, "1"):
                await cli.scenario_run(args)
            self.assertEqual(len(list(Path(temp_dir).rglob("*.junit.xml"))), 1)


if __name__ == "__main__":
    unittest.main()
