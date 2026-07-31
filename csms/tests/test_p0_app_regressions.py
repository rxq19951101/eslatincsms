"""Focused regressions for SIM-E2E-001 App API P0 failures."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import asyncio
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
import pytest

from app.api.v1.app.charging import get_current_app_user as get_charging_app_user
from app.api.v1.app.wallet import get_current_app_user as get_wallet_app_user
from app.core.auth import create_access_token, get_password_hash
from app.services.billing_service import BillingService
from app.database.models import (
    AppUser,
    AppWalletTransaction,
    ChargingSession,
    Invoice,
    PaymentOrder,
    PricingSnapshot,
    QrToken,
    Tariff,
)


def _create_app_user(db_session, *, email: str, balance: Decimal) -> AppUser:
    user = AppUser(
        id=uuid.uuid4(),
        email=email,
        password_hash=get_password_hash("test-password"),
        email_verified=True,
        balance=balance,
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _app_headers(user: AppUser) -> dict[str, str]:
    token = create_access_token({
        "user_id": str(user.id),
        "user_type": "app_user",
        "aud": "app",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
@pytest.mark.parametrize("dependency", [get_charging_app_user, get_wallet_app_user])
async def test_app_user_dependencies_reject_non_uuid_token_subject(dependency, db_session):
    with pytest.raises(HTTPException) as exc_info:
        await dependency({"user_id": "not-a-uuid"}, db_session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


def test_start_charging_uses_module_charge_point_model(
    client, db_session, sample_tenant, sample_charge_point, sample_evse
):
    user = _create_app_user(
        db_session,
        email="p0-start@example.test",
        balance=Decimal("100000.00"),
    )
    qr = QrToken(
        token="p0-start-qr-token-001",
        operator_tenant_id=sample_tenant.id,
        charge_point_id=sample_charge_point.id,
        connector_id=sample_evse.evse_id,
    )
    db_session.add(qr)
    db_session.commit()

    with patch(
        "app.api.v1.app.charging.send_remote_start",
        new=AsyncMock(return_value={"success": True, "status": "Accepted"}),
    ) as sender:
        response = client.post(
            "/api/v1/app/charging/start",
            headers=_app_headers(user),
            json={"qr_token": qr.token},
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["status"] == "accepted"
    assert response.json()["ocpp_identity"] == sample_charge_point.ocpp_identity
    sender.assert_awaited_once_with(
        sample_charge_point.ocpp_identity,
        f"APP{str(user.id).replace('-', '')[:17]}",
        sample_evse.evse_id,
    )


def test_start_charging_returns_existing_session_without_ocpp(
    client, db_session, sample_tenant, sample_charge_point, sample_evse
):
    user = _create_app_user(
        db_session,
        email="p0-active-start@example.test",
        balance=Decimal("0.00"),
    )
    qr = QrToken(
        token="p0-active-start-qr-001",
        operator_tenant_id=sample_tenant.id,
        charge_point_id=sample_charge_point.id,
        connector_id=sample_evse.evse_id,
    )
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=88001,
        id_tag="ACTIVE-APP-USER",
        user_id=str(user.id),
        app_user_id=user.id,
        start_time=datetime.now(timezone.utc),
        status="ongoing",
    )
    db_session.add_all([qr, session])
    db_session.commit()

    with patch(
        "app.api.v1.app.charging.send_remote_start", new=AsyncMock()
    ) as sender:
        response = client.post(
            "/api/v1/app/charging/start",
            headers=_app_headers(user),
            json={"qr_token": qr.token},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "already_active"
    assert body["ocpp_identity"] == sample_charge_point.ocpp_identity
    assert body["session"]["session_id"] == str(session.id)
    assert body["session"]["connector_id"] == sample_evse.evse_id
    sender.assert_not_awaited()


def test_active_session_recovers_without_qr_and_enforces_owner(
    client, db_session, sample_tenant, sample_charge_point, sample_evse
):
    owner = _create_app_user(
        db_session,
        email="p0-active-owner@example.test",
        balance=Decimal("1000.00"),
    )
    intruder = _create_app_user(
        db_session,
        email="p0-active-intruder@example.test",
        balance=Decimal("1000.00"),
    )
    qr = QrToken(
        token="p0-active-recovery-qr-001",
        operator_tenant_id=sample_tenant.id,
        charge_point_id=sample_charge_point.id,
        connector_id=sample_evse.evse_id,
    )
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=88002,
        id_tag=f"APP{str(owner.id).replace('-', '')[:17]}",
        user_id=str(owner.id),
        app_user_id=owner.id,
        start_time=datetime.now(timezone.utc),
        status="ongoing",
    )
    db_session.add_all([qr, session])
    db_session.commit()

    recovered = client.get(
        "/api/v1/app/charging/active",
        headers=_app_headers(owner),
    )
    compatible = client.get(
        f"/api/v1/app/charging/active?qr_token={qr.token}",
        headers=_app_headers(owner),
    )
    forbidden_without_qr = client.get(
        "/api/v1/app/charging/active",
        headers=_app_headers(intruder),
    )
    forbidden_with_qr = client.get(
        f"/api/v1/app/charging/active?qr_token={qr.token}",
        headers=_app_headers(intruder),
    )

    assert recovered.status_code == 200
    assert compatible.status_code == 200
    assert recovered.json()["id"] == str(session.id)
    assert recovered.json()["ocpp_identity"] == sample_charge_point.ocpp_identity
    assert recovered.json()["connector_id"] == sample_evse.evse_id
    assert compatible.json()["id"] == str(session.id)
    assert forbidden_without_qr.status_code == 404
    assert forbidden_with_qr.status_code == 404


def test_stop_charging_by_owned_session_id_sends_derived_ocpp_command(
    client, db_session, sample_tenant, sample_charge_point, sample_evse
):
    owner = _create_app_user(
        db_session,
        email="p0-stop-session-owner@example.test",
        balance=Decimal("1000.00"),
    )
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=88003,
        id_tag=f"APP{str(owner.id).replace('-', '')[:17]}",
        user_id=str(owner.id),
        app_user_id=owner.id,
        start_time=datetime.now(timezone.utc),
        status="ongoing",
    )
    db_session.add(session)
    db_session.commit()

    with patch(
        "app.api.v1.app.charging.send_remote_stop",
        new=AsyncMock(return_value={"success": True, "message": "accepted"}),
    ) as sender:
        response = client.post(
            "/api/v1/app/charging/stop",
            headers=_app_headers(owner),
            json={"session_id": str(session.id)},
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    sender.assert_awaited_once_with(sample_charge_point.ocpp_identity, 88003)


def test_stop_charging_rejects_other_users_session_without_ocpp(
    client, db_session, sample_tenant, sample_charge_point, sample_evse
):
    owner = _create_app_user(
        db_session,
        email="p0-stop-other-owner@example.test",
        balance=Decimal("1000.00"),
    )
    other_user = _create_app_user(
        db_session,
        email="p0-stop-other-user@example.test",
        balance=Decimal("1000.00"),
    )
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=88004,
        id_tag=f"APP{str(owner.id).replace('-', '')[:17]}",
        user_id=str(owner.id),
        app_user_id=owner.id,
        start_time=datetime.now(timezone.utc),
        status="ongoing",
    )
    db_session.add(session)
    db_session.commit()

    with patch(
        "app.api.v1.app.charging.send_remote_stop", new=AsyncMock()
    ) as sender:
        response = client.post(
            "/api/v1/app/charging/stop",
            headers=_app_headers(other_user),
            json={"session_id": str(session.id)},
        )

    assert response.status_code == 404
    sender.assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"qr_token": "p0-stop-validation-qr", "session_id": str(uuid.uuid4())},
    ],
)
def test_stop_charging_requires_exactly_one_reference_without_ocpp(
    client, db_session, payload
):
    user = _create_app_user(
        db_session,
        email=f"p0-stop-validation-{len(payload)}@example.test",
        balance=Decimal("1000.00"),
    )

    with patch(
        "app.api.v1.app.charging.send_remote_stop", new=AsyncMock()
    ) as sender:
        response = client.post(
            "/api/v1/app/charging/stop",
            headers=_app_headers(user),
            json=payload,
        )

    assert response.status_code == 422
    sender.assert_not_awaited()


@pytest.mark.parametrize(
    ("side_effect", "return_value", "expected_status", "expected_code"),
    [
        (
            None,
            {
                "success": False,
                "message": "rejected",
                "details": {"device_status": "Rejected"},
            },
            409,
            "REMOTE_START_REJECTED",
        ),
        (
            HTTPException(status_code=504, detail="RemoteStartTransaction timed out"),
            None,
            504,
            "HTTP_ERROR",
        ),
    ],
)
def test_start_charging_distinguishes_rejection_and_timeout(
    client,
    db_session,
    sample_tenant,
    sample_charge_point,
    sample_evse,
    side_effect,
    return_value,
    expected_status,
    expected_code,
):
    user = _create_app_user(
        db_session,
        email=f"p0-start-error-{expected_status}@example.test",
        balance=Decimal("100000.00"),
    )
    qr = QrToken(
        token=f"p0-start-error-qr-{expected_status}",
        operator_tenant_id=sample_tenant.id,
        charge_point_id=sample_charge_point.id,
        connector_id=sample_evse.evse_id,
    )
    db_session.add(qr)
    db_session.commit()

    mock = AsyncMock(side_effect=side_effect, return_value=return_value)
    with patch("app.api.v1.app.charging.send_remote_start", new=mock):
        response = client.post(
            "/api/v1/app/charging/start",
            headers=_app_headers(user),
            json={"qr_token": qr.token},
        )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code


@pytest.mark.asyncio
async def test_identical_concurrent_app_starts_share_one_ocpp_command():
    from app.api.v1.app import charging
    from app.api.v1.ocpp_control import RemoteResponse

    charging._start_attempts.clear()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def accepted(*args, **kwargs):
        entered.set()
        await release.wait()
        return RemoteResponse(
            success=True,
            message="accepted",
            details={"device_status": "Accepted"},
        )

    with patch(
        "app.api.v1.app.charging.send_remote_start",
        new=AsyncMock(side_effect=accepted),
    ) as sender:
        first = asyncio.create_task(
            charging._coalesced_remote_start(("user", "qr", 1), "CP-1", "TAG", 1)
        )
        await entered.wait()
        second = asyncio.create_task(
            charging._coalesced_remote_start(("user", "qr", 1), "CP-1", "TAG", 1)
        )
        release.set()
        first_result, second_result = await asyncio.gather(first, second)

    assert first_result.success is True
    assert second_result.success is True
    assert sender.await_count == 1
    charging._start_attempts.clear()


def test_wallet_transactions_serialize_charge_and_payment_ledgers(
    client, db_session, sample_tenant, sample_site, sample_charge_point, sample_evse
):
    user = _create_app_user(
        db_session,
        email="p0-wallet@example.test",
        balance=Decimal("50000.00"),
    )
    payment_order = PaymentOrder(
        id=uuid.uuid4(),
        app_user_id=user.id,
        type="top_up",
        amount=Decimal("25000.00"),
        currency="COP",
        payment_provider="fake",
        status="approved",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    now = datetime.now(timezone.utc)
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=908172,
        id_tag=f"APP{str(user.id).replace('-', '')[:17]}",
        app_user_id=user.id,
        start_time=now,
        end_time=now,
        meter_start=0,
        meter_stop=162,
        status="completed",
        payment_status="paid",
    )
    tariff = Tariff(
        tenant_id=sample_tenant.id,
        site_id=sample_site.id,
        name="P0 wallet tariff",
        base_price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        valid_from=now,
        is_active=True,
    )
    db_session.add_all([session, tariff])
    db_session.flush()
    snapshot = PricingSnapshot(
        tenant_id=sample_tenant.id,
        tariff_id=tariff.id,
        session_id=session.id,
        price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
    )
    db_session.add(snapshot)
    db_session.flush()
    invoice = Invoice(
        invoice_number="INV-P0-WALLET-001",
        tenant_id=sample_tenant.id,
        session_id=session.id,
        pricing_snapshot_id=snapshot.id,
        energy_kwh=Decimal("0.162"),
        duration_minutes=Decimal("1.70"),
        energy_cost=Decimal("437.40"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("437.40"),
        status="paid",
    )
    db_session.add(invoice)
    db_session.flush()
    charging_ledger = AppWalletTransaction(
        id=uuid.uuid4(),
        transaction_number="wallet-p0-charge",
        app_user_id=user.id,
        invoice_id=invoice.id,
        operator_tenant_id=sample_tenant.id,
        charge_point_id=sample_charge_point.id,
        type="charge",
        amount=Decimal("-1200.00"),
        description="Charging settlement",
        idempotency_key="wallet-p0-charge",
    )
    payment_ledger = AppWalletTransaction(
        id=uuid.uuid4(),
        transaction_number="wallet-p0-payment",
        app_user_id=user.id,
        payment_order_id=payment_order.id,
        operator_tenant_id=sample_tenant.id,
        charge_point_id=None,
        type="top_up",
        amount=Decimal("25000.00"),
        description="Approved payment",
        idempotency_key="wallet-p0-payment",
    )
    db_session.add_all([payment_order, charging_ledger, payment_ledger])
    db_session.commit()

    response = client.get(
        "/api/v1/app/wallet/transactions",
        headers=_app_headers(user),
    )

    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()}
    assert set(by_id) == {str(charging_ledger.id), str(payment_ledger.id)}
    assert by_id[str(charging_ledger.id)]["charge_point_name"] == sample_site.name
    assert by_id[str(charging_ledger.id)]["ocpp_identity"] == sample_charge_point.ocpp_identity
    assert by_id[str(charging_ledger.id)]["charging_session_id"] == str(session.id)
    assert by_id[str(payment_ledger.id)]["charge_point_name"] is None
    assert by_id[str(payment_ledger.id)]["charging_session_id"] is None
    for transaction_id, transaction in by_id.items():
        assert str(uuid.UUID(transaction_id)) == transaction_id
        assert transaction["reference"]
        assert str(transaction_id) not in transaction["reference"]

    detail = client.get(
        f"/api/v1/app/transactions/{session.id}",
        headers=_app_headers(user),
    )
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["invoice_number"] == invoice.invoice_number
    assert payload["total_amount"] == "437.40"
    assert payload["currency"] == "COP"
    assert payload["billing_status"] == "paid"
    assert payload["connector_number"] == sample_evse.evse_id
    assert payload["charge_point_label"] == sample_charge_point.display_code

    other_user = _create_app_user(
        db_session,
        email="p0-wallet-other@example.test",
        balance=Decimal("0.00"),
    )
    forbidden = client.get(
        f"/api/v1/app/transactions/{session.id}",
        headers=_app_headers(other_user),
    )
    assert forbidden.status_code == 404


def test_billing_settlement_persists_wallet_invoice_link(
    db_session, sample_tenant, sample_site, sample_charge_point, sample_evse
):
    user = _create_app_user(
        db_session,
        email="p0-wallet-settlement@example.test",
        balance=Decimal("50000.00"),
    )
    now = datetime.now(timezone.utc)
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=908173,
        id_tag=f"APP{str(user.id).replace('-', '')[:17]}",
        app_user_id=user.id,
        start_time=now - timedelta(minutes=10),
        end_time=now,
        meter_start=1000,
        meter_stop=2000,
        status="completed",
        payment_status="pending",
    )
    tariff = Tariff(
        tenant_id=sample_tenant.id,
        site_id=sample_site.id,
        charge_point_id=sample_charge_point.id,
        name="P0 settlement tariff",
        base_price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        valid_from=now - timedelta(days=1),
        is_active=True,
    )
    db_session.add_all([session, tariff])
    db_session.commit()

    result = BillingService.settle_session(db_session, session, user)

    invoice_id = uuid.UUID(result.invoice_id)
    ledger = (
        db_session.query(AppWalletTransaction)
        .filter(AppWalletTransaction.invoice_id == invoice_id)
        .one()
    )
    assert ledger.type == "charge"
    assert ledger.app_user_id == user.id
    assert ledger.idempotency_key == f"charge:{session.id}"
