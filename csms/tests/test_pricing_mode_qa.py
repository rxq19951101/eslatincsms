"""Direct QA coverage for PRC-MODE-001 pricing gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.api.v1.chargers import ChargerPricingUpdateRequest
from app.api.v1.sites import SitePricingUpdateRequest
from app.database.models import AuditLog, QrToken, Tariff
from app.services.pricing_service import PricingMode, PricingService


def _metadata(mode: PricingMode, *, reason: str | None = None):
    return PricingService.metadata(mode, free_reason=reason)


def _tariff(db_session, charge_point, *, mode: PricingMode, source: str, valid_until=None):
    tariff = Tariff(
        tenant_id=charge_point.tenant_id,
        site_id=charge_point.site_id,
        charge_point_id=charge_point.id if source == "charger" else None,
        name=f"QA {source} {mode.value}",
        base_price_per_kwh=Decimal("2700.00") if mode == PricingMode.PAID else Decimal("0.00"),
        service_fee=Decimal("0.00"),
        time_based_rules=_metadata(
            mode,
            reason="QA promotion" if mode == PricingMode.FREE else None,
        ),
        valid_from=datetime.now(timezone.utc) - timedelta(minutes=1),
        valid_until=valid_until,
        is_active=True,
    )
    db_session.add(tariff)
    db_session.commit()
    return tariff


def _app_headers(user_id):
    from app.core.auth import create_access_token

    token = create_access_token({
        "user_id": str(user_id),
        "user_type": "app_user",
        "aud": "app",
    })
    return {"Authorization": f"Bearer {token}"}


def test_free_pricing_requires_reason_and_future_timezone_aware_expiry():
    with pytest.raises(ValidationError):
        SitePricingUpdateRequest(
            pricing_mode="free",
            free_reason="ab",
            valid_until=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    with pytest.raises(ValidationError):
        ChargerPricingUpdateRequest(
            pricing_mode="free",
            free_reason="QA promotion",
            valid_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    with pytest.raises(ValidationError):
        ChargerPricingUpdateRequest(
            pricing_mode="free",
            free_reason="QA promotion",
            valid_until=datetime.now(),
        )


def test_expired_free_pricing_falls_back_to_unavailable(db_session, sample_charge_point):
    _tariff(
        db_session,
        sample_charge_point,
        mode=PricingMode.FREE,
        source="site",
        valid_until=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    resolved = PricingService.resolve(
        db_session,
        sample_charge_point.tenant_id,
        sample_charge_point.id,
    )

    assert resolved.pricing_mode is PricingMode.UNAVAILABLE
    assert resolved.is_available is False


def test_commission_rejects_unavailable_tariff_with_stable_error(
    admin_client, sample_charge_point
):
    sample_charge_point.commissioning_status = "ready"

    response = admin_client.post(f"/api/v1/chargers/{sample_charge_point.id}/commission")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TARIFF_NOT_CONFIGURED"


def test_scan_and_start_reject_unavailable_without_remote_start(
    client, db_session, sample_charge_point, sample_evse
):
    from app.core.auth import get_password_hash
    from app.database.models import AppUser

    user = AppUser(
        email="pricing-gate@example.test",
        password_hash=get_password_hash("test-password"),
        email_verified=True,
        balance=Decimal("0.00"),
        status="active",
    )
    qr = QrToken(
        token="pricing-gate-qr-token-001",
        operator_tenant_id=sample_charge_point.tenant_id,
        charge_point_id=sample_charge_point.id,
        connector_id=1,
    )
    sample_charge_point.commissioning_status = "commissioned"
    db_session.add_all([user, qr])
    db_session.commit()

    headers = _app_headers(user.id)
    check = client.get(
        "/api/v1/app/charging/check",
        params={"qr_token": qr.token},
        headers=headers,
    )
    assert check.status_code == 409
    assert check.json()["error"]["code"] == "TARIFF_NOT_CONFIGURED"

    with patch(
        "app.api.v1.app.charging.send_remote_start",
        new_callable=AsyncMock,
    ) as sender:
        start = client.post(
            "/api/v1/app/charging/start",
            json={"qr_token": qr.token, "settlement_method": "wallet"},
            headers=headers,
        )
    assert start.status_code == 409
    assert start.json()["error"]["code"] == "TARIFF_NOT_CONFIGURED"
    sender.assert_not_awaited()


def test_pricing_update_audit_is_tenant_scoped_and_safe(admin_client, db_session, sample_site):
    response = admin_client.put(
        f"/api/v1/sites/{sample_site.id}/pricing",
        json={
            "pricing_mode": "free",
            "free_reason": "QA promotion",
            "valid_until": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )

    assert response.status_code == 200
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "tariff.site.update")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.tenant_id == sample_site.tenant_id
    assert audit.resource_id == str(sample_site.id)
    assert audit.before_data["pricing_mode"] == "unavailable"
    assert audit.after_data["pricing_mode"] == "free"
    assert audit.after_data["free_reason"] == "QA promotion"

    forbidden = {"password", "token", "secret", "private_key", "card_number", "cvv"}

    def assert_safe(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value.keys())
            for child in value.values():
                assert_safe(child)
        elif isinstance(value, list):
            for child in value:
                assert_safe(child)

    assert_safe(audit.before_data)
    assert_safe(audit.after_data)
    assert_safe(audit.audit_metadata)


@pytest.mark.parametrize("site_mode, charger_mode, expected", [
    (PricingMode.PAID, None, PricingMode.PAID),
    (PricingMode.UNAVAILABLE, PricingMode.PAID, PricingMode.PAID),
    (PricingMode.UNAVAILABLE, PricingMode.FREE, PricingMode.FREE),
    (PricingMode.PAID, PricingMode.UNAVAILABLE, PricingMode.UNAVAILABLE),
])
def test_site_and_charger_pricing_priority_matrix(
    db_session, sample_charge_point, site_mode, charger_mode, expected
):
    _tariff(db_session, sample_charge_point, mode=site_mode, source="site")
    if charger_mode is not None:
        _tariff(db_session, sample_charge_point, mode=charger_mode, source="charger")

    resolved = PricingService.resolve(
        db_session,
        sample_charge_point.tenant_id,
        sample_charge_point.id,
    )

    assert resolved.pricing_mode is expected
