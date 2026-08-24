from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.database.models import (
    AppWalletTransaction,
    AppUser,
    AppUserPaymentMethod,
    ChargingSession,
    Invoice,
    Order,
    OutboxEvent,
    PaymentOrder,
    PricingSnapshot,
    Tariff,
)
from app.services.billing_service import BillingService
from app.services.payment_providers.base import (
    ProviderRefundFacts,
    ProviderRefundResult,
    ProviderCreateResult,
    ProviderPaymentStatus,
    PaymentProviderError,
)
from app.services.payment_reconciliation import PaymentReconciliationService
from app.services.payment_method_codec import encode_payment_method_brand
from app.services.payment_refunds import (
    PaymentRefundService,
    RefundManualReviewRequired,
    RefundRequestInvalid,
    RefundRetryable,
)


class RefundProvider:
    provider_code = "mercadopago"

    def __init__(self, *, timeout=False):
        self.total = Decimal("0.00")
        self.timeout = timeout
        self.create_calls = 0

    def get_payment_status(self, payment_id, *, merchant_context):
        return ProviderPaymentStatus(
            status="approved",
            provider_payment_id=payment_id,
            external_reference="unused",
            amount=Decimal("2700.00"),
            currency="COP",
        )

    def create_payment(self, command, *, merchant_context):
        return ProviderCreateResult(status="approved", provider_payment_id="mp-unused")

    def get_refund_facts(self, payment_id, *, merchant_context):
        return ProviderRefundFacts(refunded_amount=self.total)

    def create_refund(self, payment_id, amount, *, idempotency_key, merchant_context):
        self.create_calls += 1
        if self.timeout:
            raise PaymentProviderError("provider_timeout", retryable=True)
        self.total += Decimal(str(amount))
        return ProviderRefundResult(
            refund_id=f"refund-{self.create_calls}",
            status="approved",
            amount=Decimal(str(amount)),
        )


class Registry:
    def __init__(self, provider):
        self.provider = provider

    def get(self, provider_code):
        assert provider_code == "mercadopago"
        return self.provider


class HintProvider:
    provider_code = "mercadopago"

    def __init__(self):
        self.commands = []

    def create_payment(self, command, *, merchant_context):
        self.commands.append(command)
        return ProviderCreateResult(
            status="declined",
            provider_payment_id="mp-be7-hints",
        )

    def get_payment_status(self, payment_id, *, merchant_context):
        return ProviderPaymentStatus(
            status="declined",
            provider_payment_id=payment_id,
            external_reference=None,
            amount=Decimal("2700.00"),
            currency="COP",
        )


class HintCheckoutStore:
    def consume_card_token(self, checkout_session_id):
        return "be7-saved-mastercard-token"

    def get(self, checkout_session_id):
        raise RuntimeError("projection not configured")


def _merchant():
    return {
        "merchant_mode": "platform",
        "merchant_account_ref": "platform:eslatin",
        "provider": "mercadopago",
        "marketplace_fee_policy": None,
    }


def _direct_fixture(db, sample_tenant, sample_charge_point, sample_evse, *, checkout_id):
    from app.services.pricing_service import PricingService

    now = datetime.now(timezone.utc)
    user = AppUser(email=f"{checkout_id}@example.test", password_hash="test", balance=Decimal("0.00"))
    db.add(user)
    db.flush()
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=980000 + db.query(ChargingSession).count(),
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
        pre_authorization={"settlement_method": "direct_card", "checkout_session_id": checkout_id},
    )
    tariff = Tariff(
        tenant_id=sample_tenant.id,
        site_id=sample_charge_point.site_id,
        charge_point_id=sample_charge_point.id,
        name="BE-7 tariff",
        base_price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        valid_from=now - timedelta(days=1),
        is_active=True,
        time_based_rules=PricingService.metadata("paid"),
    )
    db.add_all([session, order, tariff])
    db.flush()
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


