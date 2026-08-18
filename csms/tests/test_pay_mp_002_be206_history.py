"""Direct BE-206 coverage for the safe App transaction projection."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.auth import create_access_token, get_password_hash
from app.database.models import (
    AppUser,
    ChargebackCase,
    ChargingSession,
    Invoice,
    Payment,
    PaymentAllocation,
    PaymentOrder,
    PricingSnapshot,
    RecoveryAttempt,
    RefundCase,
    Tariff,
    Tenant,
)


P002_ACCEPT = "application/vnd.eslatin.pay-mp-002.v1+json"
CVV_SENTINEL = "CVV_SENTINEL_NON_REFERENCE"
_SENSITIVE_PROJECTION_KEYS = {
    "pan",
    "card_number",
    "card_pan",
    "cvv",
    "security_code",
    "token",
    "access_token",
    "payment_token",
    "three_ds_secret",
    "provider_payload",
    "raw_provider",
    "raw_provider_payload",
    "provider_response",
    "raw_response",
}


def _assert_no_sensitive_projection_data(value, sensitive_values: set[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert str(key).lower() not in _SENSITIVE_PROJECTION_KEYS
            _assert_no_sensitive_projection_data(nested, sensitive_values)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_sensitive_projection_data(nested, sensitive_values)
    else:
        assert value not in sensitive_values


def _app_user(db_session, email: str) -> AppUser:
    user = AppUser(
        id=uuid.uuid4(),
        email=email,
        password_hash=get_password_hash("test-password"),
        email_verified=True,
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _headers(user: AppUser, accept: str | None = None) -> dict[str, str]:
    token = create_access_token(
        {"user_id": str(user.id), "user_type": "app_user", "aud": "app"}
    )
    headers = {"Authorization": f"Bearer {token}"}
    if accept:
        headers["Accept"] = accept
    return headers


def _history_facts(
    db_session,
    user: AppUser,
    sample_tenant,
    sample_site,
    sample_charge_point,
    sample_evse,
    *,
    start_time: datetime | None = None,
):
    now = start_time or datetime.now(timezone.utc)
    session = ChargingSession(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=uuid.uuid4().int % 100000,
        id_tag=f"APP{str(user.id).replace('-', '')[:17]}",
        user_id=str(user.id),
        app_user_id=user.id,
        start_time=now,
        end_time=now + timedelta(minutes=30),
        meter_start=1000,
        meter_stop=2234,
        status="completed",
    )
    tariff = Tariff(
        tenant_id=sample_tenant.id,
        site_id=sample_site.id,
        name=f"BE-206 tariff {uuid.uuid4()}",
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
        snapshot_time=now,
    )
    invoice = Invoice(
        invoice_number=f"INV-BE206-{uuid.uuid4().hex[:12]}",
        tenant_id=sample_tenant.id,
        session_id=session.id,
        pricing_snapshot_id=snapshot.id,
        energy_kwh=Decimal("1.234"),
        duration_minutes=Decimal("30.00"),
        energy_cost=Decimal("3331.80"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("3331.80"),
        status="pending",
        issued_at=now,
    )
    db_session.add(snapshot)
    db_session.flush()
    invoice.pricing_snapshot_id = snapshot.id
    db_session.add(invoice)
    db_session.flush()
    order = PaymentOrder(
        id=uuid.uuid4(),
        app_user_id=user.id,
        type="charging",
        amount=Decimal("3331.80"),
        currency="COP",
        payment_provider="provider-secret-must-not-leak",
        reference=f"ORDER-BE206-{uuid.uuid4().hex[:8]}",
        status="processing",
        expires_at=now + timedelta(days=1),
        order_metadata={
            "session_id": str(session.id),
            "invoice_id": str(invoice.id),
            "settlement_method": "new_card",
            "pan": "4111111111111111",
            "cvv": CVV_SENTINEL,
            "access_token": "synthetic-token",
            "three_ds_secret": "synthetic-3ds-secret",
            "provider_payload": "raw-provider-payload",
        },
    )
    payment = Payment(
        id=uuid.uuid4(),
        payment_number=f"PAY-BE206-{uuid.uuid4().hex[:8]}",
        tenant_id=sample_tenant.id,
        invoice_id=invoice.id,
        amount=Decimal("3331.80"),
        payment_method="new_card",
        payment_provider="raw-provider-name",
        transaction_id=f"raw-provider-transaction-id-{uuid.uuid4().hex}",
        status="pending",
        initiated_at=now,
    )
    attempt = RecoveryAttempt(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        app_user_id=user.id,
        invoice_id=invoice.id,
        session_id=session.id,
        attempt_number=1,
        method="new_card",
        provider="raw-provider-name",
        provider_account_ref=f"raw-account-ref-{uuid.uuid4().hex}",
        provider_operation_key=f"raw-operation-key-{uuid.uuid4().hex}",
        provider_payment_ref=f"raw-payment-ref-{uuid.uuid4().hex}",
        target_amount=Decimal("3331.80"),
        allocated_amount=Decimal("0.00"),
        status="processing",
        idempotency_key=f"be206-{uuid.uuid4()}",
        request_fingerprint="synthetic-fingerprint",
        audit_reference=f"AUDIT-BE206-{uuid.uuid4().hex[:8]}",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([order, payment, attempt])
    db_session.commit()
    return session, invoice, order, payment, attempt


def test_p002_golden_projection_is_decimal_and_safe(
    client,
    db_session,
    sample_tenant,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    user = _app_user(db_session, "be206-golden@example.test")
    session, invoice, order, payment, attempt = _history_facts(
        db_session,
        user,
        sample_tenant,
        sample_site,
        sample_charge_point,
        sample_evse,
    )

    response = client.get(
        "/api/v1/app/transactions",
        headers=_headers(user, P002_ACCEPT),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(P002_ACCEPT)
    assert response.headers["vary"] == "Accept"
    body = response.json()
    assert set(body) == {"items", "page"}
    assert body["page"]["has_more"] is False
    item = body["items"][0]
    assert item["id"] == str(session.id)
    assert item["energy_kwh"] == "1.234"
    assert item["duration_minutes"] == "30.00"
    assert item["session"]["status"] == "completed"
    assert item["payment_status"] == "processing"
    assert item["invoice"]["reference"] == invoice.invoice_number
    assert item["invoice"]["amount"] == "3331.80"
    assert item["payments"][0]["status"] == "processing"
    assert item["payments"][0]["reference"] == payment.payment_number
    assert item["recovery_attempts"][0]["status"] == "processing"
    assert item["recovery_attempts"][0]["reference"] == attempt.audit_reference
    assert item["data_quality"] == "current"

    _assert_no_sensitive_projection_data(
        body,
        {
            "provider-secret-must-not-leak",
            "raw-provider-name",
            payment.transaction_id,
            attempt.provider_account_ref,
            attempt.provider_operation_key,
            attempt.provider_payment_ref,
            "synthetic-token",
            "synthetic-3ds-secret",
            "raw-provider-payload",
            "4111111111111111",
            CVV_SENTINEL,
        },
    )


def test_p002_statuses_distinguish_unpaid_paid_refunded_disputed_unknown(
    client,
    db_session,
    sample_tenant,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    user = _app_user(db_session, "be206-status@example.test")
    session, invoice, _order, payment, attempt = _history_facts(
        db_session,
        user,
        sample_tenant,
        sample_site,
        sample_charge_point,
        sample_evse,
    )

    attempt.status = "provider_approved"
    invoice.status = "paid"
    invoice.paid_at = datetime.now(timezone.utc)
    payment.status = "completed"
    payment.completed_at = datetime.now(timezone.utc)
    allocation = PaymentAllocation(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        invoice_id=invoice.id,
        recovery_attempt_id=attempt.id,
        method="new_card",
        provider="raw-provider-name",
        amount=Decimal("3331.80"),
        status="committed",
        audit_reference="ALLOC-BE206-001",
        committed_at=datetime.now(timezone.utc),
    )
    db_session.add(allocation)
    db_session.commit()

    paid = client.get(
        f"/api/v1/app/transactions/{session.id}",
        headers=_headers(user, P002_ACCEPT),
    )
    assert paid.status_code == 200
    assert paid.json()["payment_status"] == "paid"
    assert paid.json()["allocations"][0]["status"] == "confirmed"

    refund = RefundCase(
        id=uuid.uuid4(),
        case_reference="REFUND-BE206-001",
        tenant_id=sample_tenant.id,
        app_user_id=user.id,
        invoice_id=invoice.id,
        payment_allocation_id=allocation.id,
        requested_amount=Decimal("3331.80"),
        approved_amount=Decimal("3331.80"),
        refunded_amount=Decimal("0.00"),
        reason_code="user_request",
        status="provider_processing",
        audit_reference="REFUND-AUDIT-BE206-001",
    )
    db_session.add(refund)
    db_session.commit()
    processing = client.get(
        f"/api/v1/app/transactions/{session.id}",
        headers=_headers(user, P002_ACCEPT),
    )
    assert processing.json()["payment_status"] == "processing"

    refund.status = "refunded"
    refund.refunded_amount = Decimal("3331.80")
    invoice.status = "refunded"
    payment.status = "refunded"
    db_session.commit()
    refunded = client.get(
        f"/api/v1/app/transactions/{session.id}",
        headers=_headers(user, P002_ACCEPT),
    )
    assert refunded.json()["payment_status"] == "refunded"

    chargeback = ChargebackCase(
        id=uuid.uuid4(),
        case_reference="CB-BE206-001",
        tenant_id=sample_tenant.id,
        app_user_id=user.id,
        invoice_id=invoice.id,
        payment_allocation_id=allocation.id,
        provider="raw-provider-name",
        provider_account_ref="raw-account-ref",
        provider_dispute_ref="raw-dispute-ref",
        disputed_amount=Decimal("3331.80"),
        status="hold",
        audit_reference="CB-AUDIT-BE206-001",
        received_at=datetime.now(timezone.utc),
    )
    db_session.add(chargeback)
    db_session.commit()
    disputed = client.get(
        f"/api/v1/app/transactions/{session.id}",
        headers=_headers(user, P002_ACCEPT),
    )
    assert disputed.json()["payment_status"] == "disputed"

    chargeback.status = "unknown"
    db_session.commit()
    unknown = client.get(
        f"/api/v1/app/transactions/{session.id}",
        headers=_headers(user, P002_ACCEPT),
    )
    assert unknown.json()["payment_status"] == "unknown"
    assert unknown.json()["data_quality"] == "unknown"


def test_p001_remains_bare_array_with_legacy_numeric_fields(
    client,
    db_session,
    sample_tenant,
    sample_charge_point,
    sample_evse,
):
    user = _app_user(db_session, "be206-p001@example.test")
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=206001,
        id_tag=f"APP{str(user.id).replace('-', '')[:17]}",
        user_id=str(user.id),
        app_user_id=user.id,
        start_time=datetime.now(timezone.utc),
        meter_start=1000,
        meter_stop=2000,
        status="ongoing",
    )
    db_session.add(session)
    db_session.commit()

    response = client.get(
        "/api/v1/app/transactions",
        headers=_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert set(body[0]) == {
        "id",
        "transaction_id",
        "charge_point_id",
        "ocpp_identity",
        "evse_id",
        "start_time",
        "end_time",
        "status",
        "energy_kwh",
        "duration_minutes",
        "site_name",
        "site_address",
    }
    assert isinstance(body[0]["energy_kwh"], float)
    assert body[0]["energy_kwh"] == 1.0


def test_p002_cursor_pagination_and_ownership(
    client,
    db_session,
    sample_tenant,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    user = _app_user(db_session, "be206-page@example.test")
    other = _app_user(db_session, "be206-other@example.test")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sessions = []
    for index in range(3):
        session, _invoice, _order, _payment, _attempt = _history_facts(
            db_session,
            user,
            sample_tenant,
            sample_site,
            sample_charge_point,
            sample_evse,
            start_time=base + timedelta(minutes=index),
        )
        sessions.append(session)

    first = client.get(
        "/api/v1/app/transactions?limit=1",
        headers=_headers(user, P002_ACCEPT),
    )
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["items"]) == 1
    assert first_body["page"]["has_more"] is True
    cursor = first_body["page"]["next_cursor"]

    second = client.get(
        f"/api/v1/app/transactions?limit=1&cursor={cursor}",
        headers=_headers(user, P002_ACCEPT),
    )
    assert second.status_code == 200
    assert second.json()["items"][0]["id"] != first_body["items"][0]["id"]

    offset = client.get(
        "/api/v1/app/transactions?offset=1",
        headers=_headers(user, P002_ACCEPT),
    )
    assert offset.status_code == 400
    assert offset.json()["error"]["code"] == "PAGINATION_MODE_INVALID"

    forbidden = client.get(
        f"/api/v1/app/transactions/{sessions[0].id}",
        headers=_headers(other, P002_ACCEPT),
    )
    assert forbidden.status_code == 404
    assert client.get(
        "/api/v1/app/transactions",
        headers=_headers(other, P002_ACCEPT),
    ).json()["items"] == []

    tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
    invalid = client.get(
        f"/api/v1/app/transactions?cursor={tampered}",
        headers=_headers(user, P002_ACCEPT),
    )
    assert invalid.status_code == 409
