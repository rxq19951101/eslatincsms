"""PAY-MP-001 BE-1 merchant selection and credential-boundary tests."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import hmac
import json
import logging
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.services import mercadopago_service as service_module
from app.services.payment_providers.base import (
    CreatePaymentCommand,
    PaymentProviderError,
)
from app.services.payment_providers.credential_resolver import (
    EnvironmentCredentialResolver,
    ProviderCredentialError,
    ProviderCredentials,
)
from app.services.payment_providers.mercadopago_provider import MercadoPagoProvider
from app.services.payment_providers.merchant_context import (
    MerchantContext,
    MerchantContextError,
    MerchantMode,
    PaymentPurpose,
    PlatformMerchantAccountResolver,
)


def _payment_settings(**overrides) -> Settings:
    values = {
        "mercadopago_environment": "sandbox",
        "mercadopago_access_token": "TEST-123456-abcdefghijklmnopqrstuvwxyz",
        "mercadopago_public_key": "TEST-public-key-value",
        "mercadopago_webhook_secret": "webhook-secret-value",
    }
    values.update(overrides)
    return Settings(**values)


def test_platform_resolver_requires_trusted_tenant_for_charging() -> None:
    resolver = PlatformMerchantAccountResolver()

    with pytest.raises(MerchantContextError):
        resolver.resolve(
            operator_tenant_id=None,
            payment_purpose=PaymentPurpose.CHARGING_DIRECT,
        )

    context = resolver.resolve(
        operator_tenant_id=uuid4(),
        payment_purpose=PaymentPurpose.CHARGING_DIRECT,
    )
    assert context.merchant_mode is MerchantMode.PLATFORM
    assert context.merchant_account_ref == "platform:eslatin"
    assert context.provider == "mercadopago"


def test_context_snapshot_and_repr_never_expose_credential_handle() -> None:
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )

    assert "credential_handle" not in context.safe_snapshot()
    assert context.credential_handle not in repr(context)


def test_environment_credential_resolver_fails_closed() -> None:
    context = MerchantContext(
        merchant_mode=MerchantMode.PLATFORM,
        merchant_account_ref="platform:eslatin",
        provider="mercadopago",
        credential_handle="unknown:handle",
    )
    resolver = EnvironmentCredentialResolver(_payment_settings())
    with pytest.raises(ProviderCredentialError, match="Unknown provider credential handle"):
        resolver.resolve(context)

    valid_context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )
    missing = EnvironmentCredentialResolver(
        _payment_settings(mercadopago_access_token="")
    )
    with pytest.raises(ProviderCredentialError, match="not configured"):
        missing.resolve(valid_context)


def test_provider_credentials_repr_hides_every_secret() -> None:
    credentials = ProviderCredentials(
        environment="sandbox",
        access_token="access-token-secret",
        public_key="public-key-secret",
        webhook_secret="webhook-secret",
    )
    rendered = repr(credentials)
    assert "access-token-secret" not in rendered
    assert "public-key-secret" not in rendered
    assert "webhook-secret" not in rendered


def test_mercadopago_webhook_signature_uses_constant_time_comparison(monkeypatch) -> None:
    service = object.__new__(service_module.MercadoPagoService)
    service._webhook_secret = "webhook-secret"
    data_id = "payment-123"
    request_id = "request-123"
    timestamp = "1700000000"
    manifest = f"id:{data_id};request-id:{request_id};ts:{timestamp};"
    expected = hmac.new(
        service._webhook_secret.encode(), manifest.encode(), hashlib.sha256
    ).hexdigest()

    calls: list[tuple[str, str]] = []
    original = hmac.compare_digest

    def compare_digest(left: str, right: str) -> bool:
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr(service_module.hmac, "compare_digest", compare_digest)

    assert service.verify_webhook_signature(
        f"ts={timestamp},v1={expected}", request_id, data_id
    ) is True
    assert calls == [(expected, expected)]


def test_mercadopago_refund_query_converts_non_json_sdk_response_to_safe_failure(
    monkeypatch, caplog
) -> None:
    class BrokenRefundClient:
        def list_all(self, payment_id: str):
            raise json.JSONDecodeError("Expecting value", "", 0)

    class BrokenSDK:
        def __init__(self, token: str) -> None:
            self._refund = BrokenRefundClient()

        def refund(self):
            return self._refund

    monkeypatch.setattr(service_module.mercadopago, "SDK", BrokenSDK)
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )
    service = service_module.get_mercadopago_service(
        merchant_context=context,
        credential_resolver=EnvironmentCredentialResolver(_payment_settings()),
    )

    with caplog.at_level(logging.ERROR, logger="mercadopago_service"):
        result = service.get_refund_facts("123456")

    assert result == {
        "success": False,
        "error": "mercadopago_refund_query_failed",
        "retryable": True,
    }
    assert "JSONDecodeError" in caplog.text
    assert "Expecting value" not in caplog.text


def test_mercadopago_refund_query_rejects_non_collection_success_body(
    monkeypatch,
) -> None:
    class InvalidRefundClient:
        def list_all(self, payment_id: str):
            return {"status": 200, "response": "<html>gateway error</html>"}

    class InvalidResponseSDK:
        def __init__(self, token: str) -> None:
            self._refund = InvalidRefundClient()

        def refund(self):
            return self._refund

    monkeypatch.setattr(service_module.mercadopago, "SDK", InvalidResponseSDK)
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )
    service = service_module.get_mercadopago_service(
        merchant_context=context,
        credential_resolver=EnvironmentCredentialResolver(_payment_settings()),
    )

    result = service.get_refund_facts("123456")

    assert result == {
        "success": False,
        "error": "mercadopago_refund_response_invalid",
        "retryable": False,
    }


def test_provider_preserves_non_retryable_refund_response_error() -> None:
    class InvalidRefundFactsService:
        def get_refund_facts(self, payment_id: str):
            return {
                "success": False,
                "error": "mercadopago_refund_response_invalid",
                "retryable": False,
            }

    provider = MercadoPagoProvider()
    provider._service = lambda merchant_context: InvalidRefundFactsService()
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )

    with pytest.raises(PaymentProviderError) as error:
        provider.get_refund_facts("123456", merchant_context=context)

    assert error.value.code == "mercadopago_refund_response_invalid"
    assert error.value.retryable is False


def test_mercadopago_service_is_merchant_scoped_and_not_cached(monkeypatch) -> None:
    sdk_tokens: list[str] = []

    class FakeSDK:
        def __init__(self, token: str) -> None:
            sdk_tokens.append(token)

    monkeypatch.setattr(service_module.mercadopago, "SDK", FakeSDK)
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )
    credentials = EnvironmentCredentialResolver(_payment_settings())

    first = service_module.get_mercadopago_service(
        merchant_context=context,
        credential_resolver=credentials,
    )
    second = service_module.get_mercadopago_service(
        merchant_context=context,
        credential_resolver=credentials,
    )

    assert first is not second
    assert first.merchant_account_ref == "platform:eslatin"
    assert not hasattr(first, "access_token")
    assert sdk_tokens == [
        "TEST-123456-abcdefghijklmnopqrstuvwxyz",
        "TEST-123456-abcdefghijklmnopqrstuvwxyz",
    ]


def test_provider_rejects_context_for_another_provider() -> None:
    provider = MercadoPagoProvider()
    command = CreatePaymentCommand(
        provider="mercadopago",
        order_type="top_up",
        amount=Decimal("1000.00"),
        currency="COP",
        email="payer@example.com",
        token="card-token",
        idempotency_key="payment-idempotency-key",
    )
    wrong_context = MerchantContext(
        merchant_mode=MerchantMode.PLATFORM,
        merchant_account_ref="platform:eslatin",
        provider="wompi",
        credential_handle="env:wompi:platform",
    )

    with pytest.raises(PaymentProviderError, match="merchant_provider_mismatch"):
        provider.create_payment(command, merchant_context=wrong_context)


def test_provider_failure_does_not_log_or_return_raw_error(
    monkeypatch,
    caplog,
) -> None:
    provider_secret = "ProviderRawSecretPrefix_8mQ4vT2pL7xN"

    class FailedPaymentClient:
        def create(self, payment_data, request_options):
            return {
                "status": 400,
                "response": {
                    "message": provider_secret,
                    "status_detail": "cc_rejected_bad_filled_card_number",
                    "cause": [{"code": "bad_request", "description": "sandbox rejection"}],
                },
            }

    class FailedSDK:
        def __init__(self, token: str) -> None:
            self._payment = FailedPaymentClient()

        def payment(self):
            return self._payment

    monkeypatch.setattr(service_module.mercadopago, "SDK", FailedSDK)
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )
    service = service_module.get_mercadopago_service(
        merchant_context=context,
        credential_resolver=EnvironmentCredentialResolver(_payment_settings()),
    )

    with caplog.at_level(logging.INFO, logger="mercadopago_service"):
        result = service.create_payment(
            token="card-token",
            amount=Decimal("1000.00"),
            email="payer@example.com",
            description="Wallet top-up",
            idempotency_key="payment-idempotency-key",
        )

    assert result["error"] == "mercadopago_payment_failed"
    assert provider_secret not in caplog.text
    assert "cc_rejected_bad_filled_card_number" in caplog.text
    assert "bad_request" in caplog.text
    assert "sandbox rejection" in caplog.text
    assert "card-token" not in caplog.text
    assert "request_shape" in caplog.text
    assert "response_fields" in caplog.text


def test_provider_generic_message_is_logged_but_secret_like_message_is_redacted(
    monkeypatch,
    caplog,
) -> None:
    class FailedPaymentClient:
        def create(self, payment_data, request_options):
            return {
                "status": 500,
                "response": {
                    "message": "Internal server error from sandbox provider",
                },
            }

    class FailedSDK:
        def __init__(self, token: str) -> None:
            self._payment = FailedPaymentClient()

        def payment(self):
            return self._payment

    monkeypatch.setattr(service_module.mercadopago, "SDK", FailedSDK)
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )
    service = service_module.get_mercadopago_service(
        merchant_context=context,
        credential_resolver=EnvironmentCredentialResolver(_payment_settings()),
    )

    with caplog.at_level(logging.INFO, logger="mercadopago_service"):
        service.create_payment(
            token="card-token",
            amount=Decimal("48.60"),
            email="payer@example.com",
            description="Wallet top-up",
            idempotency_key="payment-idempotency-key-500",
        )

    assert "Internal server error from sandbox provider" in caplog.text
    assert "card-token" not in caplog.text


def test_mercadopago_service_serializes_decimal_amount_at_provider_boundary(
    monkeypatch,
):
    captured = []

    class SuccessfulPaymentClient:
        def create(self, payment_data, request_options):
            json.dumps(payment_data)
            captured.append(payment_data)
            return {
                "status": 201,
                "response": {
                    "id": "sandbox-payment-1",
                    "status": "approved",
                },
            }

    class SuccessfulSDK:
        def __init__(self, token: str) -> None:
            self._payment = SuccessfulPaymentClient()

        def payment(self):
            return self._payment

    monkeypatch.setattr(service_module.mercadopago, "SDK", SuccessfulSDK)
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )
    service = service_module.get_mercadopago_service(
        merchant_context=context,
        credential_resolver=EnvironmentCredentialResolver(_payment_settings()),
    )

    result = service.create_payment(
        token="card-token",
        amount=Decimal("1000.00"),
        email="payer@example.com",
        description="Wallet top-up",
        idempotency_key="payment-idempotency-key",
    )

    assert result["success"] is True
    assert captured[0]["transaction_amount"] == 1000.0
    assert isinstance(captured[0]["transaction_amount"], float)


def test_mercadopago_service_serializes_fractional_amount_as_json_number(
    monkeypatch,
):
    captured = []

    class SuccessfulPaymentClient:
        def create(self, payment_data, request_options):
            json.dumps(payment_data)
            captured.append(payment_data)
            return {
                "status": 201,
                "response": {
                    "id": "sandbox-payment-fractional",
                    "status": "approved",
                },
            }

    class SuccessfulSDK:
        def __init__(self, token: str) -> None:
            self._payment = SuccessfulPaymentClient()

        def payment(self):
            return self._payment

    monkeypatch.setattr(service_module.mercadopago, "SDK", SuccessfulSDK)
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )
    service = service_module.get_mercadopago_service(
        merchant_context=context,
        credential_resolver=EnvironmentCredentialResolver(_payment_settings()),
    )

    result = service.create_payment(
        token="card-token",
        amount=Decimal("48.60"),
        email="payer@example.com",
        description="Charging settlement",
        idempotency_key="payment-idempotency-key-fractional",
    )

    assert result["success"] is True
    assert captured[0]["transaction_amount"] == 48.6
    assert isinstance(captured[0]["transaction_amount"], float)


def test_mercadopago_service_preserves_two_decimal_cop_amounts(
    monkeypatch,
):
    captured = []

    class SuccessfulPaymentClient:
        def create(self, payment_data, request_options):
            json.dumps(payment_data)
            captured.append(payment_data)
            return {"status": 201, "response": {"id": "sandbox-payment-1000-10", "status": "approved"}}

    class SuccessfulSDK:
        def __init__(self, token: str) -> None:
            self._payment = SuccessfulPaymentClient()

        def payment(self):
            return self._payment

    monkeypatch.setattr(service_module.mercadopago, "SDK", SuccessfulSDK)
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )
    service = service_module.get_mercadopago_service(
        merchant_context=context,
        credential_resolver=EnvironmentCredentialResolver(_payment_settings()),
    )

    result = service.create_payment(
        token="card-token",
        amount=Decimal("1000.10"),
        email="payer@example.com",
        description="Wallet top-up",
        idempotency_key="payment-idempotency-key-1000-10",
    )

    assert result["success"] is True
    assert captured[0]["transaction_amount"] == 1000.1
    assert isinstance(captured[0]["transaction_amount"], float)


def test_mercadopago_service_rejects_more_than_two_decimal_places():
    with pytest.raises(ValueError, match="at most two decimal places"):
        service_module.MercadoPagoService._provider_transaction_amount(Decimal("1000.105"))
