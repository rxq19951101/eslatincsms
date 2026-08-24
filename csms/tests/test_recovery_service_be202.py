"""BE-202 typed recovery and allocation tests."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.database.models import (
    AppUser,
    ChargingSession,
    Invoice,
    PaymentAllocation,
    PaymentOrder,
    PricingSnapshot,
    RecoveryAttempt,
    Tariff,
)
from app.api.v1.app.payment_checkout import _valid_recovery_attempt_id
from app.services.payment_providers.merchant_context import (
    MerchantMode,
    MerchantContext,
    PaymentPurpose,
)
from app.services.payment_providers.base import PaymentProviderError, ProviderCreateResult
from app.services.payment_reconciliation import PaymentReconciliationService
from app.services.recovery_service import (
    IdempotencyConflict,
    RecoveryService,
)


def _invoice(db_session, sample_tenant, sample_commercial_charge_point, sample_evse, *, balance):
    user = AppUser(
        email=f"be202-{uuid4().hex}@example.test",
        password_hash="test-hash",
        email_verified=True,
        balance=balance,
    )
    db_session.add(user)
    db_session.flush()
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_commercial_charge_point.id,
        transaction_id=int(uuid4().int % 1_000_000_000),
        id_tag=f"BE202-{uuid4().hex[:12]}",
        app_user_id=user.id,
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        meter_start=0,
        meter_stop=1000,
        status="completed",
        payment_status="unpaid",
    )
    db_session.add(session)
    db_session.flush()
    tariff = Tariff(
        tenant_id=sample_tenant.id,
        name="BE-202 test tariff",
        base_price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        valid_from=datetime.now(timezone.utc),
        is_active=True,
    )
    db_session.add(tariff)
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
        tenant_id=sample_tenant.id,
        session_id=session.id,
        pricing_snapshot_id=snapshot.id,
        energy_kwh=Decimal("1.000"),
        duration_minutes=Decimal("10.00"),
        energy_cost=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("2700.00"),
        status="pending",
    )
    db_session.add(invoice)
    db_session.commit()
    return user, session, invoice


def _merchant(*, operator_tenant_id, payment_purpose):
    return {
        "merchant_mode": MerchantMode.PLATFORM.value,
        "merchant_account_ref": "platform:eslatin",
        "provider": "mercadopago",
        "marketplace_fee_policy": None,
    }


def test_wallet_recovery_is_atomic_and_idempotent(
    db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    user, session, invoice = _invoice(
        db_session,
        sample_tenant,
        sample_commercial_charge_point,
        sample_evse,
        balance=Decimal("5000.00"),
    )
    service = RecoveryService()
    first = service.prepare(
        db_session,
        app_user_id=user.id,
        invoice_id=invoice.id,
        method="wallet",
        saved_payment_method_id=None,
        idempotency_key="be202-wallet-1",
    )
    settled = service.settle_wallet(db_session, attempt_id=first.attempt.id)
    assert settled.status == "allocated"

    db_session.refresh(user)
    assert Decimal(str(user.balance)) == Decimal("2300.00")
    allocation = db_session.query(PaymentAllocation).filter_by(invoice_id=invoice.id).one()
    assert allocation.status == "committed"
    assert allocation.amount == Decimal("2700.00")
    assert db_session.query(Invoice).get(invoice.id).status == "pending"
    assert db_session.query(ChargingSession).get(session.id).payment_status == "unpaid"

    replay = service.prepare(
        db_session,
        app_user_id=user.id,
        invoice_id=invoice.id,
        method="wallet",
        saved_payment_method_id=None,
        idempotency_key="be202-wallet-1",
    )
    assert replay.reused is True
    assert replay.attempt.id == first.attempt.id
    service.settle_wallet(db_session, attempt_id=replay.attempt.id)
    db_session.refresh(user)
    assert Decimal(str(user.balance)) == Decimal("2300.00")
    assert db_session.query(PaymentAllocation).filter_by(invoice_id=invoice.id).count() == 1


def test_recovery_idempotency_fingerprint_conflict_and_insufficient_wallet(
    db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    user, _, invoice = _invoice(
        db_session,
        sample_tenant,
        sample_commercial_charge_point,
        sample_evse,
        balance=Decimal("10.00"),
    )
    service = RecoveryService()
    prepared = service.prepare(
        db_session,
        app_user_id=user.id,
        invoice_id=invoice.id,
        method="wallet",
        saved_payment_method_id=None,
        idempotency_key="be202-conflict-1",
    )
    declined = service.settle_wallet(db_session, attempt_id=prepared.attempt.id)
    assert declined.status == "declined"
    assert declined.reason_code == "insufficient_wallet_balance"
    assert db_session.query(PaymentAllocation).filter_by(invoice_id=invoice.id).count() == 0

    with pytest.raises(IdempotencyConflict):
        service.prepare(
            db_session,
            app_user_id=user.id,
            invoice_id=invoice.id,
            method="new_card",
            saved_payment_method_id=None,
            idempotency_key="be202-conflict-1",
        )


def test_card_recovery_provider_approval_has_one_typed_winner(
    db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    user, _, invoice = _invoice(
        db_session,
        sample_tenant,
        sample_commercial_charge_point,
        sample_evse,
        balance=Decimal("0.00"),
    )
    with patch(
        "app.services.recovery_service.RecoveryService._merchant",
        side_effect=lambda tenant_id: _merchant(operator_tenant_id=tenant_id, payment_purpose=None),
    ):
        service = RecoveryService()
        first = service.prepare(
            db_session,
            app_user_id=user.id,
            invoice_id=invoice.id,
            method="new_card",
            saved_payment_method_id=None,
            idempotency_key="be202-card-1",
        )
        second = service.prepare(
            db_session,
            app_user_id=user.id,
            invoice_id=invoice.id,
            method="new_card",
            saved_payment_method_id=None,
            idempotency_key="be202-card-2",
        )
        first_order = db_session.query(PaymentOrder).filter(PaymentOrder.id == first.payment_order.id).one()
        assert service.apply_card_result(
            db_session,
            attempt_id=first.attempt.id,
            payment_order_id=first_order.id,
            provider_status="approved",
            provider_payment_ref="mp-1",
            provider_amount=Decimal("2700.00"),
            provider_currency="COP",
        ) is False
        db_session.commit()
        assert db_session.query(PaymentAllocation).filter_by(status="committed").count() == 1
        assert db_session.query(RecoveryAttempt).get(first.attempt.id).status == "allocated"

        second_order = db_session.query(PaymentOrder).filter(PaymentOrder.id == second.payment_order.id).one()
        assert service.apply_card_result(
            db_session,
            attempt_id=second.attempt.id,
            payment_order_id=second_order.id,
            provider_status="approved",
            provider_payment_ref="mp-2",
            provider_amount=Decimal("2700.00"),
            provider_currency="COP",
        ) is True
        db_session.commit()
        duplicate = db_session.query(RecoveryAttempt).get(second.attempt.id)
        assert duplicate.status == "duplicate_approved"
        assert duplicate.reason_code == "duplicate_approval"
        assert db_session.query(PaymentAllocation).filter_by(invoice_id=invoice.id).count() == 1


def test_card_provider_timeout_is_unknown_and_never_allocated(
    db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    user, _, invoice = _invoice(
        db_session,
        sample_tenant,
        sample_commercial_charge_point,
        sample_evse,
        balance=Decimal("0.00"),
    )
    with patch(
        "app.services.recovery_service.RecoveryService._merchant",
        side_effect=lambda tenant_id: _merchant(operator_tenant_id=tenant_id, payment_purpose=None),
    ):
        service = RecoveryService()
        prepared = service.prepare(
            db_session,
            app_user_id=user.id,
            invoice_id=invoice.id,
            method="new_card",
            saved_payment_method_id=None,
            idempotency_key="be202-unknown-1",
        )
        service.mark_unknown(
            db_session,
            attempt_id=prepared.attempt.id,
            reason="provider_timeout_or_unknown",
        )
        db_session.commit()
    attempt = db_session.get(RecoveryAttempt, prepared.attempt.id)
    assert attempt.status == "unknown"
    assert db_session.query(PaymentAllocation).filter_by(invoice_id=invoice.id).count() == 0


def test_checkout_recovery_id_is_additive_only_for_owned_unpaid_charge(
    db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    user, _, invoice = _invoice(
        db_session,
        sample_tenant,
        sample_commercial_charge_point,
        sample_evse,
        balance=Decimal("5000.00"),
    )
    attempt = RecoveryService().prepare(
        db_session,
        app_user_id=user.id,
        invoice_id=invoice.id,
        method="wallet",
        saved_payment_method_id=None,
        idempotency_key="be202-checkout-projection-1",
    ).attempt

    assert (
        _valid_recovery_attempt_id(
            db_session,
            app_user_id=user.id,
            purpose=PaymentPurpose.UNPAID_CHARGE,
            recovery_attempt_id=str(attempt.id),
        )
        == str(attempt.id)
    )
    assert (
        _valid_recovery_attempt_id(
            db_session,
            app_user_id=user.id,
            purpose=PaymentPurpose.WALLET_TOP_UP,
            recovery_attempt_id=str(attempt.id),
        )
        is None
    )


def test_recovery_provider_call_has_no_active_database_transaction(
    db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    class BoundaryCheckoutStore:
        def consume_card_token(self, checkout_session_id):
            return "one-time-card-token"

        def get(self, checkout_session_id):
            raise RuntimeError("projection not configured")

    class BoundaryProvider:
        provider_code = "mercadopago"

        def __init__(self):
            self.active_transaction_at_call = None
            self.commands = []

        def create_payment(self, command, *, merchant_context):
            self.active_transaction_at_call = db_session.in_transaction()
            self.commands.append(command)
            return ProviderCreateResult(status="processing")

    user, session, invoice = _invoice(
        db_session,
        sample_tenant,
        sample_commercial_charge_point,
        sample_evse,
        balance=Decimal("0.00"),
    )
    with patch(
        "app.services.recovery_service.RecoveryService._merchant",
        side_effect=lambda tenant_id: {
            "merchant_mode": MerchantMode.PLATFORM.value,
            "merchant_account_ref": "platform:eslatin",
            "provider": "mercadopago",
            "marketplace_fee_policy": None,
        },
    ):
        prepared = RecoveryService().prepare(
            db_session,
            app_user_id=user.id,
            invoice_id=invoice.id,
            method="new_card",
            saved_payment_method_id=None,
            idempotency_key="be202-provider-boundary-1",
        )

    payment_order = db_session.get(PaymentOrder, prepared.payment_order.id)
    payment_order.order_metadata = {
        **dict(payment_order.order_metadata or {}),
        "checkout_session_id": "be202-provider-boundary-checkout",
        "provider_hints": {
            "provider_payment_method_id": "visa",
            "provider_payment_type_id": "credit_card",
        },
    }
    db_session.commit()

    provider = BoundaryProvider()
    service = PaymentReconciliationService(
        provider_registry=type("Registry", (), {"get": lambda self, _: provider})(),
        checkout_store=BoundaryCheckoutStore(),
    )
    result = service.start_payment_order(
        db_session,
        payment_order_id=payment_order.id,
    )

    assert provider.active_transaction_at_call is False
    assert provider.commands[0].idempotency_key == f"payment-order:{payment_order.id}"
    assert result.api_status == "processing"
    persisted_order = db_session.get(PaymentOrder, payment_order.id)
    assert persisted_order.status == "processing"
    assert persisted_order.order_metadata["provider_operation_key"] == (
        f"payment-order:{payment_order.id}"
    )


def test_retryable_provider_error_preserves_unknown_recovery_and_processing_order(
    db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    class RetryableCheckoutStore:
        def consume_card_token(self, checkout_session_id):
            return "one-time-card-token"

        def get(self, checkout_session_id):
            raise RuntimeError("projection not configured")

    class RetryableProvider:
        provider_code = "mercadopago"

        def __init__(self):
            self.calls = 0
            self.commands = []

        def create_payment(self, command, *, merchant_context):
            self.calls += 1
            self.commands.append(command)
            raise PaymentProviderError("provider_timeout", retryable=True)

    user, session, invoice = _invoice(
        db_session,
        sample_tenant,
        sample_commercial_charge_point,
        sample_evse,
        balance=Decimal("0.00"),
    )
    with patch(
        "app.services.recovery_service.RecoveryService._merchant",
        side_effect=lambda tenant_id: {
            "merchant_mode": MerchantMode.PLATFORM.value,
            "merchant_account_ref": "platform:eslatin",
            "provider": "mercadopago",
            "marketplace_fee_policy": None,
        },
    ):
        prepared = RecoveryService().prepare(
            db_session,
            app_user_id=user.id,
            invoice_id=invoice.id,
            method="new_card",
            saved_payment_method_id=None,
            idempotency_key="be202-retryable-provider-error-1",
        )

    payment_order = db_session.get(PaymentOrder, prepared.payment_order.id)
    payment_order.order_metadata = {
        **dict(payment_order.order_metadata or {}),
        "checkout_session_id": "be202-retryable-provider-error-checkout",
        "provider_hints": {
            "provider_payment_method_id": "visa",
            "provider_payment_type_id": "credit_card",
        },
    }
    db_session.commit()

    provider = RetryableProvider()
    service = PaymentReconciliationService(
        provider_registry=type("Registry", (), {"get": lambda self, _: provider})(),
        checkout_store=RetryableCheckoutStore(),
    )
    first = service.start_payment_order(
        db_session,
        payment_order_id=payment_order.id,
    )

    persisted_attempt = db_session.get(RecoveryAttempt, prepared.attempt.id)
    persisted_order = db_session.get(PaymentOrder, payment_order.id)
    assert first.api_status == "processing"
    assert persisted_attempt.status == "unknown"
    assert persisted_order.status == "processing"
    assert persisted_order.order_metadata["provider_operation_key"] == (
        f"payment-order:{payment_order.id}"
    )
    assert persisted_order.order_metadata["reconciliation_error"] == (
        "provider_timeout_or_unknown"
    )
    assert db_session.query(PaymentAllocation).filter_by(invoice_id=invoice.id).count() == 0

    second = service.start_payment_order(
        db_session,
        payment_order_id=payment_order.id,
    )
    assert second.api_status == "processing"
    assert second.order_status == "processing"
    assert provider.calls == 1
    assert db_session.query(PaymentAllocation).filter_by(invoice_id=invoice.id).count() == 0


def test_wallet_top_up_provider_call_has_no_active_database_transaction(db_session, sample_tenant):
    class BoundaryCheckoutStore:
        def consume_card_token(self, checkout_session_id):
            return "one-time-card-token"

        def get(self, checkout_session_id):
            raise RuntimeError("projection not configured")

    class BoundaryProvider:
        provider_code = "mercadopago"

        def __init__(self):
            self.active_transaction_at_call = None

        def create_payment(self, command, *, merchant_context):
            self.active_transaction_at_call = db_session.in_transaction()
            return ProviderCreateResult(status="processing")

    user = AppUser(
        email=f"be202-topup-{uuid4().hex}@example.test",
        password_hash="test-hash",
        balance=Decimal("0.00"),
    )
    db_session.add(user)
    db_session.flush()
    payment_order = PaymentOrder(
        app_user_id=user.id,
        type="top_up",
        amount=Decimal("50000.00"),
        currency="COP",
        payment_provider="mercadopago",
        idempotency_key=f"be202-topup-boundary-{uuid4()}",
        status="created",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        order_metadata={
            "payment_purpose": PaymentPurpose.WALLET_TOP_UP.value,
            "checkout_session_id": "be202-topup-boundary-checkout",
            "operator_tenant_id": str(sample_tenant.id),
            "merchant": {
                "merchant_mode": MerchantMode.PLATFORM.value,
                "merchant_account_ref": "platform:eslatin",
                "provider": "mercadopago",
                "marketplace_fee_policy": None,
            },
            "provider_hints": {
                "provider_payment_method_id": "visa",
                "provider_payment_type_id": "credit_card",
            },
        },
    )
    db_session.add(payment_order)
    db_session.commit()

    provider = BoundaryProvider()
    service = PaymentReconciliationService(
        provider_registry=type("Registry", (), {"get": lambda self, _: provider})(),
        checkout_store=BoundaryCheckoutStore(),
    )
    result = service.start_payment_order(db_session, payment_order_id=payment_order.id)

    assert provider.active_transaction_at_call is False
    assert result.api_status == "processing"
    persisted_order = db_session.get(PaymentOrder, payment_order.id)
    assert persisted_order.status == "processing"
    assert persisted_order.order_metadata["provider_operation_key"] == (
        f"payment-order:{payment_order.id}"
    )
