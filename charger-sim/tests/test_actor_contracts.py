from __future__ import annotations

import unittest
import uuid

from actors.app_user import AppUserActor
from actors.admin import AdminActor


class AppActorContractTests(unittest.TestCase):
    def test_generic_api_query_is_get_by_default(self) -> None:
        app = AppUserActor("app", {}, "run")
        admin = AdminActor("admin", {}, "run")
        self.assertEqual(
            app._build_request("query", {"path": "/api/v1/app/transactions"}),
            ("GET", "/api/v1/app/transactions", None, None),
        )
        self.assertEqual(
            admin._build_request("query", {"path": "/api/v1/transactions", "query": {"status": "ongoing"}}),
            ("GET", "/api/v1/transactions", None, {"status": "ongoing"}),
        )
    def test_active_session_uses_uuid_resources_and_integer_transaction(self) -> None:
        body = {
            "id": str(uuid.uuid4()),
            "charge_point_id": str(uuid.uuid4()),
            "evse_id": str(uuid.uuid4()),
            "transaction_id": 42,
        }
        AppUserActor._validate_resource_ids("get_active", body)

    def test_active_session_rejects_transaction_id_as_resource_uuid(self) -> None:
        body = {"id": 42, "transaction_id": str(uuid.uuid4())}
        with self.assertRaisesRegex(ValueError, "UUID string"):
            AppUserActor._validate_resource_ids("get_active", body)


if __name__ == "__main__":
    unittest.main()
