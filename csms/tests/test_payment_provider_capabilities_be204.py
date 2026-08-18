"""BE-204 provider-neutral capability boundary tests.

The fake below is deliberately not registered in the application registry: it
is a test double, not a second production payment rail.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.payment_providers.base import (
    DisputeCapabilityFact,
    FundsCapabilityFact,
    PaymentCapabilityCommand,
    PaymentCapabilityResult,
    ProviderCapabilityError,
    ProviderNextAction,
    RefundCapabilityCommand,
    RefundCapabilityFacts,
    RefundCapabilityResult,
)
from app.services.payment_providers.mercadopago_provider import MercadoPagoProvider
from app.services.payment_reconciliation import PaymentReconciliationService
from app.api.v1.app.transactions import (
    P002_MEDIA_TYPE,
    _decode_cursor,
    _encode_cursor,
    _transaction_contract,
)


class FakeCapabilityProvider:
    provider_code = "fake-test-only"

    def __init__(self, status: str):
        self.status = status
        self.created = []
        self.refunded = Decimal("0.00")

    def create_recovery_payment(self, command, *, merchant_context, idempotency_key):
        self.created.append((command, idempotency_key))
        return PaymentCapabilityResult(
            status=self.status,
            provider_ref="opaque-payment-ref",
            merchant_ref="opaque-merchant-ref",
            amount=command.amount,
            currency=command.currency,
            next_action=(
                ProviderNextAction(type="open_url", url="https://pay.example.test/3ds")
                if self.status == "action_required"
                else None
            ),
        )

    def query_payment(self, provider_ref, *, merchant_context):
        return PaymentCapabilityResult(
            status=self.status,
            provider_ref=provider_ref,
            amount=Decimal("2700.00"),
            currency="COP",
        )

    def create_refund_capability(self, command, *, merchant_context, idempotency_key):
        self.refunded += command.amount
        return RefundCapabilityResult(
            status="refunded",
            refund_ref="opaque-refund-ref",
            amount=command.amount,
        )

    def query_refund_capability(self, provider_ref, *, merchant_context):
        return RefundCapabilityFacts(
            refunded_amount=self.refunded,
            refund_refs=("opaque-refund-ref",) if self.refunded else (),
        )

    def normalize_dispute_fact(self, payload, *, merchant_context):
        return DisputeCapabilityFact(
            payment_ref=str(payload["payment_ref"]),
            status=payload.get("status", "unknown"),
            dispute_ref=payload.get("dispute_ref"),
        )

    def normalize_funds_fact(self, payload, *, merchant_context):
        return FundsCapabilityFact(
            payment_ref=str(payload["payment_ref"]),
            status=payload.get("status", "unknown"),
            funds_ref=payload.get("funds_ref"),
        )


@pytest.mark.parametrize(
    "status",
    ["processing", "action_required", "provider_approved", "declined", "unknown"],
)
def test_fake_provider_exercises_canonical_payment_states(status):
    provider = FakeCapabilityProvider(status)
    result = provider.create_recovery_payment(
        PaymentCapabilityCommand(
            amount=Decimal("2700.00"),
            currency="COP",
            purpose="unpaid_charge",
            merchant_account_ref="platform:eslatin",
            references={"invoice_id": "opaque-invoice"},
            instrument_token="one-time-hosted-token",
        ),
        merchant_context=SimpleNamespace(merchant_account_ref="platform:eslatin"),
        idempotency_key="operation-1",
    )

    assert result.status == status
    assert result.provider_ref == "opaque-payment-ref"
    assert not hasattr(result, "raw_response")
    assert not hasattr(result, "provider_payment_id")


def test_fake_provider_covers_late_reversal_refund_chargeback_and_funds():
    provider = FakeCapabilityProvider("provider_approved")
    context = SimpleNamespace(merchant_account_ref="platform:eslatin")

    reversal = provider.query_payment("opaque-payment-ref", merchant_context=context)
    assert reversal.status == "provider_approved"
    late_reversal = PaymentCapabilityResult(
        status="unknown", provider_ref=reversal.provider_ref, amount=reversal.amount, currency=reversal.currency
    )
    assert late_reversal.status == "unknown"

    refund = provider.create_refund_capability(
        RefundCapabilityCommand(
            payment_ref="opaque-payment-ref",
            amount=Decimal("2700.00"),
            currency="COP",
            merchant_account_ref="platform:eslatin",
        ),
        merchant_context=context,
        idempotency_key="refund-1",
    )
    assert refund.status == "refunded"
    assert provider.query_refund_capability("opaque-payment-ref", merchant_context=context).refunded_amount == Decimal("2700.00")

    dispute = provider.normalize_dispute_fact(
        {"payment_ref": "opaque-payment-ref", "status": "disputed", "dispute_ref": "opaque-dispute"},
        merchant_context=context,
    )
    funds = provider.normalize_funds_fact(
        {"payment_ref": "opaque-payment-ref", "status": "held", "funds_ref": "opaque-funds"},
        merchant_context=context,
    )
    assert dispute.status == "disputed"
    assert funds.status == "held"


def test_core_adapter_bridge_accepts_canonical_provider_without_provider_fields():
    service = PaymentReconciliationService(provider_registry=SimpleNamespace(get=lambda _: FakeCapabilityProvider("unknown")))
    provider = FakeCapabilityProvider("action_required")
    result = service._create_payment(
        provider,
        SimpleNamespace(
            metadata={"payment_purpose": "unpaid_charge"},
            amount=Decimal("2700.00"),
            currency="COP",
            order_type="charging",
            email="user@example.test",
            token="opaque-token",
            payment_method_id="card_hint",
        ),
        merchant_context=SimpleNamespace(merchant_account_ref="platform:eslatin"),
        operation_key="operation-1",
    )
    assert result.status == "action_required"
    assert result.next_action_url == "https://pay.example.test/3ds"
    assert provider.created[0][1] == "operation-1"


def test_mercado_pago_adapter_normalizes_sdk_result_without_leaking_raw_response(monkeypatch):
    provider = MercadoPagoProvider()
    monkeypatch.setattr(
        provider,
        "create_payment",
        lambda command, *, merchant_context: SimpleNamespace(
            status="approved",
            provider_order_ref="opaque-merchant-ref",
            provider_payment_id="opaque-payment-ref",
            redirect_url=None,
            next_action_url=None,
        ),
    )
    result = provider.create_recovery_payment(
        PaymentCapabilityCommand(
            amount=Decimal("2700.00"),
            currency="COP",
            purpose="unpaid_charge",
            merchant_account_ref="platform:eslatin",
            references={"payer_email": "user@example.test"},
            instrument_token="opaque-token",
            payment_method_hint="visa",
        ),
        merchant_context=SimpleNamespace(provider="mercadopago", merchant_account_ref="platform:eslatin"),
        idempotency_key="operation-1",
    )
    assert result.status == "provider_approved"
    assert result.provider_ref == "opaque-payment-ref"
    assert not hasattr(result, "raw_response")


def test_provider_capability_error_has_only_canonical_reason():
    error = ProviderCapabilityError("provider_unavailable", retryable=True)
    assert error.reason == "provider_unavailable"
    assert error.retryable is True
    assert "mercado" not in str(error).lower()


def test_transactions_use_only_frozen_p002_accept_negotiation_and_opaque_cursor():
    assert _transaction_contract(None) == "p001"
    assert _transaction_contract(P002_MEDIA_TYPE) == "p002"
    with pytest.raises(HTTPException) as unsupported:
        _transaction_contract("application/vnd.eslatin.pay-mp-002.v2+json")
    assert unsupported.value.status_code == 406
    with pytest.raises(HTTPException) as invalid:
        _decode_cursor("not-a-cursor", user_id=SimpleNamespace(__str__=lambda _: "user"), status=None)
    assert invalid.value.status_code == 409


def test_transactions_cursor_round_trip_is_tenant_user_scoped():
    from datetime import datetime, timezone
    from uuid import UUID

    user_id = UUID("00000000-0000-0000-0000-000000000001")
    session_id = UUID("00000000-0000-0000-0000-000000000002")
    cursor = _encode_cursor(
        datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
        session_id,
        user_id=user_id,
        status="completed",
    )
    start_time, decoded_session_id = _decode_cursor(
        cursor,
        user_id=user_id,
        status="completed",
    )
    assert decoded_session_id == session_id
    assert start_time.isoformat() == "2026-08-13T12:00:00+00:00"
