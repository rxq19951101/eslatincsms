from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock

from simulator.charge_point import SimChargePoint
from simulator.profiles import ChargePointProfile, MeteringProfile


def status_of(payload) -> str:
    return str(getattr(payload, "status", ""))


class RemoteCommandTests(unittest.IsolatedAsyncioTestCase):
    def make_charge_point(self) -> SimChargePoint:
        return SimChargePoint(
            ChargePointProfile(charge_point_id="CP-HANDLER-001"),
            [MeteringProfile(connector_id=1)],
            object(),
        )

    async def test_authorize_rejection_terminates_remote_start_flow(self) -> None:
        cp = self.make_charge_point()
        cp.send_status_notification = AsyncMock()
        cp.send_authorize = AsyncMock(return_value=False)
        cp.send_start_transaction = AsyncMock(return_value=123)

        response = await cp.on_remote_start("DENIED", connector_id=1)
        await asyncio.sleep(0)

        self.assertEqual(status_of(response), "Accepted")
        cp.send_start_transaction.assert_not_awaited()
        self.assertIsNone(cp.state.connectors[1].transaction_id)
        self.assertEqual(cp.received_commands[-1]["action"], "RemoteStartTransaction")
        self.assertEqual(cp.received_commands[-1]["status"], "Accepted")

    async def test_concurrent_remote_start_accepts_only_one(self) -> None:
        cp = self.make_charge_point()
        gate = asyncio.Event()

        async def authorize(_id_tag):
            await gate.wait()
            return True

        cp.send_status_notification = AsyncMock()
        cp.send_authorize = AsyncMock(side_effect=authorize)
        cp.send_start_transaction = AsyncMock(return_value=123)
        cp._meter_values_loop = AsyncMock()

        first = await cp.on_remote_start("TAG", connector_id=1)
        second = await cp.on_remote_start("TAG", connector_id=1)
        self.assertEqual(status_of(first), "Accepted")
        self.assertEqual(status_of(second), "Rejected")
        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        cp.send_start_transaction.assert_awaited_once()

    async def test_unknown_remote_stop_is_rejected(self) -> None:
        cp = self.make_charge_point()
        response = await cp.on_remote_stop(999999)
        self.assertEqual(status_of(response), "Rejected")

    async def test_minimum_configuration_reset_and_unlock_handlers(self) -> None:
        cp = self.make_charge_point()
        changed = await cp.on_change_configuration("HeartbeatInterval", "10")
        configuration = await cp.on_get_configuration(["HeartbeatInterval", "Missing"])
        unlocked = await cp.on_unlock_connector(1)
        reset = await cp.on_reset("Soft")

        self.assertEqual(status_of(changed), "Accepted")
        self.assertEqual(status_of(unlocked), "Unlocked")
        self.assertEqual(status_of(reset), "Accepted")
        self.assertEqual(configuration.configuration_key[0]["value"], "10")
        self.assertEqual(configuration.unknown_key, ["Missing"])
        self.assertEqual(
            [item["action"] for item in cp.received_commands[-4:]],
            ["ChangeConfiguration", "GetConfiguration", "UnlockConnector", "Reset"],
        )


if __name__ == "__main__":
    unittest.main()
