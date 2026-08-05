import base64
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

from app.core.ocpp_auth import (
    _presented_secret,
    hash_ocpp_secret,
    is_secure_ocpp_websocket,
    verify_charge_point_pre_registered,
    verify_ocpp_api_key,
)
from app.database.models import ChargingSession, MeterValue, OCPPMessageEvent


def _session_with_charge_point(charge_point):
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = charge_point
    return session


def _basic_auth(identity, secret):
    encoded = base64.b64encode(f"{identity}:{secret}".encode("utf-8")).decode("ascii")
    return {"authorization": f"Basic {encoded}"}


def test_pre_registration_returns_real_boolean():
    session = _session_with_charge_point(("id",))
    with patch("app.database.base.SuperSessionLocal", return_value=session):
        assert verify_charge_point_pre_registered("CP-SECURE-001") is True


def test_per_device_secret_is_bound_to_identity(monkeypatch):
    secret = "high-entropy-device-secret"
    charge_point = MagicMock(
        ocpp_auth_secret_hash=hash_ocpp_secret(secret),
        is_active=True,
    )
    session = _session_with_charge_point(charge_point)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with patch("app.database.base.SuperSessionLocal", return_value=session):
        assert verify_ocpp_api_key(_basic_auth("CP-SECURE-001", secret), "CP-SECURE-001")
        assert not verify_ocpp_api_key(_basic_auth("CP-SECURE-001", secret), "CP-OTHER-001")


def test_basic_auth_uses_complete_colon_identity_and_preserves_colons_in_secret(monkeypatch):
    identity = "CO.BOGOTA:SIM-AC-7KW-01"
    secret = "device:secret:with:colons"
    charge_point = MagicMock(
        ocpp_auth_secret_hash=hash_ocpp_secret(secret),
        is_active=True,
    )
    session = _session_with_charge_point(charge_point)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with patch("app.database.base.SuperSessionLocal", return_value=session):
        assert verify_ocpp_api_key(_basic_auth(identity, secret), identity)
        assert not verify_ocpp_api_key(_basic_auth("CO.BOGOTA", secret), identity)
        assert not verify_ocpp_api_key(_basic_auth(identity, "wrong-secret"), identity)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"authorization": "Basic"},
        {"authorization": "Basic !!!not-base64!!!"},
        {"authorization": "Basic " + base64.b64encode(b"missing-separator").decode("ascii")},
        {"authorization": "Basic " + base64.b64encode(b"CP-SECURE-001:\xff").decode("ascii")},
    ],
)
def test_malformed_basic_auth_fails_closed(headers):
    assert _presented_secret(headers, "CP-SECURE-001") is None


def test_x_api_key_and_bearer_secret_compatibility():
    assert _presented_secret({"X-API-Key": " device-secret "}, "CP-SECURE-001") == "device-secret"
    assert _presented_secret(
        {"Authorization": "Bearer device-secret"}, "CP-SECURE-001"
    ) == "device-secret"


def test_colon_identity_completes_websocket_handshake(
    client, db_session, sample_charge_point
):
    identity = "CO.BOGOTA:SIM-AC-7KW-01"
    secret = "device:secret"
    sample_charge_point.ocpp_identity = identity
    sample_charge_point.ocpp_auth_secret_hash = hash_ocpp_secret(secret)
    db_session.commit()

    with client.websocket_connect(
        f"/ocpp?id={identity}",
        headers=_basic_auth(identity, secret),
        subprotocols=["ocpp1.6"],
    ) as websocket:
        assert websocket.accepted_subprotocol == "ocpp1.6"


def test_production_proxy_wss_detection():
    assert is_secure_ocpp_websocket({}, "wss")
    assert is_secure_ocpp_websocket({"x-forwarded-proto": "https"}, "ws")
    assert not is_secure_ocpp_websocket({}, "ws")


def test_acceptance_report_requires_complete_protocol_evidence(
    db_session, sample_charge_point, sample_evse, sample_evse_status
):
    from app.api.v1.chargers import _build_acceptance_report

    sample_charge_point.ocpp_auth_secret_hash = hash_ocpp_secret("device-secret")
    sample_evse.physical_reference = "A-01"
    sample_evse.max_power_kw = 7.0
    for index, action in enumerate(
        [
            "BootNotification",
            "BootNotification",
            "Heartbeat",
            "StartTransaction",
            "MeterValues",
            "StopTransaction",
        ]
    ):
        db_session.add(OCPPMessageEvent(
            tenant_id=sample_charge_point.tenant_id,
            charge_point_id=sample_charge_point.id,
            action=action,
            unique_id=f"acceptance-{index}",
            message_key=f"acceptance-{index}",
            payload={},
            response_payload={},
            response_message_type=3,
            processing_status="completed",
            outcome="processed",
            processed_at=datetime.now(timezone.utc),
        ))
    sample_evse_status.last_seen = datetime.now(timezone.utc)
    session = ChargingSession(
        tenant_id=sample_charge_point.tenant_id,
        charge_point_id=sample_charge_point.id,
        evse_id=sample_evse.id,
        transaction_id=88001,
        id_tag="ACCEPTANCE",
        start_time=datetime.now(timezone.utc),
        status="ongoing",
    )
    db_session.add(session)
    db_session.flush()
    db_session.add(MeterValue(
        tenant_id=sample_charge_point.tenant_id,
        session_id=session.id,
        idempotency_key="acceptance-meter",
        timestamp=datetime.now(timezone.utc),
        value=100,
    ))
    db_session.commit()

    with patch(
        "app.api.v1.charger_management.check_charger_connection",
        return_value=True,
    ):
        report = _build_acceptance_report(db_session, sample_charge_point)

    assert report["passed"] is True
    assert report["checks"]["disconnect_recovery"] is True
