"""PAY-MP-001 BE-3 Customers/Cards and payment-method API coverage."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from app.core.auth import create_access_token
from app.core.config import Settings
from app.database.models import AppUser, AppUserPaymentMethod
from app.services.payment_method_codec import (
    decode_payment_method_brand,
    encode_payment_method_brand,
)
from app.services.payment_methods import (
    PaymentMethodNotFound,
    PaymentMethodProviderUnavailable,
    PaymentMethodService,
)
from app.services.payment_checkout.crypto import PaymentTokenCipher
from app.services.payment_checkout.redis_store import (
    CheckoutSessionStore,
    CheckoutTokenUnavailable,
)
from app.services.payment_checkout.service import (
    ConfirmCheckoutSessionCommand,
    CheckoutRequestInvalid,
    CheckoutSessionService,
    CreateCheckoutSessionCommand,
    PaymentMethodMode,
)
from app.services.payment_checkout.signing import CheckoutURLSigner
from app.services.payment_providers.base import (
    CreatePaymentCommand,
    PaymentProviderError,
    ProviderCardResult,
    ProviderCustomerResult,
)
from app.services.payment_providers.credential_resolver import (
    EnvironmentCredentialResolver,
)
from app.services.payment_providers.mercadopago_provider import MercadoPagoProvider
from app.services.payment_providers.merchant_context import (
    PlatformMerchantAccountResolver,
    PaymentPurpose,
)


def _user(db_session, email: str = "cards@example.test") -> AppUser:
    user = AppUser(
        id=uuid4(),
        email=email,
        password_hash="test-password-hash",
        balance=Decimal("0.00"),
    )
    db_session.add(user)
    db_session.commit()
    return user


@dataclass
class FakeCustomerCardProvider:
    card_number: int = 0
    deleted: list[tuple[str, str]] | None = None

    def __post_init__(self):
        self.deleted = []
        self.customers: list[str] = []

    def create_customer(self, *, email, idempotency_key, merchant_context):
        self.customers.append(email)
        return ProviderCustomerResult(customer_id="customer-1")

    def create_card(
        self,
        *,
        customer_id,
        token,
        idempotency_key,
        payment_method_id,
        payment_type_id,
        merchant_context,
    ):
        self.card_number += 1
        return ProviderCardResult(
            customer_id=customer_id,
            card_id=f"card-{self.card_number}",
            brand=payment_method_id or "visa",
            payment_type=payment_type_id or "credit_card",
            last_four=f"123{self.card_number}",
        )

    def delete_card(self, *, customer_id, card_id, idempotency_key, merchant_context):
        self.deleted.append((customer_id, card_id))


class CheckoutRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, *, ex=None, nx=False, xx=False):
        if nx and key in self.values:
            return False
        if xx and key not in self.values:
            return False
        self.values[key] = value
        return True

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)

    def eval(self, script, numkeys, *args):
        if len(args) == 1:
            return self.values.pop(args[0], None)
        if len(args) == 5:
            session_key, index_key, ciphertext, _ttl, index_value = args
            existing = self.values.get(index_key)
            if existing:
                return [1, existing]
            self.values[session_key] = ciphertext
            self.values[index_key] = index_value
            return [0, index_value]
        if len(args) == 6:
            session_key, token_key, current, next_value, token, _ttl = args
            if self.values.get(session_key) != current:
                return 0
            if token_key in self.values:
                return -2
            self.values[token_key] = token
            self.values[session_key] = next_value
            return 1
        if len(args) == 4:
            session_key, current, next_value, _ttl = args
            if self.values.get(session_key) != current:
                return 0
            self.values[session_key] = next_value
            return 1
        raise AssertionError("unexpected Redis script")


def test_brand_codec_supports_v1_and_legacy_values():
    encoded = encode_payment_method_brand("Master", "debit_card")
    assert encoded == "v1:master:debit_card"
    assert decode_payment_method_brand(encoded).brand == "master"
    assert decode_payment_method_brand(encoded).payment_type == "debit_card"
    assert decode_payment_method_brand("visa").brand == "visa"
    assert decode_payment_method_brand("visa").payment_type is None


def test_payment_method_service_projects_prepaid_card(db_session):
    user = _user(db_session, "prepaid@example.test")
    service = PaymentMethodService(provider=FakeCustomerCardProvider())

    saved = service.save_card(
        db_session,
        app_user_id=user.id,
        token="token-prepaid",
        idempotency_key="checkout-prepaid",
        payment_method_id="master",
        payment_type_id="prepaid_card",
    )

    assert saved.brand == "master"
    assert saved.payment_type == "prepaid_card"
    assert service.list_for_user(db_session, app_user_id=user.id)[0] == saved


def test_payment_method_service_does_not_persist_invalid_provider_card(db_session):
    user = _user(db_session, "invalid-provider-card@example.test")
    provider = FakeCustomerCardProvider()
    provider.create_card = lambda **_kwargs: ProviderCardResult(
        customer_id="customer-1",
        card_id="card-invalid",
        brand="visa",
        payment_type="unknown_card",  # type: ignore[arg-type]
        last_four="1234",
    )
    service = PaymentMethodService(provider=provider)

    with pytest.raises(PaymentMethodProviderUnavailable):
        service.save_card(
            db_session,
            app_user_id=user.id,
            token="token-invalid-provider-card",
            idempotency_key="checkout-invalid-provider-card",
            payment_method_id="visa",
            payment_type_id="credit_card",
        )

    assert (
        db_session.query(AppUserPaymentMethod)
        .filter(AppUserPaymentMethod.app_user_id == user.id)
        .count()
        == 0
    )


def test_payment_method_service_saves_defaults_and_deletes_provider_missing_card(db_session):
    user = _user(db_session)
    provider = FakeCustomerCardProvider()
    service = PaymentMethodService(provider=provider)

    first = service.save_card(
        db_session,
        app_user_id=user.id,
        token="token-one",
        idempotency_key="checkout-one",
        payment_method_id="visa",
        payment_type_id="credit_card",
    )
    second = service.save_card(
        db_session,
        app_user_id=user.id,
        token="token-two",
        idempotency_key="checkout-two",
        payment_method_id="master",
        payment_type_id="debit_card",
    )
    assert first.is_default is True
    assert second.is_default is False
    assert provider.customers == [user.email]
    assert service.list_for_user(db_session, app_user_id=user.id)[0].id == first.id

    service.set_default(
        db_session, app_user_id=user.id, payment_method_id=UUID(second.id)
    )
    service.delete(
        db_session,
        app_user_id=user.id,
        payment_method_id=UUID(second.id),
        idempotency_key="delete-second",
    )
    remaining = service.list_for_user(db_session, app_user_id=user.id)
    assert len(remaining) == 1
    assert remaining[0].is_default is True
    assert provider.deleted == [("customer-1", "card-2")]


def test_payment_method_service_isolates_users(db_session):
    user = _user(db_session, "owner@example.test")
    other = _user(db_session, "other@example.test")
    service = PaymentMethodService(provider=FakeCustomerCardProvider())
    saved = service.save_card(
        db_session,
        app_user_id=user.id,
        token="token-owner",
        idempotency_key="owner-card",
        payment_method_id="visa",
        payment_type_id="credit_card",
    )
    with pytest.raises(PaymentMethodNotFound):
        service.set_default(
            db_session,
            app_user_id=other.id,
            payment_method_id=UUID(saved.id),
        )
    assert service.list_for_user(db_session, app_user_id=other.id) == []


def test_save_card_checkout_consumes_token_and_publishes_saved_method(db_session):
    user = _user(db_session, "checkout-save@example.test")
    settings = Settings(
        payment_rails_enabled=True,
        public_api_base_url="https://api.example.test",
        payment_token_encryption_key=Fernet.generate_key().decode("ascii"),
        checkout_signing_key="checkout-signing-key-for-tests-1234567890",
        checkout_return_url_allowlist="eslatin://payment-return",
    )
    redis_client = CheckoutRedis()
    store = CheckoutSessionStore(
        redis_client=redis_client,
        cipher=PaymentTokenCipher(
            settings.payment_token_encryption_key.get_secret_value()
        ),
        ttl_seconds=900,
    )
    provider = FakeCustomerCardProvider()
    payment_service = PaymentMethodService(provider=provider)
    service = CheckoutSessionService(
        store=store,
        signer=CheckoutURLSigner(settings.checkout_signing_key.get_secret_value()),
        settings=settings,
        payment_method_service=payment_service,
    )
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=CreateCheckoutSessionCommand(
            purpose=PaymentPurpose.SAVE_CARD,
            payment_method_mode=PaymentMethodMode.NEW_CARD,
            saved_payment_method_id=None,
            save_card=True,
            amount=None,
            currency="COP",
            charge_point_id=None,
            connector_id=None,
            session_id=None,
            return_url="eslatin://payment-return",
            idempotency_key="save-card-checkout",
        ),
    )
    result = service.confirm(
        db_session,
        signed_token=created.checkout_url.rsplit("/", 1)[-1],
        command=ConfirmCheckoutSessionCommand(
            card_token="tok_save_card_1234567890",
            payment_method_id="visa",
            payment_type_id="credit_card",
            issuer_id=None,
            installments=1,
        ),
    )
    assert result.status.value == "approved"
    assert store.get(created.checkout_session_id).data["results"]["saved_payment_method_id"]
    with pytest.raises(CheckoutTokenUnavailable):
        store.consume_card_token(created.checkout_session_id)
    assert payment_service.list_for_user(db_session, app_user_id=user.id)[0].brand == "visa"


@pytest.mark.parametrize(
    ("payment_method_id", "payment_type_id"),
    [
        (None, "credit_card"),
        ("visa", None),
        ("visa", "unknown_card"),
    ],
)
def test_save_card_checkout_rejects_missing_or_unknown_provider_hints(
    db_session,
    payment_method_id,
    payment_type_id,
):
    user = _user(db_session, f"invalid-save-hints-{uuid4()}@example.test")
    settings = Settings(
        payment_rails_enabled=True,
        public_api_base_url="https://api.example.test",
        payment_token_encryption_key=Fernet.generate_key().decode("ascii"),
        checkout_signing_key="checkout-signing-key-for-tests-1234567890",
        checkout_return_url_allowlist="eslatin://payment-return",
    )
    redis_client = CheckoutRedis()
    store = CheckoutSessionStore(
        redis_client=redis_client,
        cipher=PaymentTokenCipher(
            settings.payment_token_encryption_key.get_secret_value()
        ),
        ttl_seconds=900,
    )
    service = CheckoutSessionService(
        store=store,
        signer=CheckoutURLSigner(settings.checkout_signing_key.get_secret_value()),
        settings=settings,
        payment_method_service=PaymentMethodService(
            provider=FakeCustomerCardProvider()
        ),
    )
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=CreateCheckoutSessionCommand(
            purpose=PaymentPurpose.SAVE_CARD,
            payment_method_mode=PaymentMethodMode.NEW_CARD,
            saved_payment_method_id=None,
            save_card=True,
            amount=None,
            currency="COP",
            charge_point_id=None,
            connector_id=None,
            session_id=None,
            return_url="eslatin://payment-return",
            idempotency_key=f"save-card-invalid-hints-{uuid4()}",
        ),
    )

    with pytest.raises(CheckoutRequestInvalid):
        service.confirm(
            db_session,
            signed_token=created.checkout_url.rsplit("/", 1)[-1],
            command=ConfirmCheckoutSessionCommand(
                card_token="tok_invalid_hints_1234567890",
                payment_method_id=payment_method_id,
                payment_type_id=payment_type_id,
                issuer_id=None,
                installments=1,
            ),
        )

    assert store.get(created.checkout_session_id).status.value == "created"
    assert store._token_key(created.checkout_session_id) not in redis_client.values
    assert (
        db_session.query(AppUserPaymentMethod)
        .filter(AppUserPaymentMethod.app_user_id == user.id)
        .count()
        == 0
    )


@pytest.mark.parametrize(
    ("brand", "payment_type"),
    [
        ("visa", "credit_card"),
        ("master", "debit_card"),
        ("master", "prepaid_card"),
    ],
)
def test_mercado_pago_provider_maps_customer_card_and_idempotent_delete(
    monkeypatch,
    brand,
    payment_type,
):
    class FakeCustomer:
        def create(self, body, options):
            assert body == {"email": "payer@example.test"}
            return {"status": 201, "response": {"id": "customer-1"}}

    class FakeCard:
        def create(self, customer_id, body, options):
            assert customer_id == "customer-1"
            assert body == {"token": "one-time-card-token"}
            return {
                "status": 201,
                "response": {
                    "id": "card-1",
                    "payment_method": {"id": brand, "type": payment_type},
                    "last_four_digits": "1234",
                },
            }

        def delete(self, customer_id, card_id, options):
            assert (customer_id, card_id) == ("customer-1", "card-1")
            return {"status": 404}

    class FakeSDK:
        def __init__(self, access_token):
            self._customer = FakeCustomer()
            self._card = FakeCard()

        def customer(self):
            return self._customer

        def card(self):
            return self._card

    monkeypatch.setattr("app.services.mercadopago_service.mercadopago.SDK", FakeSDK)
    settings = Settings(
        mercadopago_access_token="access-token",
        mercadopago_public_key="public-key",
        mercadopago_webhook_secret="webhook-secret",
    )
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None, payment_purpose=PaymentPurpose.SAVE_CARD
    )
    provider = MercadoPagoProvider(
        merchant_resolver=PlatformMerchantAccountResolver(),
        credential_resolver=EnvironmentCredentialResolver(settings),
    )
    customer = provider.create_customer(
        email="payer@example.test",
        idempotency_key="customer-key",
        merchant_context=context,
    )
    card = provider.create_card(
        customer_id=customer.customer_id,
        token="one-time-card-token",
        idempotency_key="card-key",
        payment_method_id=brand,
        payment_type_id=payment_type,
        merchant_context=context,
    )
    provider.delete_card(
        customer_id=customer.customer_id,
        card_id=card.card_id,
        idempotency_key="delete-key",
        merchant_context=context,
    )
    assert card.last_four == "1234"
    assert card.brand == brand
    assert card.payment_type == payment_type


@pytest.mark.parametrize(
    "card_response",
    [
        {"card_id": "card-1", "brand": "visa", "payment_type": None, "last_four": "1234"},
        {"card_id": "card-1", "brand": "visa", "payment_type": "crypto_card", "last_four": "1234"},
        {"card_id": "card-1", "brand": None, "payment_type": "credit_card", "last_four": "1234"},
        {"card_id": "card-1", "brand": "master", "payment_type": "credit_card", "last_four": "1234"},
        {"card_id": "card-1", "brand": "visa", "payment_type": "debit_card", "last_four": "1234"},
    ],
)
def test_mercado_pago_provider_rejects_missing_unknown_or_conflicting_card_facts(
    monkeypatch,
    card_response,
):
    provider = MercadoPagoProvider()
    monkeypatch.setattr(
        provider,
        "_service",
        lambda _context: SimpleNamespace(
            create_card=lambda **_kwargs: {"success": True, **card_response}
        ),
    )
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.SAVE_CARD,
    )

    with pytest.raises(PaymentProviderError, match="mercadopago_card_response_invalid"):
        provider.create_card(
            customer_id="customer-1",
            token="one-time-card-token",
            idempotency_key="card-key",
            payment_method_id="visa",
            payment_type_id="credit_card",
            merchant_context=context,
        )


def test_mercado_pago_payment_provider_rejects_missing_payment_method_hint():
    provider = MercadoPagoProvider()
    context = PlatformMerchantAccountResolver().resolve(
        operator_tenant_id=None,
        payment_purpose=PaymentPurpose.WALLET_TOP_UP,
    )

    with pytest.raises(PaymentProviderError, match="mercadopago_invalid_payment_command"):
        provider.create_payment(
            CreatePaymentCommand(
                provider="mercadopago",
                order_type="top_up",
                amount=Decimal("1000.00"),
                currency="COP",
                email="payer@example.test",
                token="one-time-card-token",
                payment_method_id=None,
                idempotency_key="payment-key",
            ),
            merchant_context=context,
        )


def test_payment_method_api_lists_only_canonical_projection(client, db_session, monkeypatch):
    import app.api.v1.app.payment_methods as payment_methods_api
    from app.api.v1.app.payment_methods import get_payment_method_service

    user = _user(db_session, "api-cards@example.test")
    db_session.add(
        AppUserPaymentMethod(
            app_user_id=user.id,
            provider="mercadopago",
            mp_customer_id="customer-1",
            mp_card_id="card-1",
            payment_method_brand="v1:visa:credit_card",
            last_four="1234",
            is_default=True,
        )
    )
    db_session.commit()
    token = create_access_token(
        {"user_id": str(user.id), "user_type": "app_user", "aud": "app"}
    )
    client.headers.update({"Authorization": f"Bearer {token}"})
    client.app.dependency_overrides[get_payment_method_service] = lambda: PaymentMethodService(
        provider=FakeCustomerCardProvider()
    )
    monkeypatch.setattr(
        payment_methods_api,
        "get_settings",
        lambda: SimpleNamespace(payment_rails_enabled=True),
    )
    try:
        modern = client.get("/api/v1/app/payment-methods")
        legacy = client.get("/api/v1/app/wallet/saved-payment-methods")
        method_id = modern.json()["items"][0]["id"]
        changed = client.patch(
            f"/api/v1/app/payment-methods/{method_id}",
            json={"is_default": True},
            headers={"Idempotency-Key": "set-default-api"},
        )
        deleted = client.delete(
            f"/api/v1/app/payment-methods/{method_id}",
            headers={"Idempotency-Key": "delete-card-api"},
        )
    finally:
        client.app.dependency_overrides.pop(get_payment_method_service, None)
    assert modern.status_code == 200
    assert modern.json()["items"] == [
        {
            "id": modern.json()["items"][0]["id"],
            "provider": "mercadopago",
            "brand": "visa",
            "payment_type": "credit_card",
            "last_four": "1234",
            "is_default": True,
        }
    ]
    assert legacy.status_code == 404
    assert changed.status_code == 200
    assert changed.json()["is_default"] is True
    assert deleted.status_code == 204
