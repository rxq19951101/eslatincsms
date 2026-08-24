from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.database.models import (
    AppWalletTransaction,
    ChargingSession,
    Invoice,
    OutboxEvent,
    Payment,
    PaymentOrder,
    PricingSnapshot,
)
from app.services.billing_service import BillingService
from app.services.payment_providers.base import (
    ProviderCreateResult,
    ProviderPaymentStatus,
)
from app.services.payment_reconciliation import PaymentReconciliationService
from app.services.payment_reconciliation import PaymentReconciliationError
from app.core.config import Settings


class FakeCheckoutStore:
    def __init__(self, token="one-time-card-token"):
        self.token = token
        self.consumed = 0

    def consume_card_token(self, checkout_session_id):
        self.consumed += 1
        if self.token is None:
            raise RuntimeError("token unavailable")
        token, self.token = self.token, None
        return token

    def get(self, checkout_session_id):
        raise RuntimeError("projection not configured")


class FakeProvider:
    provider_code = "mercadopago"

    def __init__(self, result):
        self.result = result
        self.commands = []

    def create_payment(self, command, *, merchant_context):
        self.commands.append((command, merchant_context))
        return self.result

    def get_payment_status(self, payment_id, *, merchant_context):
        return ProviderPaymentStatus(
            status="approved",
            provider_payment_id=payment_id,
            external_reference="ext-be6",
            amount=Decimal("2700.00"),
            currency="COP",
        )


class FakeRegistry:
    def __init__(self, provider):
        self.provider = provider

    def get(self, provider_code):
        assert provider_code == "mercadopago"
        return self.provider


def _merchant():
    return {
        "merchant_mode": "platform",
        "merchant_account_ref": "platform:eslatin",
        "provider": "mercadopago",
        "marketplace_fee_policy": None,
    }


def _direct_fixture(db, sample_tenant, sample_charge_point, sample_evse, *, checkout_id="checkout-be6"):
    from app.database.models import AppUser, Order, PricingSnapshot, Tariff
    from app.services.pricing_service import PricingService

    now = datetime.now(timezone.utc)
    user = AppUser(email="be6@example.test", password_hash="test", balance=Decimal("0.00"))
    db.add(user)
    db.flush()
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=990000 + db.query(ChargingSession).count(),
        id_tag=f"APP{str(user.id).replace('-', '')[:17]}",
        user_id=str(user.id),
        app_user_id=user.id,
        start_time=now - timedelta(minutes=10),
        end_time=now,
        meter_start=0,
        meter_stop=1000,
        status="completed",
        payment_status="unpaid",
    )
    order = Order(
        tenant_id=sample_tenant.id,
        session_id=session.id,
        charge_point_id=sample_charge_point.id,
        user_id=str(user.id),
        app_user_id=user.id,
        id_tag=session.id_tag,
        status="completed",
        pre_authorization={
            "settlement_method": "direct_card",
            "checkout_session_id": checkout_id,
            "merchant": _merchant(),
            "payment_method": {
                "provider_payment_method_id": "visa",
                "provider_payment_type_id": "prepaid_card",
            },
        },
    )
    tariff = Tariff(
        tenant_id=sample_tenant.id,
        site_id=sample_charge_point.site_id,
        charge_point_id=sample_charge_point.id,
        name="BE-6 tariff",
        base_price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        valid_from=now - timedelta(days=1),
        is_active=True,
        time_based_rules=PricingService.metadata("paid"),
    )
    db.add_all([session, order, tariff])
    db.flush()
    order.session_id = session.id
    snapshot = PricingSnapshot(
        tenant_id=sample_tenant.id,
        tariff_id=tariff.id,
        session_id=session.id,
        order_id=order.id,
        price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        snapshot_data=PricingService.metadata("paid"),
        snapshot_time=session.start_time,
    )
    db.add(snapshot)
    db.commit()
    return user, session, order


