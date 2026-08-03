"""Business-entry gates for retired chargers and archived sites."""

import base64
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.auth import create_access_token, get_password_hash
from app.core.ocpp_auth import hash_ocpp_secret, verify_ocpp_api_key
from app.database.models import AppUser, ChargingSession, Order, QrToken
from app.services.asset_lifecycle_service import AssetNotOperationalError
from app.services.qr_service import (
    InvalidQrTokenError,
    ensure_qr_token,
    resolve_qr_token,
)
from app.services.session_service import SessionService


def _basic_headers(identity: str, secret: str) -> dict[str, str]:
    value = base64.b64encode(f"{identity}:{secret}".encode()).decode()
    return {"authorization": f"Basic {value}"}


def _app_headers(user: AppUser) -> dict[str, str]:
    token = create_access_token({
        "user_id": str(user.id),
        "user_type": "app_user",
        "aud": "app",
    })
    return {"Authorization": f"Bearer {token}"}


def test_qr_resolution_fails_closed_for_lifecycle_and_revocation(
    db_session,
    sample_site,
    sample_charge_point,
):
    qr = QrToken(
        token="lifecycle-business-gate-token",
        operator_tenant_id=sample_charge_point.tenant_id,
        charge_point_id=sample_charge_point.id,
        connector_id=1,
    )
    db_session.add(qr)
    db_session.commit()

    assert resolve_qr_token(db_session, qr.token).id == qr.id

    sample_charge_point.is_active = False
    db_session.flush()
    with pytest.raises(AssetNotOperationalError) as retired:
        resolve_qr_token(db_session, qr.token)
    assert retired.value.code == "charger_not_operational"

    sample_charge_point.is_active = True
    sample_site.is_active = False
    db_session.flush()
    with pytest.raises(AssetNotOperationalError) as archived:
        resolve_qr_token(db_session, qr.token)
    assert archived.value.code == "site_not_operational"

    sample_site.is_active = True
    qr.revoked_at = datetime.now(timezone.utc)
    db_session.flush()
    with pytest.raises(InvalidQrTokenError) as invalid:
        resolve_qr_token(db_session, qr.token)
    assert invalid.value.code == "qr_token_invalid"

    old_token = qr.token
    rotated = ensure_qr_token(db_session, sample_charge_point.id, 1)
    assert rotated.id == qr.id
    assert rotated.token != old_token
    assert rotated.revoked_at is None
    with pytest.raises(InvalidQrTokenError):
        resolve_qr_token(db_session, old_token)
    assert resolve_qr_token(db_session, rotated.token).id == qr.id


def test_session_service_does_not_create_session_or_order_for_retired_charger(
    db_session,
    sample_charge_point,
    sample_evse,
):
    sample_charge_point.is_active = False
    sample_charge_point.commissioning_status = "suspended"
    db_session.commit()

    with pytest.raises(AssetNotOperationalError) as exc_info:
        SessionService.start_session(
            db=db_session,
            charge_point_id=sample_charge_point.ocpp_identity,
            evse_id=sample_evse.evse_id,
            transaction_id=99101,
            id_tag="BLOCKED-RETIRED",
        )

    assert exc_info.value.code == "charger_not_operational"
    assert db_session.query(ChargingSession).count() == 0
    assert db_session.query(Order).count() == 0


def test_ocpp_auth_requires_operational_asset_and_current_device_secret(
    db_session,
    sample_site,
    sample_charge_point,
):
    current_secret = "current-device-secret"
    sample_charge_point.ocpp_auth_secret_hash = hash_ocpp_secret(current_secret)
    db_session.commit()
    session_factory = sessionmaker(bind=db_session.get_bind())

    with patch("app.database.base.SuperSessionLocal", side_effect=session_factory):
        assert verify_ocpp_api_key(
            _basic_headers(sample_charge_point.ocpp_identity, current_secret),
            sample_charge_point.ocpp_identity,
        ) is True
        assert verify_ocpp_api_key(
            _basic_headers(sample_charge_point.ocpp_identity, "old-device-secret"),
            sample_charge_point.ocpp_identity,
        ) is False

        sample_charge_point.is_active = False
        db_session.commit()
        assert verify_ocpp_api_key(
            _basic_headers(sample_charge_point.ocpp_identity, current_secret),
            sample_charge_point.ocpp_identity,
        ) is False

        sample_charge_point.is_active = True
        sample_site.is_active = False
        db_session.commit()
        assert verify_ocpp_api_key(
            _basic_headers(sample_charge_point.ocpp_identity, current_secret),
            sample_charge_point.ocpp_identity,
        ) is False


@pytest.mark.parametrize(
    ("retire_charger", "archive_site", "expected_code"),
    [
        (True, False, "charger_not_operational"),
        (False, True, "site_not_operational"),
    ],
)
def test_app_scan_returns_stable_lifecycle_conflict(
    client,
    db_session,
    sample_site,
    sample_charge_point,
    sample_evse,
    retire_charger,
    archive_site,
    expected_code,
):
    user = AppUser(
        email=f"{expected_code}@example.test",
        password_hash=get_password_hash("test-password"),
        email_verified=True,
        balance=Decimal("100000.00"),
        status="active",
    )
    qr = QrToken(
        token=f"scan-{expected_code}-token",
        operator_tenant_id=sample_charge_point.tenant_id,
        charge_point_id=sample_charge_point.id,
        connector_id=sample_evse.evse_id,
    )
    sample_charge_point.is_active = not retire_charger
    sample_site.is_active = not archive_site
    db_session.add_all([user, qr])
    db_session.commit()

    response = client.get(
        f"/api/v1/app/charging/check?qr_token={qr.token}",
        headers=_app_headers(user),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == expected_code