def _invoice_fixture(db, sample_tenant, sample_charge_point, sample_evse):
    user, session, order = _direct_fixture(
        db, sample_tenant, sample_charge_point, sample_evse, checkout_id="be7-checkout"
    )
    snapshot_id = db.query(Invoice).filter(Invoice.session_id == session.id).first()
    if snapshot_id is None:
        snapshot_id = db.query(PricingSnapshot.id).filter(
            PricingSnapshot.session_id == session.id
        ).one()[0]
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
    db.add(invoice)
    db.flush()
    order_metadata = {
        "payment_purpose": "charging_direct",
        "invoice_id": str(invoice.id),
        "session_id": str(session.id),
        "operator_tenant_id": str(session.tenant_id),
        "merchant": _merchant(),
    }
    order = PaymentOrder(
        app_user_id=user.id,
        type="charging",
        amount=Decimal("2700.00"),
        currency="COP",
        payment_provider="mercadopago",
        mercadopago_payment_id="mp-be7",
        status="approved",
        idempotency_key="be7-order",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        order_metadata=order_metadata,
    )
    db.add(order)
    db.commit()
    return user, session, invoice, order


def test_wallet_unpaid_uses_invoice_and_is_idempotent(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session, order = _direct_fixture(
        db_session, sample_tenant, sample_charge_point, sample_evse, checkout_id="be7-wallet"
    )
    user.balance = Decimal("3000.00")
    snapshot_id = db_session.query(PricingSnapshot.id).filter(
        PricingSnapshot.session_id == session.id
    ).one()[0]
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
    db_session.commit()
    first = BillingService.pay_unpaid_charge(
        db_session,
        app_user_id=user.id,
        session_id=session.id,
        idempotency_key="be7-wallet-1",
    )
    second = BillingService.pay_unpaid_charge(
        db_session,
        app_user_id=user.id,
        session_id=session.id,
        idempotency_key="be7-wallet-1",
    )
    assert first.payment_status == "paid"
    assert second.already_settled is True
    assert db_session.get(Invoice, invoice.id).total_amount == Decimal("2700.00")
    assert db_session.query(AppWalletTransaction).filter(
        AppWalletTransaction.invoice_id == invoice.id
    ).count() == 1


def test_saved_mastercard_debit_hint_survives_unpaid_reconciliation(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session, order = _direct_fixture(
        db_session,
        sample_tenant,
        sample_charge_point,
        sample_evse,
        checkout_id="be7-saved-mastercard",
    )
    order.session_id = session.id
    db_session.flush()
    snapshot_id = db_session.query(PricingSnapshot.id).filter(
        PricingSnapshot.session_id == session.id
    ).one()[0]
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
    saved = AppUserPaymentMethod(
        app_user_id=user.id,
        provider="mercadopago",
        mp_customer_id="customer-be7",
        mp_card_id="card-be7-mastercard",
        payment_method_brand=encode_payment_method_brand("master", "debit_card"),
        last_four="4444",
        is_default=True,
    )
    db_session.add_all([invoice, saved])
    db_session.flush()
    payment_order = PaymentOrder(
        app_user_id=user.id,
        type="charging",
        amount=Decimal("2700.00"),
        currency="COP",
        payment_provider="mercadopago",
        idempotency_key="be7-saved-mastercard-order",
        status="created",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        order_metadata={
            "payment_purpose": "unpaid_charge",
            "invoice_id": str(invoice.id),
            "session_id": str(session.id),
            "operator_tenant_id": str(session.tenant_id),
            "checkout_session_id": "be7-saved-mastercard",
            "merchant": _merchant(),
            "provider_hints": {"selected_payment_method_id": str(saved.id)},
        },
    )
    db_session.add(payment_order)
    db_session.commit()

    provider = HintProvider()
    service = PaymentReconciliationService(
        provider_registry=Registry(provider),
        checkout_store=HintCheckoutStore(),
    )
    assert service._payment_order_provider_hints(
        db_session, payment_order, user.id
    ) == {
        "provider_payment_method_id": "master",
        "provider_payment_type_id": "debit_card",
    }
    result = service.start_payment_order(db_session, payment_order_id=payment_order.id)

    assert result.api_status == "declined"
    assert provider.commands[0].payment_method_id == "master"


def test_direct_refund_serializes_partial_cumulative_amount(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    _, _, _, order = _invoice_fixture(
        db_session, sample_tenant, sample_charge_point, sample_evse
    )
    provider = RefundProvider()
    reconciliation = PaymentReconciliationService(provider_registry=Registry(provider))
    service = PaymentRefundService(reconciliation=reconciliation)
    first = service.refund_payment_order(
        db_session,
        payment_order_id=order.id,
        amount=Decimal("1000.00"),
        idempotency_key="refund-1",
    )
    second = service.refund_payment_order(
        db_session,
        payment_order_id=order.id,
        amount=Decimal("1700.00"),
        idempotency_key="refund-2",
    )
    assert first.refunded_amount == Decimal("1000.00")
    assert second.refunded_amount == Decimal("2700.00")
    assert db_session.get(PaymentOrder, order.id).status == "refunded"
    assert provider.create_calls == 2
    events = db_session.query(OutboxEvent).filter(
        OutboxEvent.event_type == "financial.eligibility.recheck_requested",
        OutboxEvent.aggregate_id == str(order.app_user_id),
    ).all()
    assert len(events) == 2
    assert {event.scope_ref for event in events} == {f"tenant:{sample_tenant.id}"}
    assert {event.payload["source_type"] for event in events} == {"payment_refund"}
    assert len({event.idempotency_key for event in events}) == 2


def test_refund_overage_and_provider_timeout_fail_closed(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    _, _, _, order = _invoice_fixture(
        db_session, sample_tenant, sample_charge_point, sample_evse
    )
    provider = RefundProvider(timeout=True)
    service = PaymentRefundService(
        reconciliation=PaymentReconciliationService(provider_registry=Registry(provider))
    )
    with pytest.raises(RefundRetryable):
        service.refund_payment_order(
            db_session,
            payment_order_id=order.id,
            amount=Decimal("1000.00"),
            idempotency_key="timeout-1",
        )
    assert db_session.get(PaymentOrder, order.id).order_metadata["refund_summary"]["operations"]
    provider.timeout = False
    service.refund_payment_order(
        db_session,
        payment_order_id=order.id,
        amount=Decimal("1000.00"),
        idempotency_key="timeout-2",
    )
    with pytest.raises(RefundRequestInvalid):
        service.refund_payment_order(
            db_session,
            payment_order_id=order.id,
            amount=Decimal("1800.00"),
            idempotency_key="over-1",
        )


def test_wallet_top_up_refund_never_creates_negative_balance(
    db_session, sample_tenant
):
    user = AppUser(
        email="be7-topup@example.test",
        password_hash="test",
        balance=Decimal("100.00"),
    )
    db_session.add(user)
    db_session.flush()
    order = PaymentOrder(
        app_user_id=user.id,
        type="top_up",
        amount=Decimal("500.00"),
        currency="COP",
        payment_provider="mercadopago",
        mercadopago_payment_id="mp-topup-be7",
        status="approved",
        idempotency_key="topup-be7",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        order_metadata={
            "payment_purpose": "wallet_top_up",
            "operator_tenant_id": str(sample_tenant.id),
            "merchant": _merchant(),
        },
    )
    db_session.add(order)
    db_session.commit()
    provider = RefundProvider()
    service = PaymentRefundService(
        reconciliation=PaymentReconciliationService(provider_registry=Registry(provider))
    )
    with pytest.raises(RefundManualReviewRequired):
        service.refund_payment_order(
            db_session,
            payment_order_id=order.id,
            amount=Decimal("200.00"),
            idempotency_key="topup-refund-1",
        )
    db_session.refresh(user)
    assert user.balance == Decimal("100.00")
    assert provider.create_calls == 0
