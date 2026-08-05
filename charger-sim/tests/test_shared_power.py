from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from simulator.charge_point import SimChargePoint
from simulator.metering import allocate_shared_power_kw
from simulator.profiles import ChargePointProfile, MeteringProfile


class SharedPowerAllocationTests(unittest.TestCase):
    def test_one_active_connector_receives_full_available_power(self) -> None:
        allocation = allocate_shared_power_kw({1: 60.0, 2: 60.0}, [1], 60.0)
        self.assertEqual(allocation, {1: 60.0, 2: 0.0})

    def test_two_equal_connectors_split_limit_equally(self) -> None:
        allocation = allocate_shared_power_kw({1: 60.0, 2: 60.0}, [1, 2], 60.0)
        self.assertEqual(allocation, {1: 30.0, 2: 30.0})

    def test_unused_share_is_redistributed_to_other_connector(self) -> None:
        allocation = allocate_shared_power_kw({1: 20.0, 2: 60.0}, [1, 2], 60.0)
        self.assertEqual(allocation, {1: 20.0, 2: 40.0})

    def test_requests_below_limit_are_not_increased(self) -> None:
        allocation = allocate_shared_power_kw({1: 10.0, 2: 20.0}, [1, 2], 60.0)
        self.assertEqual(allocation, {1: 10.0, 2: 20.0})

    def test_profile_rejects_invalid_shared_limit(self) -> None:
        for invalid_limit in (0.0, -1.0, float("inf"), float("nan")):
            with self.subTest(invalid_limit=invalid_limit):
                with self.assertRaisesRegex(ValueError, "shared_power_limit_kw"):
                    ChargePointProfile(
                        charge_point_id="CP-SHARED-INVALID",
                        shared_power_limit_kw=invalid_limit,
                    )


class SharedPowerMeterValuesTests(unittest.IsolatedAsyncioTestCase):
    async def test_meter_values_and_energy_use_allocated_power(self) -> None:
        charge_point = SimChargePoint(
            ChargePointProfile(
                charge_point_id="CP-SHARED-001",
                shared_power_limit_kw=60.0,
            ),
            [
                MeteringProfile(
                    connector_id=1,
                    power_kw=60.0,
                    meter_values_interval_sec=60,
                ),
                MeteringProfile(
                    connector_id=2,
                    power_kw=60.0,
                    meter_values_interval_sec=60,
                ),
            ],
            AsyncMock(),
        )
        charge_point.call = AsyncMock(return_value=None)
        charge_point.state.connectors[1].transaction_id = 101
        charge_point.state.connectors[2].transaction_id = 102

        await charge_point.send_meter_values(1)

        first_payload = charge_point.call.await_args.args[0]
        sampled_values = first_payload.meter_value[0]["sampledValue"]
        power = next(
            value for value in sampled_values if value["measurand"] == "Power.Active.Import"
        )
        self.assertEqual(power["value"], "30000")
        self.assertEqual(charge_point.state.connectors[1].meter.meter_wh, 500)

        charge_point.state.connectors[2].transaction_id = None
        await charge_point.send_meter_values(1)

        second_payload = charge_point.call.await_args.args[0]
        sampled_values = second_payload.meter_value[0]["sampledValue"]
        power = next(
            value for value in sampled_values if value["measurand"] == "Power.Active.Import"
        )
        self.assertEqual(power["value"], "60000")
        self.assertEqual(charge_point.state.connectors[1].meter.meter_wh, 1500)

    async def test_missing_shared_limit_preserves_per_connector_power(self) -> None:
        charge_point = SimChargePoint(
            ChargePointProfile(charge_point_id="CP-INDEPENDENT-001"),
            [MeteringProfile(connector_id=1, power_kw=60.0)],
            AsyncMock(),
        )
        charge_point.state.connectors[1].transaction_id = 101

        self.assertEqual(charge_point.allocated_power_kw(1), 60.0)


if __name__ == "__main__":
    unittest.main()
