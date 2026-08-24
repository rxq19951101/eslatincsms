"""Contract-level replacement for the removed unauthenticated simulated user flow.

The executable App/OCPP happy path lives in ``test_user_charging_flow.py`` and
``test_sim_e2e_p0.py``. These checks keep the former file's API surface covered
without bypassing authentication, tenant ownership, UUID boundaries, or strict
snake_case validation.
"""

import uuid
from datetime import datetime, timezone

from app.database.models import ChargingSession, Device


def test_device_registration_requires_admin_auth(client):
    client.headers.pop("Authorization", None)
    response = client.post(
        "/api/v1/devices",
        json={"serial_number": "888888888888888", "device_type_code": "test"},
    )
    assert response.status_code == 401
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_device_registration_is_tenant_scoped(admin_client, db_session, sample_tenant):
    response = admin_client.post(
        "/api/v1/devices",
        json={"serial_number": "888888888888888", "device_type_code": "test"},
    )
    assert response.status_code == 201
    device = db_session.query(Device).filter_by(serial_number="888888888888888").one()
    assert device.tenant_id == sample_tenant.id
    assert response.json()["serial_number"] == device.serial_number


def test_charger_lookup_exposes_uuid_and_ocpp_identity(admin_client, sample_charge_point):
    response = admin_client.get(f"/api/v1/chargers/{sample_charge_point.id}")
    assert response.status_code == 200
    assert uuid.UUID(response.json()["id"]) == sample_charge_point.id
    assert response.json()["ocpp_identity"] == sample_charge_point.ocpp_identity


def test_remote_start_rejects_legacy_camel_case(admin_client):
    response = admin_client.post(
        "/api/v1/ocpp/remote-start-transaction",
        json={"chargePointId": "CP-LEGACY", "idTag": "TAG", "connectorId": 1},
    )
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert all("path" in item for item in details)


def test_session_uses_tenant_uuid_and_integer_ocpp_transaction(
    db_session, sample_charge_point, sample_evse
):
    session = ChargingSession(
        tenant_id=sample_charge_point.tenant_id,
        charge_point_id=sample_charge_point.id,
        evse_id=sample_evse.id,
        transaction_id=12345,
        id_tag="TEST_USER_001",
        start_time=datetime.now(timezone.utc),
        status="ongoing",
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    assert isinstance(session.id, uuid.UUID)
    assert session.tenant_id == sample_charge_point.tenant_id
    assert session.transaction_id == 12345


def test_order_list_requires_admin_auth(client):
    client.headers.pop("Authorization", None)
    response = client.get("/api/v1/orders")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"
