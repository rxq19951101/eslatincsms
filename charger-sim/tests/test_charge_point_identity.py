from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

from ocpp.v16.enums import RegistrationStatus

from simulator.charge_point import SimChargePoint, build_websocket_url
from simulator.profiles import ChargePointProfile, MeteringProfile


class ChargePointIdentityTests(unittest.TestCase):
    def test_websocket_identity_and_boot_serial_can_differ(self) -> None:
        profile = ChargePointProfile(
            charge_point_id="CP:BOGOTA-001",
            serial_number="SERIAL-HARDWARE-9001",
        )

        self.assertEqual(profile.ocpp_identity, "CP:BOGOTA-001")
        self.assertEqual(profile.boot_serial_number, "SERIAL-HARDWARE-9001")

        url = build_websocket_url("ws://localhost:9000/ocpp?tenant=test", profile.ocpp_identity)
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["id"], ["CP:BOGOTA-001"])
        self.assertEqual(query["tenant"], ["test"])

    def test_boot_serial_defaults_to_websocket_identity(self) -> None:
        profile = ChargePointProfile(charge_point_id="CP-DEFAULT-001")
        self.assertEqual(profile.boot_serial_number, "CP-DEFAULT-001")

    def test_invalid_ocpp_identity_is_rejected_before_connect(self) -> None:
        with self.assertRaisesRegex(ValueError, "OCPP identity"):
            ChargePointProfile(charge_point_id="invalid identity with spaces")


class BootNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_boot_notification_uses_independent_serial_number(self) -> None:
        profile = ChargePointProfile(
            charge_point_id="CP-WS-001",
            serial_number="SERIAL-BOOT-777",
        )
        charge_point = SimChargePoint(
            profile=profile,
            meterings=[MeteringProfile(connector_id=1)],
            ws=object(),
        )
        charge_point.call = AsyncMock(
            return_value=SimpleNamespace(status=RegistrationStatus.accepted)
        )

        await charge_point.send_boot_notification()

        payload = charge_point.call.await_args.args[0]
        self.assertEqual(charge_point.id, "CP-WS-001")
        self.assertEqual(payload.charge_point_serial_number, "SERIAL-BOOT-777")


if __name__ == "__main__":
    unittest.main()