def test_direct_card_uses_invoice_amount_and_one_time_token(
    db_session, sample_tenant, sample_charge_point, sample_evse, monkeypatch
):
    user, session, order = _direct_fixture(
        db_session, sample_tenant, sample_charge_point, sample_evse
    )
    provider = FakeProvider(
        ProviderCreateResult(
            status="approved",
            provider_order_ref="ext-be6",
            provider_payment_id="mp-be6-1",
        )
    )
    store = FakeCheckoutStore()
    monkeypatch.setattr(
        "app.services.payment_reconciliation.get_payment_provider_registry",
        lambda: FakeRegistry(provider),
    )
    monkeypatch.setattr(
        "app.services.payment_reconciliation.CheckoutSessionStore",
        lambda: store,
    )

    result = BillingService.settle_session(db_session, session, user)

    invoice = db_session.query(Invoice).filter(Invoice.session_id == session.id).one()
    payment_order = db_session.query(PaymentOrder).filter(
        PaymentOrder.id == session.payment_order_id
    ).one()
    assert result.payment_status == "paid"
    assert invoice.total_amount == Decimal("2700.00")
    assert payment_order.amount == invoice.total_amount
    assert payment_order.status == "approved"
    assert db_session.query(Payment).filter(Payment.invoice_id == invoice.id).count() == 1
    assert db_session.query(AppWalletTransaction).filter(
        AppWalletTransaction.app_user_id == user.id
    ).count() == 0
    assert store.consumed == 1
    assert provider.commands[0][0].amount == Decimal("2700.00")
    assert provider.commands[0][0].payment_method_id == "visa"
    assert provider.commands[0][1].merchant_account_ref == "platform:eslatin"
    events = db_session.query(OutboxEvent).filter(
        OutboxEvent.event_type == "financial.eligibility.recheck_requested",
        OutboxEvent.aggregate_id == str(user.id),
    ).all()
    assert len(events) == 1
    assert events[0].scope_ref == f"tenant:{sample_tenant.id}"
    assert events[0].payload["source_type"] == "payment_reconciliation"


def test_provider_hints_support_prepaid_and_fail_closed_without_canonical_type():
    service = PaymentReconciliationService()

    assert service._canonical_provider_hints(
        {
            "provider_payment_method_id": "master",
            "provider_payment_type_id": "prepaid_card",
        }
    ) == {
        "provider_payment_method_id": "master",
        "provider_payment_type_id": "prepaid_card",
    }
    with pytest.raises(PaymentReconciliationError):
        service._canonical_provider_hints(
            {
                "provider_payment_method_id": "master",
                "provider_payment_type_id": None,
            }
        )
    with pytest.raises(PaymentReconciliationError):
        service._canonical_provider_hints(
            {
                "provider_payment_method_id": "master",
                "provider_payment_type_id": "unknown_card",
            }
        )


def test_sandbox_uses_provider_safe_payer_email_without_changing_app_user():
    service = PaymentReconciliationService(
        settings=Settings(
            mercadopago_environment="sandbox",
            mercadopago_sandbox_payer_email="test_payer@example.com",
        ),
    )

    assert service._payer_email("test_user_3385660957423494176@testuser.com") == (
        "test_payer@example.com"
    )

    production_service = PaymentReconciliationService(
        settings=Settings(
            mercadopago_environment="production",
            mercadopago_sandbox_payer_email="test_payer@example.com",
        ),
    )
    assert production_service._payer_email("user@example.com") == "user@example.com"


