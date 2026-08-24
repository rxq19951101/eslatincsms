from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

from ocpp.v16.enums import AuthorizationStatus

from simulator.charge_point import SimChargePoint
from simulator.profiles import ChargePointProfile, MeteringProfile


@dataclass
class IdTagInfo:
    status: object


@dataclass
class AuthorizeResponse:
    id_tag_info: IdTagInfo


class AuthorizeResponseTests(unittest.IsolatedAsyncioTestCase):
    def make_charge_point(self) -> SimChargePoint:
        charge_point = SimChargePoint(
            ChargePointProfile(charge_point_id="CP-AUTH-001"),
            [MeteringProfile(connector_id=1)],
            object(),
        )
        charge_point.call = AsyncMock()
        return charge_point

    async def test_accepted_enum_and_string_response_variants_are_authorized(self) -> None:
        responses = (
            {"idTagInfo": {"status": "Accepted"}},
            {"id_tag_info": {"status": AuthorizationStatus.accepted}},
            AuthorizeResponse(IdTagInfo(status=AuthorizationStatus.accepted)),
            SimpleNamespace(idTagInfo={"status": "accepted"}),
        )

        for response in responses:
            with self.subTest(response=response):
                charge_point = self.make_charge_point()
                charge_point.call.return_value = response

                self.assertTrue(await charge_point.send_authorize("TAG-001"))

    async def test_non_accepted_status_is_not_authorized(self) -> None:
        charge_point = self.make_charge_point()
        charge_point.call.return_value = {
            "idTagInfo": {"status": AuthorizationStatus.blocked}
        }

        self.assertFalse(await charge_point.send_authorize("TAG-001"))


if __name__ == "__main__":
    unittest.main()
