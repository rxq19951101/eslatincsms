"""Direct BE-207 authority, dual-control and Provider safety coverage."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.database.models import (
    AppUser,
    ChargebackCase,
    ChargingSession,
    Invoice,
    PaymentAllocation,
    PaymentOrder,
    PaymentWebhookEvent,
    PricingSnapshot,
    RecoveryAttempt,
    RefundCase,
    RefundAttempt,
    Tariff,
)
from app.database.base import tenant_id_context
from app.services.payment_providers.base import (
    DisputeCapabilityFact,
    PaymentCapabilityResult,
    ProviderCapabilityError,
    RefundCapabilityFacts,
    RefundCapabilityResult,
)
from app.services.payment_reconciliation import PaymentReconciliationService
from app.services.refund_cases import (
    RefundApprovalConflict,
    RefundCaseService,
    RefundIdempotencyConflict,
    RefundInvalidTarget,
    RefundNotFound,
)


class FakeRefundProvider:
    provider_code = "mercadopago"

    def __init__(self):
        self.total = Decimal("0.00")
        self.create_calls = 0
        self.timeout = False

    def query_refund_capability(self, provider_ref, *, merchant_context):
        return RefundCapabilityFacts(refunded_amount=self.total, refund_refs=())

    def create_refund_capability(self, command, *, merchant_context, idempotency_key):
        self.create_calls += 1
        if self.timeout:
            raise ProviderCapabilityError("provider_unavailable", retryable=True)
        self.total += command.amount
        return RefundCapabilityResult(status="refunded", refund_ref=f"provider-ref-{self.create_calls}", amount=command.amount)


class FakeReconciliation(PaymentReconciliationService):
    def __init__(self, provider):
        super().__init__(provider_registry=SimpleNamespace(get=lambda _: provider))

    def merchant_context_for_order(self, *, payment_order, purpose):
        return SimpleNamespace(provider="mercadopago", merchant_account_ref="platform:eslatin")


def _facts(db, tenant, charge_point, evse):
    now = datetime.now(timezone.utc)
    user = AppUser(email=f"be207-{uuid4()}@example.test", password_hash="test", balance=Decimal("0.00"))
    session = ChargingSession(
        tenant_id=tenant.id, evse_id=evse.id, charge_point_id=charge_point.id,
        transaction_id=uuid4().int % 100000, id_tag=f"APP{uuid4().hex[:12]}",
        user_id=str(user.id), app_user_id=user.id, start_time=now - timedelta(minutes=10),
        end_time=now, meter_start=0, meter_stop=1000, status="completed", payment_status="paid",
    )
    tariff = Tariff(
        tenant_id=tenant.id, site_id=charge_point.site_id, name=f"BE-207 {uuid4()}",
        base_price_per_kwh=Decimal("2700.00"), service_fee=Decimal("0.00"),
        valid_from=now - timedelta(days=1), is_active=True,
    )
    db.add_all([user, session, tariff])
    db.flush()
    snapshot = PricingSnapshot(
        tenant_id=tenant.id, tariff_id=tariff.id, session_id=session.id,
        price_per_kwh=Decimal("2700.00"), service_fee=Decimal("0.00"), snapshot_time=now,
    )
    db.add(snapshot)
    db.flush()
    invoice = Invoice(
        tenant_id=tenant.id, session_id=session.id, pricing_snapshot_id=snapshot.id,
        total_amount=Decimal("2700.00"), energy_kwh=Decimal("1.000"), duration_minutes=Decimal("10.00"),
        energy_cost=Decimal("2700.00"), service_fee=Decimal("0.00"), status="paid", paid_at=now,
    )
    db.add(invoice)
    db.flush()
    order = PaymentOrder(
        app_user_id=user.id, type="charging", amount=Decimal("2700.00"), currency="COP",
        payment_provider="mercadopago", mercadopago_payment_id=f"mp-{uuid4().hex[:12]}", status="approved",
        expires_at=now + timedelta(days=1), order_metadata={
            "invoice_id": str(invoice.id), "operator_tenant_id": str(tenant.id),
            "merchant": {"merchant_mode": "platform", "merchant_account_ref": "platform:eslatin", "provider": "mercadopago"},
        },
    )
    recovery = RecoveryAttempt(
        tenant_id=tenant.id, app_user_id=user.id, invoice_id=invoice.id, session_id=session.id,
        attempt_number=1, method="new_card", provider="mercadopago", provider_account_ref="platform:eslatin",
        provider_operation_key=f"payment:{uuid4()}", provider_payment_ref=order.mercadopago_payment_id,
        target_amount=Decimal("2700.00"), allocated_amount=Decimal("2700.00"), status="allocated",
        idempotency_key=f"attempt:{uuid4()}", request_fingerprint="be207", audit_reference=f"audit:{uuid4()}",
    )
    db.add_all([order, recovery])
    db.flush()
    allocation = PaymentAllocation(
        tenant_id=tenant.id, invoice_id=invoice.id, recovery_attempt_id=recovery.id,
        payment_order_id=order.id, method="new_card", provider="mercadopago", amount=Decimal("2700.00"),
        currency="COP", status="committed", audit_reference=f"allocation:{uuid4()}", committed_at=now,
    )
    db.add(allocation)
    db.commit()
    return user, invoice, order, allocation


def test_refund_case_requires_distinct_actor_and_confirms_provider_amount(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    from app.database.models import AdminUser

    _user, _invoice, order, allocation = _facts(db_session, sample_tenant, sample_charge_point, sample_evse)
    initiator = AdminUser(username=f"be207-init-{uuid4()}", email=f"be207-init-{uuid4()}@example.test", password_hash="test")
    approver = AdminUser(username=f"be207-approve-{uuid4()}", email=f"be207-approve-{uuid4()}@example.test", password_hash="test")
    db_session.add_all([initiator, approver])
    db_session.commit()
    provider = FakeRefundProvider()
    service = RefundCaseService(reconciliation=FakeReconciliation(provider))
    tenant_id_context.set(sample_tenant.id)

    case = service.create_refund_case(
        db_session, actor=initiator, allocation_id=allocation.id, requested_amount=Decimal("1000.00"),
        currency="COP", reason_code="customer_request", reason="customer request", idempotency_key="be207-case-1",
    )
    assert service.create_refund_case(
        db_session, actor=initiator, allocation_id=allocation.id, requested_amount=Decimal("1000.00"),
        currency="COP", reason_code="customer_request", reason="customer request", idempotency_key="be207-case-1",
    ).id == case.id
    with pytest.raises(RefundIdempotencyConflict):
        service.create_refund_case(
            db_session, actor=initiator, allocation_id=allocation.id, requested_amount=Decimal("900.00"),
            currency="COP", reason_code="customer_request", reason="different", idempotency_key="be207-case-1",
        )
    with pytest.raises(RefundApprovalConflict):
        service.approve_refund_case(db_session, actor=initiator, case_id=case.id, decision="approve", expected_version=case.version, reason="same actor", idempotency_key="be207-approval-self")

    approved = service.approve_refund_case(
        db_session, actor=approver, case_id=case.id, decision="approve", expected_version=case.version,
        reason="reviewed", idempotency_key="be207-approval-1",
    )
    assert approved.status == "partially_refunded"
    assert approved.refunded_amount == Decimal("1000.00")
    assert db_session.query(RefundAttempt).filter(RefundAttempt.refund_case_id == case.id).one().status == "partially_refunded"
    assert provider.create_calls == 1
    assert order.status == "approved"


def test_refund_cumulative_limit_unknown_and_chargeback_replay_are_fail_closed(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    from app.database.models import AdminUser

    _user, _invoice, order, allocation = _facts(db_session, sample_tenant, sample_charge_point, sample_evse)
    initiator = AdminUser(username=f"be207-init2-{uuid4()}", email=f"be207-init2-{uuid4()}@example.test", password_hash="test")
    approver = AdminUser(username=f"be207-approve2-{uuid4()}", email=f"be207-approve2-{uuid4()}@example.test", password_hash="test")
    db_session.add_all([initiator, approver])
    db_session.commit()
    provider = FakeRefundProvider()
    service = RefundCaseService(reconciliation=FakeReconciliation(provider))
    tenant_id_context.set(sample_tenant.id)

    first = service.create_refund_case(db_session, actor=initiator, allocation_id=allocation.id, requested_amount=Decimal("1000.00"), currency="COP", reason_code="customer_request", reason="partial", idempotency_key="be207-partial")
    confirmed = service.approve_refund_case(db_session, actor=approver, case_id=first.id, decision="approve", expected_version=first.version, reason="confirmed", idempotency_key="be207-confirmed")
    assert confirmed.status == "partially_refunded"
    second = service.create_refund_case(db_session, actor=initiator, allocation_id=allocation.id, requested_amount=Decimal("1700.00"), currency="COP", reason_code="customer_request", reason="second", idempotency_key="be207-second")
    provider.timeout = True
    unknown = service.approve_refund_case(db_session, actor=approver, case_id=second.id, decision="approve", expected_version=second.version, reason="timeout", idempotency_key="be207-timeout")
    assert unknown.status == "unknown"
    assert db_session.query(RefundAttempt).filter(RefundAttempt.refund_case_id == second.id).one().status == "unknown"
    provider.timeout = False
    with pytest.raises(RefundInvalidTarget):
        service.create_refund_case(db_session, actor=initiator, allocation_id=allocation.id, requested_amount=Decimal("1700.01"), currency="COP", reason_code="customer_request", reason="overage", idempotency_key="be207-overage")

    chargeback = service.ingest_chargeback_fact(
        db_session, provider="mercadopago", payment_ref=order.mercadopago_payment_id,
        disputed_amount=Decimal("2700.00"), currency="COP", status="disputed", dispute_ref="dispute-1",
        deadline_at="2026-08-20T12:00:00Z", funds_state="held", evidence_reference="evidence-1", source_reference="webhook-1",
    )
    replay = service.ingest_chargeback_fact(
        db_session, provider="mercadopago", payment_ref=order.mercadopago_payment_id,
        disputed_amount=Decimal("2700.00"), currency="COP", status="disputed", dispute_ref="dispute-1",
        deadline_at="2026-08-20T12:00:00Z", funds_state="held", evidence_reference="evidence-1", source_reference="webhook-1",
    )
    assert chargeback.id == replay.id
    assert db_session.query(ChargebackCase).count() == 1
    projection = service.project_chargeback(db_session, chargeback)
    assert projection["status"] == "hold"
    assert projection["funds_state"] == "held"
    assert projection["deadline_at"] == "2026-08-20T12:00:00Z"


class FakeMercadoPagoWebhookProvider:
    provider_code = "mercadopago"

    def __init__(self, payment_ref: str, status: str):
        self.payment_ref = payment_ref
        self.status = status
        self.dispute_ingest_calls = 0

    def verify_webhook_signature(self, **kwargs):
        return True

    def query_payment(self, provider_ref, *, merchant_context):
        return PaymentCapabilityResult(
            status=self.status,
            provider_ref=self.payment_ref,
            amount=Decimal("2700.00"),
            currency="COP",
        )

    def ingest_dispute_fact(self, payload, *, merchant_context):
        self.dispute_ingest_calls += 1
        return DisputeCapabilityFact(
            payment_ref=payload["payment_ref"],
            status="disputed",
            amount=payload["amount"],
            currency=payload["currency"],
            dispute_ref=payload["dispute_ref"],
            reason_code=payload.get("reason_code"),
        )


def _patch_webhook_provider(monkeypatch, provider):
    monkeypatch.setattr(
        "app.api.v1.app.payments.get_payment_provider_registry",
        lambda: SimpleNamespace(get=lambda _provider: provider),
    )
    monkeypatch.setattr(
        PaymentReconciliationService,
        "merchant_context_for_order",
        lambda self, *, payment_order, purpose: SimpleNamespace(
            provider="mercadopago", merchant_account_ref="platform:eslatin"
        ),
    )


def test_mercado_pago_chargeback_webhook_writes_authority_and_replays_safely(
    client, db_session, sample_tenant, sample_charge_point, sample_evse, monkeypatch
):
    _user, _invoice, order, _allocation = _facts(
        db_session, sample_tenant, sample_charge_point, sample_evse
    )
    provider = FakeMercadoPagoWebhookProvider(order.mercadopago_payment_id, "disputed")
    _patch_webhook_provider(monkeypatch, provider)
    payload = {
        "id": "mp-dispute-event-1",
        "action": "payment.updated",
        "data": {"id": order.mercadopago_payment_id, "dispute_ref": "mp-dispute-1"},
        "payer": {"card": "4111111111111111", "cvv": "123"},
    }
    headers = {"X-Signature": "verified", "X-Request-Id": "request-1"}

    first = client.post("/api/v1/app/payments/webhooks/mercadopago", json=payload, headers=headers)
    replay = client.post("/api/v1/app/payments/webhooks/mercadopago", json=payload, headers=headers)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert provider.dispute_ingest_calls == 1
    case = db_session.query(ChargebackCase).one()
    assert case.tenant_id == sample_tenant.id
    assert case.payment_allocation_id == _allocation.id
    assert case.status == "hold"
    assert db_session.query(RefundCase).count() == 0
    assert db_session.query(ChargebackCase).count() == 1
    event = db_session.query(PaymentWebhookEvent).one()
    assert event.payload == {
        "id": "mp-dispute-event-1",
        "action": "payment.updated",
        "data": {"id": order.mercadopago_payment_id},
    }
    assert "4111111111111111" not in str(event.payload)
    assert "123" not in str(event.payload)

    tenant_id_context.set(uuid4())
    with pytest.raises(RefundNotFound):
        RefundCaseService().get_chargeback_case(
            db_session,
            admin=SimpleNamespace(is_super_admin=False),
            case_id=case.id,
        )


def test_mercado_pago_unknown_or_invalid_webhook_is_fail_closed_without_chargeback(
    client, db_session, sample_tenant, sample_charge_point, sample_evse, monkeypatch
):
    _user, _invoice, order, _allocation = _facts(
        db_session, sample_tenant, sample_charge_point, sample_evse
    )
    provider = FakeMercadoPagoWebhookProvider(order.mercadopago_payment_id, "unknown")
    _patch_webhook_provider(monkeypatch, provider)
    unknown = client.post(
        "/api/v1/app/payments/webhooks/mercadopago",
        json={
            "id": "mp-unknown-event-1",
            "action": "payment.updated",
            "data": {"id": order.mercadopago_payment_id},
        },
        headers={"X-Signature": "verified", "X-Request-Id": "request-unknown"},
    )
    invalid = client.post(
        "/api/v1/app/payments/webhooks/mercadopago",
        json={"id": "missing-payment-id", "action": "payment.updated"},
        headers={"X-Signature": "verified", "X-Request-Id": "request-invalid"},
    )

    assert unknown.status_code == 200
    assert invalid.status_code == 400
    assert provider.dispute_ingest_calls == 0
    assert db_session.query(ChargebackCase).count() == 0
