from __future__ import annotations

import re
import unittest
from pathlib import Path

from scenario.loader import discover_scenarios, load_scenario


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent


class SecretHygieneTests(unittest.TestCase):
    def test_plaintext_account_file_removed_and_example_is_non_secret(self) -> None:
        self.assertFalse((ROOT / "test_accounts.yml").exists())
        example = (ROOT / "test_accounts.yml.example").read_text(encoding="utf-8")
        self.assertNotRegex(example, r"(?i)(password|secret|token)\s*:\s*\S+")

    def test_scenario_secret_fields_are_schema_validated_env_references(self) -> None:
        paths = discover_scenarios([ROOT / "scenarios"])
        self.assertTrue(paths)
        for path in paths:
            load_scenario(path)

    def test_no_real_payment_domain_or_high_risk_credential_marker(self) -> None:
        forbidden = [
            "mercado" + "pago.com",
            "api." + "stripe.com",
            "TEST" + "USER",
            "APP_" + "USR-",
            "sk_" + "live_",
            "BEGIN " + "PRIVATE KEY",
        ]
        files = [path for path in ROOT.rglob("*") if path.is_file() and "reports" not in path.parts]
        for path in files:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for marker in forbidden:
                self.assertNotIn(marker, content, f"forbidden credential marker in {path}")

    def test_no_complete_card_number_literal(self) -> None:
        card_pattern = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
        for path in ROOT.rglob("*.yml"):
            self.assertIsNone(card_pattern.search(path.read_text(encoding="utf-8")), str(path))

    def test_compose_requires_root_env_secrets_and_profiles_simulators(self) -> None:
        compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("POSTGRES_PASSWORD=${POSTGRES_PASSWORD}", compose)
        self.assertIn("SECRET_KEY=${SECRET_KEY}", compose)
        self.assertIn("ENCRYPTION_KEY=${ENCRYPTION_KEY}", compose)
        self.assertNotIn("POSTGRES_PASSWORD=ocpp_password", compose)
        self.assertNotRegex(compose, r"(?:SECRET_KEY|ENCRYPTION_KEY)=\$\{[^}]+:-[^}]+\}")
        self.assertRegex(compose, r"charger-sim:\n\s+profiles: \[\"simulator\"\]")
        self.assertRegex(compose, r"charger-scenario:\n\s+profiles: \[\"e2e\"\]")


if __name__ == "__main__":
    unittest.main()