def test_d1_gate_uses_unpaid_session_facts_without_user_flag(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session, _ = _direct_fixture(
        db_session, sample_tenant, sample_charge_point, sample_evse
    )
    user.has_unpaid_charges = False
    db_session.commit()

    from app.api.v1.app.charging import _has_global_unpaid_charging_bill

    assert _has_global_unpaid_charging_bill(db_session, user.id) is True


def test_first_approved_attempt_wins_without_duplicate_payment(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session, order = _direct_fixture(db_session, sample_tenant, sample_charge_point, sample_evse)
    snapshot_id = db_session.query(PricingSnapshot.id).filter_by(session_id=session.id).one()[0]
    invoice = Invoice(
        tenant_id=session.tenant_id,
        session_id=session.id,
        order_id=order.id,
        pricing_snapshot_id=snapshot_id,
        energy_kwh=Decimal("1.000"),
        duration_minutes=Decimal("10.00"),
        energy_cost=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("2700.00"),
        status="pending",
    )
    db_session.add(invoice)
    db_session.flush()
    common = {
        "app_user_id": user.id,
        "type": "charging",
        "amount": Decimal("2700.00"),
        "currency": "COP",
        "payment_provider": "mercadopago",
        "status": "processing",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=20),
        "order_metadata": {
            "payment_purpose": "charging_direct",
            "invoice_id": str(invoice.id),
            "session_id": str(session.id),
            "operator_tenant_id": str(session.tenant_id),
            "merchant": _merchant(),
        },
    }
    first = PaymentOrder(idempotency_key="attempt-1", mercadopago_payment_id="mp-1", **common)
    second = PaymentOrder(idempotency_key="attempt-2", mercadopago_payment_id="mp-2", **common)
    db_session.add_all([first, second])
    db_session.commit()
    service = PaymentReconciliationService(
        provider_registry=FakeRegistry(FakeProvider(ProviderCreateResult(status="processing"))),
        checkout_store=FakeCheckoutStore(),
    )
    service.reconcile(
        db_session,
        payment_order_id=first.id,
        status="approved",
        provider_payment_id="mp-1",
        external_reference="ext-1",
        amount=Decimal("2700.00"),
        currency="COP",
    )
    service.reconcile(
        db_session,
        payment_order_id=second.id,
        status="approved",
        provider_payment_id="mp-2",
        external_reference="ext-2",
        amount=Decimal("2700.00"),
        currency="COP",
    )
    assert db_session.query(Payment).filter(Payment.invoice_id == invoice.id).count() == 1
    assert db_session.get(PaymentOrder, second.id).order_metadata["settlement_exception"] == "duplicate_approved"


def test_same_approved_provider_webhook_is_idempotent_after_settlement(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session, order = _direct_fixture(
        db_session, sample_tenant, sample_charge_point, sample_evse
    )
    snapshot_id = db_session.query(PricingSnapshot.id).filter_by(session_id=session.id).one()[0]
    invoice = Invoice(
        tenant_id=session.tenant_id,
        session_id=session.id,
        order_id=order.id,
        pricing_snapshot_id=snapshot_id,
        energy_kwh=Decimal("1.000"),
        duration_minutes=Decimal("10.00"),
        energy_cost=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("2700.00"),
        status="paid",
        paid_at=datetime.now(timezone.utc),
    )
    payment_order = PaymentOrder(
        app_user_id=user.id,
        type="charging",
        amount=Decimal("2700.00"),
        currency="COP",
        payment_provider="mercadopago",
        mercadopago_payment_id="mp-same-payment",
        status="approved",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        order_metadata={
            "payment_purpose": "charging_direct",
            "invoice_id": str(invoice.id),
            "session_id": str(session.id),
            "operator_tenant_id": str(session.tenant_id),
            "merchant": _merchant(),
        },
    )
    db_session.add_all([invoice, payment_order])
    db_session.flush()
    db_session.add(Payment(
        payment_number="PAY-BE6-SAME-PROVIDER",
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        amount=invoice.total_amount,
        payment_method="direct_card",
        payment_provider="mercadopago",
        transaction_id="mp-same-payment",
        status="completed",
        completed_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    service = PaymentReconciliationService(
        provider_registry=FakeRegistry(FakeProvider(ProviderCreateResult(status="processing"))),
        checkout_store=FakeCheckoutStore(),
    )
    result = service.reconcile(
        db_session,
        payment_order_id=payment_order.id,
        status="approved",
        provider_payment_id="mp-same-payment",
        external_reference="ext-same-payment",
        amount=Decimal("2700.00"),
        currency="COP",
    )

    refreshed = db_session.get(PaymentOrder, payment_order.id)
    assert result.duplicate_approved is False
    assert refreshed.order_metadata.get("settlement_exception") is None
    assert refreshed.order_metadata.get("refund_required") is None
    assert db_session.query(Payment).filter(Payment.invoice_id == invoice.id).count() == 1


def test_reconcile_rejects_amount_and_merchant_mismatch(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session, order = _direct_fixture(db_session, sample_tenant, sample_charge_point, sample_evse)
    snapshot_id = db_session.query(PricingSnapshot.id).filter_by(session_id=session.id).one()[0]
    invoice = Invoice(
        tenant_id=session.tenant_id,
        session_id=session.id,
        order_id=order.id,
        pricing_snapshot_id=snapshot_id,
        energy_kwh=Decimal("1.000"),
        duration_minutes=Decimal("10.00"),
        energy_cost=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("2700.00"),
        status="pending",
    )
    db_session.add(invoice)
    db_session.flush()
    payment_order = PaymentOrder(
        app_user_id=user.id,
        type="charging",
        amount=Decimal("2700.00"),
        currency="COP",
        payment_provider="mercadopago",
        idempotency_key="mismatch-be6",
        status="processing",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        order_metadata={
            "invoice_id": str(invoice.id),
            "session_id": str(session.id),
            "operator_tenant_id": str(session.tenant_id),
            "merchant": {**_merchant(), "merchant_account_ref": "platform:other"},
        },
    )
    db_session.add(payment_order)
    db_session.commit()
    service = PaymentReconciliationService(
        provider_registry=FakeRegistry(FakeProvider(ProviderCreateResult(status="processing"))),
        checkout_store=FakeCheckoutStore(),
    )
    with pytest.raises(PaymentReconciliationError):
        service.reconcile(
            db_session,
            payment_order_id=payment_order.id,
            status="approved",
            provider_payment_id="mp-mismatch",
            external_reference=None,
            amount=Decimal("2701.00"),
            currency="COP",
        )
    with pytest.raises(PaymentReconciliationError):
        service.merchant_context_for_order(payment_order=payment_order)


def test_late_processing_callback_cannot_reopen_declined_order(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session, order = _direct_fixture(db_session, sample_tenant, sample_charge_point, sample_evse)
    snapshot_id = db_session.query(PricingSnapshot.id).filter_by(session_id=session.id).one()[0]
    invoice = Invoice(
        tenant_id=session.tenant_id,
        session_id=session.id,
        order_id=order.id,
        pricing_snapshot_id=snapshot_id,
        energy_kwh=Decimal("1.000"),
        duration_minutes=Decimal("10.00"),
        energy_cost=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("2700.00"),
        status="pending",
    )
    db_session.add(invoice)
    db_session.flush()
    po = PaymentOrder(
        app_user_id=user.id,
        type="charging",
        amount=Decimal("2700.00"),
        currency="COP",
        payment_provider="mercadopago",
        idempotency_key="ordering-be6",
        mercadopago_payment_id="mp-ordering",
        status="processing",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        order_metadata={
            "invoice_id": str(invoice.id),
            "session_id": str(session.id),
            "operator_tenant_id": str(session.tenant_id),
            "merchant": _merchant(),
        },
    )
    db_session.add(po)
    db_session.commit()
    service = PaymentReconciliationService(
        provider_registry=FakeRegistry(FakeProvider(ProviderCreateResult(status="processing"))),
        checkout_store=FakeCheckoutStore(),
    )
    service.reconcile(
        db_session,
        payment_order_id=po.id,
        status="declined",
        provider_payment_id="mp-ordering",
        external_reference=None,
        amount=Decimal("2700.00"),
        currency="COP",
    )
    result = service.reconcile(
        db_session,
        payment_order_id=po.id,
        status="processing",
        provider_payment_id="mp-ordering",
        external_reference=None,
        amount=Decimal("2700.00"),
        currency="COP",
    )
    assert result.order_status == "declined"
    assert db_session.get(ChargingSession, session.id).payment_status == "unpaid"


@pytest.mark.parametrize("status", ["processing", "action_required", "declined", "expired", "error"])
def test_reconcile_projects_non_approved_states(
    db_session, sample_tenant, sample_charge_point, sample_evse, status
):
    user, session, order = _direct_fixture(db_session, sample_tenant, sample_charge_point, sample_evse)
    snapshot_id = db_session.query(PricingSnapshot.id).filter_by(session_id=session.id).one()[0]
    invoice = Invoice(
        tenant_id=session.tenant_id,
        session_id=session.id,
        order_id=order.id,
        pricing_snapshot_id=snapshot_id,
        energy_kwh=Decimal("1.000"),
        duration_minutes=Decimal("10.00"),
        energy_cost=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("2700.00"),
        status="pending",
    )
    db_session.add(invoice)
    db_session.flush()
    po = PaymentOrder(
        app_user_id=user.id,
        type="charging",
        amount=Decimal("2700.00"),
        currency="COP",
        payment_provider="mercadopago",
        idempotency_key=f"status-{status}",
        mercadopago_payment_id=f"mp-{status}",
        status="processing",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        order_metadata={
            "payment_purpose": "charging_direct",
            "invoice_id": str(invoice.id),
            "session_id": str(session.id),
            "operator_tenant_id": str(session.tenant_id),
            "merchant": _merchant(),
        },
    )
    db_session.add(po)
    db_session.commit()
    result = PaymentReconciliationService(
        provider_registry=FakeRegistry(FakeProvider(ProviderCreateResult(status="processing"))),
        checkout_store=FakeCheckoutStore(),
    ).reconcile(
        db_session,
        payment_order_id=po.id,
        status=status,
        provider_payment_id=po.mercadopago_payment_id,
        external_reference=None,
        amount=Decimal("2700.00"),
        currency="COP",
        next_action_url=(
            "https://mercadopago.com/3ds" if status == "action_required" else None
        ),
    )
    assert result.api_status == status
    assert db_session.get(ChargingSession, session.id).payment_status == (
        "pending" if status in {"processing", "action_required"} else "unpaid"
    )
