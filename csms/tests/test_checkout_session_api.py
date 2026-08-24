"""PAY-MP-001 BE-2B checkout service, signing, and API tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.core.auth import create_access_token
from app.core.config import Settings
from app.database.models import (
    AppUser,
    AppWalletTransaction,
    AppUserPaymentMethod,
    ChargingSession,
    Invoice,
    Order,
    PaymentOrder,
    PricingSnapshot,
    Tariff,
    Tenant,
)
from app.services.payment_checkout.crypto import PaymentTokenCipher
from app.services.payment_checkout.hosted_page import render_hosted_checkout_page
from app.services.payment_checkout.models import CheckoutSessionStatus
from app.services.payment_checkout.redis_store import (
    CheckoutSessionStore,
    CheckoutStoreUnavailable,
)
from app.services.payment_checkout.service import (
    ConfirmCheckoutSessionCommand,
    CheckoutRequestConflict,
    CheckoutRequestInvalid,
    CheckoutSessionMissing,
    CheckoutSessionService,
    CheckoutServiceUnavailable,
    CheckoutTargetNotFound,
    CreateCheckoutSessionCommand,
    PaymentMethodMode,
)
from app.services.payment_checkout.signing import CheckoutSigningError, CheckoutURLSigner
from app.services.payment_providers.merchant_context import PaymentPurpose
from app.services.payment_providers.base import ProviderCreateResult
from app.services.pricing_service import PricingMode, PricingService


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

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
        return True

    def eval(self, script, numkeys, *args):
        if numkeys == 1:
            key = args[0]
            if len(args) == 4:
                _key, current_ciphertext, next_ciphertext, _ttl = args
                if self.values.get(key) != current_ciphertext:
                    return 0
                self.values[key] = next_ciphertext
                return 1
            value = self.values.pop(key, None)
            return value
        if numkeys == 2:
            if len(args) == 6:
                session_key, token_key = args[:2]
                current_ciphertext, next_ciphertext, token_ciphertext, _ttl = args[2:]
                if self.values.get(session_key) != current_ciphertext:
                    return 0
                if token_key in self.values:
                    return -2
                self.values[token_key] = token_ciphertext
                self.values[session_key] = next_ciphertext
                return 1
            session_key, idempotency_key = args[:2]
            ciphertext, _ttl, index_value = args[2:]
            existing = self.values.get(idempotency_key)
            if existing is not None:
                return [1, existing]
            self.values[session_key] = ciphertext
            self.values[idempotency_key] = index_value
            return [0, index_value]
        raise AssertionError("unexpected script")


def _settings(**overrides) -> Settings:
    values = {
        "environment": "test",
        "payment_rails_enabled": True,
        "public_api_base_url": "https://api.example.test",
        "checkout_session_ttl_seconds": 900,
        "payment_token_encryption_key": Fernet.generate_key().decode("ascii"),
        "checkout_signing_key": "checkout-signing-key-for-tests-1234567890",
        "checkout_return_url_allowlist": "eslatin://payment-return",
        "wallet_top_up_min_amount": Decimal("0.01"),
        "wallet_top_up_max_amount": Decimal("99999999.99"),
    }
    values.update(overrides)
    return Settings(**values)


def _service(settings: Settings | None = None):
    settings = settings or _settings()
    redis_client = FakeRedis()
    cipher = PaymentTokenCipher(
        settings.payment_token_encryption_key.get_secret_value()
    )
    store = CheckoutSessionStore(
        redis_client=redis_client,
        cipher=cipher,
        ttl_seconds=settings.checkout_session_ttl_seconds,
    )
    signer = CheckoutURLSigner(settings.checkout_signing_key.get_secret_value())
    return (
        CheckoutSessionService(store=store, signer=signer, settings=settings),
        store,
        redis_client,
        signer,
    )


def _app_user(db_session, email: str = "checkout@example.test") -> AppUser:
    user = AppUser(
        email=email,
        password_hash="test-password-hash",
        balance=Decimal("0.00"),
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _wallet_command(*, amount: str = "50000.00", idempotency_key=None):
    return CreateCheckoutSessionCommand(
        purpose=PaymentPurpose.WALLET_TOP_UP,
        payment_method_mode=PaymentMethodMode.NEW_CARD,
        saved_payment_method_id=None,
        save_card=False,
        amount=Decimal(amount),
        currency="COP",
        charge_point_id=None,
        connector_id=None,
        session_id=None,
        return_url="eslatin://payment-return",
        idempotency_key=str(idempotency_key or uuid4()),
    )


def _direct_command(charge_point, evse):
    return CreateCheckoutSessionCommand(
        purpose=PaymentPurpose.CHARGING_DIRECT,
        payment_method_mode=PaymentMethodMode.NEW_CARD,
        saved_payment_method_id=None,
        save_card=False,
        amount=None,
        currency="COP",
        charge_point_id=charge_point.id,
        connector_id=evse.evse_id,
        session_id=None,
        return_url="eslatin://payment-return",
        idempotency_key=str(uuid4()),
    )


class _TopUpProvider:
    provider_code = "mercadopago"

    def __init__(self):
        self.commands = []

    def create_payment(self, command, *, merchant_context):
        self.commands.append((command, merchant_context))
        return ProviderCreateResult(
            status="approved",
            provider_order_ref="top-up-external-reference",
            provider_payment_id="top-up-payment-123",
        )


def test_checkout_url_signature_is_short_lived_and_tamper_evident():
    now = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
    signer = CheckoutURLSigner(
        "checkout-signing-key-for-tests-1234567890",
        clock=lambda: now,
    )
    token = signer.sign(
        opaque_id="checkout_session_123456789",
        expires_at=now + timedelta(minutes=15),
        nonce="checkout_nonce_123456789",
    )

    verified = signer.verify(token)
    assert verified.opaque_id == "checkout_session_123456789"
    assert verified.nonce == "checkout_nonce_123456789"
    assert "email" not in token
    assert "credential" not in token

    with pytest.raises(CheckoutSigningError):
        signer.verify(f"{token[:-1]}x")
    expired_signer = CheckoutURLSigner(
        "checkout-signing-key-for-tests-1234567890",
        clock=lambda: now + timedelta(minutes=16),
    )
    with pytest.raises(CheckoutSigningError, match="expired"):
        expired_signer.verify(token)


def test_wallet_checkout_is_idempotent_owned_and_encrypted(db_session):
    user = _app_user(db_session)
    other_user = _app_user(db_session, "other-checkout@example.test")
    service, store, redis_client, signer = _service()
    idempotency_key = uuid4()
    command = _wallet_command(idempotency_key=idempotency_key)

    created = service.create(db_session, app_user_id=user.id, command=command)
    replay = service.create(db_session, app_user_id=user.id, command=command)

    assert replay.checkout_session_id == created.checkout_session_id
    assert replay.checkout_url == created.checkout_url
    signed_token = created.checkout_url.rsplit("/", 1)[-1]
    assert signer.verify(signed_token).opaque_id == created.checkout_session_id
    view = service.get(
        app_user_id=user.id,
        checkout_session_id=created.checkout_session_id,
    )
    assert view.status.value == "created"
    assert view.payment_order_id is None
    ciphertext = redis_client.values[store._session_key(created.checkout_session_id)]
    assert str(user.id) not in ciphertext
    assert "50000.00" not in ciphertext

    with pytest.raises(CheckoutSessionMissing):
        service.get(
            app_user_id=other_user.id,
            checkout_session_id=created.checkout_session_id,
        )
    with pytest.raises(CheckoutRequestConflict):
        service.create(
            db_session,
            app_user_id=user.id,
            command=_wallet_command(
                amount="60000.00",
                idempotency_key=idempotency_key,
            ),
        )


def test_direct_checkout_derives_tenant_connector_and_current_price(
    db_session,
    sample_commercial_charge_point,
    sample_evse,
):
    user = _app_user(db_session)
    service, store, _redis_client, _signer = _service()
    command = _direct_command(sample_commercial_charge_point, sample_evse)

    created = service.create(db_session, app_user_id=user.id, command=command)
    record = store.get(created.checkout_session_id)

    assert record.data["operator_tenant_id"] == str(
        sample_commercial_charge_point.tenant_id
    )
    assert record.data["charge_point_id"] == str(sample_commercial_charge_point.id)
    assert record.data["connector_id"] == sample_evse.evse_id
    assert record.data["pricing"]["base_price_per_kwh"] == "2700.00"
    assert record.data["merchant"]["merchant_account_ref"] == "platform:eslatin"
    assert "credential_handle" not in record.data["merchant"]

    # A valid idempotent replay returns the original state even if the mutable
    # charger projection changes after the first successful request.
    sample_commercial_charge_point.commissioning_status = "suspended"
    db_session.commit()
    replay = service.create(db_session, app_user_id=user.id, command=command)
    assert replay.checkout_session_id == created.checkout_session_id


def test_direct_checkout_rejects_free_pricing(
    db_session,
    sample_site,
    sample_commercial_charge_point,
    sample_evse,
):
    tariff = db_session.query(Tariff).filter(Tariff.site_id == sample_site.id).one()
    tariff.base_price_per_kwh = Decimal("0.00")
    tariff.service_fee = Decimal("0.00")
    tariff.time_based_rules = PricingService.metadata(
        PricingMode.FREE,
        free_reason="Test promotion",
    )
    db_session.commit()
    user = _app_user(db_session, "free-checkout@example.test")
    service, _store, redis_client, _signer = _service()

    with pytest.raises(CheckoutRequestInvalid):
        service.create(
            db_session,
            app_user_id=user.id,
            command=_direct_command(sample_commercial_charge_point, sample_evse),
        )

    assert redis_client.values == {}


def test_direct_checkout_rejects_cross_tenant_site_link(
    db_session,
    sample_site,
    sample_commercial_charge_point,
    sample_evse,
):
    other_tenant = Tenant(name="Cross-tenant site owner", status="active")
    db_session.add(other_tenant)
    db_session.flush()
    sample_site.tenant_id = other_tenant.id
    db_session.commit()
    user = _app_user(db_session, "cross-site-checkout@example.test")
    service, _store, redis_client, _signer = _service()

    with pytest.raises(CheckoutTargetNotFound):
        service.create(
            db_session,
            app_user_id=user.id,
            command=_direct_command(sample_commercial_charge_point, sample_evse),
        )

    assert redis_client.values == {}


def test_unpaid_checkout_uses_owned_invoice_amount(
    db_session,
    sample_tenant,
    sample_site,
    sample_commercial_charge_point,
    sample_evse,
):
    user = _app_user(db_session)
    now = datetime.now(timezone.utc)
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_commercial_charge_point.id,
        transaction_id=90321,
        id_tag=f"APP{str(user.id).replace('-', '')[:17]}",
        app_user_id=user.id,
        start_time=now - timedelta(minutes=10),
        end_time=now,
        meter_start=0,
        meter_stop=1000,
        status="completed",
        payment_status="unpaid",
    )
    tariff = db_session.query(Tariff).filter(Tariff.site_id == sample_site.id).first()
    db_session.add(session)
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
        invoice_number="INV-BE-2B-UNPAID",
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

    service, store, _redis_client, _signer = _service()
    command = CreateCheckoutSessionCommand(
        purpose=PaymentPurpose.UNPAID_CHARGE,
        payment_method_mode=PaymentMethodMode.NEW_CARD,
        saved_payment_method_id=None,
        save_card=False,
        amount=None,
        currency="COP",
        charge_point_id=None,
        connector_id=None,
        session_id=session.id,
        return_url="eslatin://payment-return",
        idempotency_key=str(uuid4()),
    )

    created = service.create(db_session, app_user_id=user.id, command=command)
    record = store.get(created.checkout_session_id)
    assert record.data["amount"] == "2700.00"
    assert record.data["invoice_id"] == str(invoice.id)

    other_user = _app_user(db_session, "unpaid-other@example.test")
    with pytest.raises(CheckoutTargetNotFound):
        service.create(db_session, app_user_id=other_user.id, command=command)

    other_tenant = Tenant(name="Cross-tenant invoice owner", status="active")
    db_session.add(other_tenant)
    db_session.flush()
    invoice.tenant_id = other_tenant.id
    db_session.commit()
    with pytest.raises(CheckoutTargetNotFound):
        service.create(
            db_session,
            app_user_id=user.id,
            command=CreateCheckoutSessionCommand(
                **{**command.__dict__, "idempotency_key": str(uuid4())}
            ),
        )


def test_saved_card_checkout_enforces_current_user_ownership(db_session):
    user = _app_user(db_session)
    other_user = _app_user(db_session, "saved-card-other@example.test")
    saved_card = AppUserPaymentMethod(
        app_user_id=user.id,
        provider="mercadopago",
        mp_customer_id="customer-safe-id",
        mp_card_id="card-safe-id",
        payment_method_brand="master",
        last_four="1234",
        is_default=True,
    )
    db_session.add(saved_card)
    db_session.commit()
    service, store, _redis_client, _signer = _service()
    command = CreateCheckoutSessionCommand(
        purpose=PaymentPurpose.WALLET_TOP_UP,
        payment_method_mode=PaymentMethodMode.SAVED_CARD,
        saved_payment_method_id=saved_card.id,
        save_card=False,
        amount=Decimal("50000.00"),
        currency="COP",
        charge_point_id=None,
        connector_id=None,
        session_id=None,
        return_url="eslatin://payment-return",
        idempotency_key=str(uuid4()),
    )

    created = service.create(db_session, app_user_id=user.id, command=command)
    assert store.get(created.checkout_session_id).data[
        "selected_payment_method_id"
    ] == str(saved_card.id)
    with pytest.raises(CheckoutTargetNotFound):
        service.create(
            db_session,
            app_user_id=other_user.id,
            command=CreateCheckoutSessionCommand(
                **{**command.__dict__, "idempotency_key": str(uuid4())}
            ),
        )


@pytest.mark.parametrize(
    ("payment_method_id", "payment_type_id", "issuer_id"),
    [
        ("visa", None, None),
        (None, "credit_card", None),
        (None, None, "123"),
    ],
)
def test_saved_card_confirm_rejects_client_card_fact_overrides(
    db_session,
    payment_method_id,
    payment_type_id,
    issuer_id,
):
    user = _app_user(db_session, f"saved-card-override-{uuid4()}@example.test")
    saved_card = AppUserPaymentMethod(
        app_user_id=user.id,
        provider="mercadopago",
        mp_customer_id="customer-safe-id",
        mp_card_id="card-safe-id",
        payment_method_brand="v1:master:prepaid_card",
        last_four="1234",
        is_default=True,
    )
    db_session.add(saved_card)
    db_session.commit()
    service, store, redis_client, _signer = _service()
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=CreateCheckoutSessionCommand(
            purpose=PaymentPurpose.WALLET_TOP_UP,
            payment_method_mode=PaymentMethodMode.SAVED_CARD,
            saved_payment_method_id=saved_card.id,
            save_card=False,
            amount=Decimal("50000.00"),
            currency="COP",
            charge_point_id=None,
            connector_id=None,
            session_id=None,
            return_url="eslatin://payment-return",
            idempotency_key=str(uuid4()),
        ),
    )

    with pytest.raises(CheckoutRequestInvalid):
        service.confirm(
            db_session,
            signed_token=created.checkout_url.rsplit("/", 1)[-1],
            command=ConfirmCheckoutSessionCommand(
                card_token="tok_saved_override_123456789",
                payment_method_id=payment_method_id,
                payment_type_id=payment_type_id,
                issuer_id=issuer_id,
                installments=1,
            ),
        )

    assert store.get(created.checkout_session_id).status.value == "created"
    assert store._token_key(created.checkout_session_id) not in redis_client.values


@pytest.mark.parametrize(
    ("payment_method_id", "payment_type_id", "installments"),
    [
        (None, "credit_card", 1),
        ("visa", None, 1),
        ("visa", "unknown_card", 1),
        ("visa", "credit_card", 2),
    ],
)
def test_new_card_confirm_rejects_invalid_provider_facts_before_token_storage(
    db_session,
    payment_method_id,
    payment_type_id,
    installments,
):
    user = _app_user(db_session, f"new-card-invalid-{uuid4()}@example.test")
    service, store, redis_client, _signer = _service()
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=_wallet_command(),
    )

    with pytest.raises(CheckoutRequestInvalid):
        service.confirm(
            db_session,
            signed_token=created.checkout_url.rsplit("/", 1)[-1],
            command=ConfirmCheckoutSessionCommand(
                card_token="tok_new_card_invalid_123456789",
                payment_method_id=payment_method_id,
                payment_type_id=payment_type_id,
                issuer_id=None,
                installments=installments,
            ),
        )

    assert store.get(created.checkout_session_id).status.value == "created"
    assert store._token_key(created.checkout_session_id) not in redis_client.values


def test_checkout_rejects_untrusted_return_url_and_out_of_bounds_amount(db_session):
    user = _app_user(db_session)
    service, _store, _redis_client, _signer = _service(
        _settings(wallet_top_up_min_amount=Decimal("1000.00"))
    )
    invalid_return = _wallet_command()
    invalid_return = CreateCheckoutSessionCommand(
        **{**invalid_return.__dict__, "return_url": "evil://payment-return"}
    )
    with pytest.raises(CheckoutRequestInvalid):
        service.create(db_session, app_user_id=user.id, command=invalid_return)
    with pytest.raises(CheckoutRequestInvalid):
        service.create(
            db_session,
            app_user_id=user.id,
            command=_wallet_command(amount="999.99"),
        )
    assert (
        service._validated_next_action_url(
            "https://secure.mercadopago.com.co/three-d-secure"
        )
        == "https://secure.mercadopago.com.co/three-d-secure"
    )
    with pytest.raises(CheckoutServiceUnavailable, match="not trusted"):
        service._validated_next_action_url("https://mercadopago.com.evil.test/3ds")


def test_checkout_freezes_save_card_to_the_independent_save_card_purpose(db_session):
    user = _app_user(db_session, "save-card-purpose@example.test")
    service, store, redis_client, _signer = _service(
        _settings(mercadopago_public_key="TEST-public-key")
    )
    wallet_with_save = CreateCheckoutSessionCommand(
        **{**_wallet_command().__dict__, "save_card": True}
    )
    save_without_flag = CreateCheckoutSessionCommand(
        purpose=PaymentPurpose.SAVE_CARD,
        payment_method_mode=PaymentMethodMode.NEW_CARD,
        saved_payment_method_id=None,
        save_card=False,
        amount=None,
        currency="COP",
        charge_point_id=None,
        connector_id=None,
        session_id=None,
        return_url="eslatin://payment-return",
        idempotency_key=str(uuid4()),
    )
    save_with_saved_card = CreateCheckoutSessionCommand(
        **{
            **save_without_flag.__dict__,
            "payment_method_mode": PaymentMethodMode.SAVED_CARD,
            "saved_payment_method_id": uuid4(),
            "save_card": True,
            "idempotency_key": str(uuid4()),
        }
    )

    for command in (wallet_with_save, save_without_flag, save_with_saved_card):
        with pytest.raises(CheckoutRequestInvalid):
            service.create(db_session, app_user_id=user.id, command=command)
        assert redis_client.values == {}

    valid_save = CreateCheckoutSessionCommand(
        **{
            **save_without_flag.__dict__,
            "save_card": True,
            "idempotency_key": str(uuid4()),
        }
    )
    created = service.create(db_session, app_user_id=user.id, command=valid_save)
    record = store.get(created.checkout_session_id)
    assert record.purpose is PaymentPurpose.SAVE_CARD
    assert record.data["payment_method_mode"] == "new_card"
    assert record.data["save_card"] is True


def test_checkout_create_and_query_api_follow_frozen_contract(
    client,
    db_session,
    monkeypatch,
):
    import app.api.v1.app.payment_checkout as checkout_api

    user = _app_user(db_session, "checkout-api@example.test")
    service, _store, _redis_client, _signer = _service()
    monkeypatch.setattr(checkout_api, "get_checkout_session_service", lambda: service)
    monkeypatch.setattr(
        checkout_api,
        "get_settings",
        lambda: SimpleNamespace(payment_rails_enabled=True),
    )
    token = create_access_token(
        {"user_id": str(user.id), "user_type": "app_user", "aud": "app"}
    )
    client.headers.update({"Authorization": f"Bearer {token}"})
    payload = {
        "purpose": "wallet_top_up",
        "payment_method_mode": "new_card",
        "saved_payment_method_id": None,
        "save_card": False,
        "amount": "50000.00",
        "currency": "COP",
        "charge_point_id": None,
        "connector_id": None,
        "session_id": None,
        "return_url": "eslatin://payment-return",
        "idempotency_key": str(uuid4()),
    }

    created = client.post("/api/v1/app/payments/checkout-sessions", json=payload)
    assert created.status_code == 200, created.text
    body = created.json()
    assert set(body) == {
        "checkout_session_id",
        "checkout_url",
        "expires_at",
        "purpose",
    }
    assert body["purpose"] == "wallet_top_up"
    assert body["checkout_url"].startswith(
        "https://api.example.test/api/v1/app/payments/checkout/"
    )

    queried = client.get(
        f"/api/v1/app/payments/checkout-sessions/{body['checkout_session_id']}"
    )
    assert queried.status_code == 200, queried.text
    assert queried.json()["status"] == "created"
    assert queried.json()["payment_order_id"] is None

    payload["return_url"] = "evil://payment-return"
    payload["idempotency_key"] = str(uuid4())
    rejected = client.post("/api/v1/app/payments/checkout-sessions", json=payload)
    assert rejected.status_code == 400
    assert rejected.json() == {
        "detail": {
            "code": "CHECKOUT_REQUEST_INVALID",
            "message": "The checkout request is invalid.",
        }
    }

    invalid_shape = dict(payload)
    invalid_shape["return_url"] = "eslatin://payment-return"
    invalid_shape["pan"] = "forbidden-card-field"
    validation_error = client.post(
        "/api/v1/app/payments/checkout-sessions",
        json=invalid_shape,
    )
    assert validation_error.status_code == 422
    assert validation_error.json() == {
        "detail": {
            "code": "VALIDATION_ERROR",
            "message": "The checkout request is invalid.",
        }
    }

    conflicting_save = {
        **payload,
        "return_url": "eslatin://payment-return",
        "save_card": True,
        "idempotency_key": str(uuid4()),
    }
    purpose_conflict = client.post(
        "/api/v1/app/payments/checkout-sessions",
        json=conflicting_save,
    )
    assert purpose_conflict.status_code == 400
    assert purpose_conflict.json()["detail"]["code"] == "CHECKOUT_REQUEST_INVALID"

    identity_in_confirm = client.post(
        "/api/v1/app/payments/checkout/not-a-valid-signed-token/confirm",
        json={
            "card_token": "tok_test_123456789012345",
            "payment_method_id": "master",
            "payment_type_id": "credit_card",
            "issuer_id": "123",
            "installments": 1,
            "identification_type": "document-type-must-not-enter-api",
            "identification_number": "document-number-must-not-enter-api",
        },
    )
    assert identity_in_confirm.status_code == 422
    assert identity_in_confirm.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_checkout_api_unauthenticated_error_follows_frozen_contract(client):
    response = client.get(
        "/api/v1/app/payments/checkout-sessions/checkout_session_missing"
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "code": "AUTHENTICATION_REQUIRED",
            "message": "Authentication is required.",
        }
    }


def test_checkout_api_invalid_user_error_follows_frozen_contract(client):
    token = create_access_token(
        {"user_id": str(uuid4()), "user_type": "app_user", "aud": "app"}
    )
    client.headers.update({"Authorization": f"Bearer {token}"})

    response = client.get(
        "/api/v1/app/payments/checkout-sessions/checkout_session_missing"
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "code": "AUTHENTICATION_INVALID",
            "message": "Authentication is invalid.",
        }
    }


def test_hosted_checkout_page_uses_secure_fields_and_security_headers(db_session):
    user = _app_user(db_session, "hosted-page@example.test")
    settings = _settings(mercadopago_public_key="TEST-public-key")
    service, _store, _redis_client, signer = _service(settings)
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=_wallet_command(),
    )
    signed_token = created.checkout_url.rsplit("/", 1)[-1]
    page = service.get_hosted_page(db_session, signed_token=signed_token)
    document = render_hosted_checkout_page(
        page,
        signed_token=signed_token,
        script_nonce="test-script-nonce",
    )

    assert signer.verify(signed_token).opaque_id == created.checkout_session_id
    assert "https://sdk.mercadopago.com/js/v2" in document
    assert 'mp.fields.create("cardNumber"' in document
    assert "mp.getIdentificationTypes()" in document
    assert "item.min_length ?? item.minLength" in document
    assert "identificationNumber.minLength = capability.minimum" in document
    assert "identificationNumber.maxLength = capability.maximum" in document
    assert "mp.getPaymentMethods({ bin: String(bin) })" in document
    assert 'supportedPaymentTypes.has(candidate.payment_type_id)' in document
    assert '"prepaid_card"' in document
    assert "mp.cardForm" not in document
    assert "fields.createCardToken" in document
    assert "fetch(checkout.confirmPath" in document
    assert 'id="identification-type"' in document
    assert 'id="identification-number"' in document
    assert '<option value="CC">' not in document
    assert 'id="issuer"' not in document
    assert 'id="installments"' not in document
    assert "Operación:" not in document
    assert "Cardholder name" not in document
    assert "Identification number" not in document
    assert "height: 3.25rem" in document
    assert "@media (max-width: 32rem)" in document
    assert "mercadopago_access_token" not in document
    assert "card_token_value" not in document


def test_saved_card_hosted_page_only_renders_cvv_and_server_card_projection(
    db_session,
):
    user = _app_user(db_session, "saved-hosted-page@example.test")
    saved_card = AppUserPaymentMethod(
        app_user_id=user.id,
        provider="mercadopago",
        mp_customer_id="customer-safe-id",
        mp_card_id="card-safe-id",
        payment_method_brand="v1:master:prepaid_card",
        last_four="1234",
        is_default=True,
    )
    db_session.add(saved_card)
    db_session.commit()
    service, _store, _redis_client, _signer = _service(
        _settings(mercadopago_public_key="TEST-public-key")
    )
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=CreateCheckoutSessionCommand(
            purpose=PaymentPurpose.WALLET_TOP_UP,
            payment_method_mode=PaymentMethodMode.SAVED_CARD,
            saved_payment_method_id=saved_card.id,
            save_card=False,
            amount=Decimal("50000.00"),
            currency="COP",
            charge_point_id=None,
            connector_id=None,
            session_id=None,
            return_url="eslatin://payment-return",
            idempotency_key=str(uuid4()),
        ),
    )

    signed_token = created.checkout_url.rsplit("/", 1)[-1]
    page = service.get_hosted_page(db_session, signed_token=signed_token)
    document = render_hosted_checkout_page(
        page,
        signed_token=signed_token,
        script_nonce="test-script-nonce",
    )

    assert page.saved_card_payment_type == "prepaid_card"
    assert "MASTER ···· 1234" in document
    assert "Tarjeta prepago" in document
    assert 'mp.fields.create("securityCode"' in document
    assert "savedProviderCardId" in document
    assert 'id="card-number"' not in document
    assert 'id="expiration-date"' not in document
    assert "cardholder-name" not in document
    assert "identification-type" not in document
    assert "identification-number" not in document
    assert "getIdentificationTypes" not in document
    assert "getPaymentMethods" not in document


def test_direct_checkout_initializes_secure_fields_without_a_final_amount(
    db_session,
    sample_commercial_charge_point,
    sample_evse,
):
    user = _app_user(db_session, "direct-hosted-page@example.test")
    settings = _settings(mercadopago_public_key="TEST-public-key")
    service, _store, _redis_client, _signer = _service(settings)
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=_direct_command(sample_commercial_charge_point, sample_evse),
    )
    signed_token = created.checkout_url.rsplit("/", 1)[-1]
    page = service.get_hosted_page(db_session, signed_token=signed_token)
    document = render_hosted_checkout_page(
        page,
        signed_token=signed_token,
        script_nonce="test-script-nonce",
    )

    assert 'mp.fields.create("cardNumber"' in document
    assert 'amount: checkout.amount ||' not in document
    assert "Validar tarjeta y continuar" in document
    assert "La tarjeta se cobrará al finalizar la carga por el importe calculado, con un mínimo de 1.011 COP." in document
    assert "charging_direct" not in document
    assert "save_card" not in document
    assert "preautoriz" not in document.lower()


def test_wallet_top_up_confirm_creates_payment_and_projects_approval(
    db_session,
    sample_tenant,
    monkeypatch,
):
    user = _app_user(db_session, "confirm-page@example.test")
    service, store, redis_client, _signer = _service(
        _settings(mercadopago_public_key="TEST-public-key")
    )
    provider = _TopUpProvider()
    monkeypatch.setattr(
        "app.services.payment_reconciliation.get_payment_provider_registry",
        lambda: type("Registry", (), {"get": lambda _self, _provider: provider})(),
    )
    monkeypatch.setattr(
        "app.services.payment_reconciliation.CheckoutSessionStore",
        lambda: store,
    )
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=_wallet_command(),
    )
    signed_token = created.checkout_url.rsplit("/", 1)[-1]
    result = service.confirm(
        db_session,
        signed_token=signed_token,
        command=ConfirmCheckoutSessionCommand(
            card_token="tok_test_123456789012345",
            payment_method_id="visa",
            payment_type_id="credit_card",
            issuer_id="123",
            installments=1,
        ),
    )

    assert result.status.value == "approved"
    assert result.redirect_url.startswith("eslatin://payment-return?")
    assert "tok_test_123456789012345" not in result.redirect_url
    record = store.get(created.checkout_session_id)
    assert record.status.value == "approved"
    assert record.data["confirmation"]["save_card"] is False
    assert store._token_key(created.checkout_session_id) not in redis_client.values

    payment_order = db_session.query(PaymentOrder).filter(
        PaymentOrder.app_user_id == user.id,
        PaymentOrder.type == "top_up",
    ).one()
    assert payment_order.status == "approved"
    assert payment_order.mercadopago_payment_id == "top-up-payment-123"
    assert payment_order.order_metadata["checkout_session_id"] == created.checkout_session_id
    assert payment_order.order_metadata["payment_purpose"] == "wallet_top_up"
    assert db_session.query(AppWalletTransaction).filter(
        AppWalletTransaction.payment_order_id == payment_order.id,
        AppWalletTransaction.type == "top_up",
    ).count() == 1
    db_session.refresh(user)
    assert user.balance == Decimal("50000.00")
    assert provider.commands[0][0].amount == Decimal("50000.00")
    assert provider.commands[0][0].payment_method_id == "visa"
    assert provider.commands[0][1].merchant_account_ref == "platform:eslatin"


@pytest.mark.parametrize(
    "payment_type_id",
    ["credit_card", "debit_card", "prepaid_card"],
)
def test_direct_checkout_confirm_creates_versioned_payment_intent_order(
    db_session,
    sample_commercial_charge_point,
    sample_evse,
    payment_type_id,
):
    user = _app_user(db_session, f"direct-confirm-{payment_type_id}@example.test")
    service, store, _redis_client, _signer = _service(
        _settings(mercadopago_public_key="TEST-public-key")
    )
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=_direct_command(sample_commercial_charge_point, sample_evse),
    )
    signed_token = created.checkout_url.rsplit("/", 1)[-1]

    result = service.confirm(
        db_session,
        signed_token=signed_token,
        command=ConfirmCheckoutSessionCommand(
            card_token="tok_direct_test_123456789",
            payment_method_id="visa",
            payment_type_id=payment_type_id,
            issuer_id="123",
            installments=1,
        ),
    )

    assert result.status.value == "ready"
    checkout = store.get(created.checkout_session_id)
    intent_id = checkout.data["results"]["payment_intent_id"]
    order = (
        db_session.query(Order)
        .filter(Order.app_user_id == user.id, Order.charge_point_id == sample_commercial_charge_point.id)
        .one()
    )
    assert order.pre_authorization["schema_version"] == 1
    assert order.pre_authorization["kind"] == "charging_payment_intent"
    assert order.pre_authorization["intent_id"] == intent_id
    assert order.pre_authorization["status"] == "ready"
    assert order.pre_authorization["connector_id"] == sample_evse.evse_id
    assert order.pre_authorization["payment_method"][
        "provider_payment_type_id"
    ] == payment_type_id
    assert order.session_id is None
    assert store.consume_card_token(created.checkout_session_id) == "tok_direct_test_123456789"


def test_direct_intent_recovery_uses_checkout_session_after_result_projection_failure(
    db_session,
    sample_commercial_charge_point,
    sample_evse,
    monkeypatch,
):
    user = _app_user(db_session, "direct-recovery@example.test")
    service, store, _redis_client, _signer = _service(
        _settings(mercadopago_public_key="TEST-public-key")
    )
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=_direct_command(sample_commercial_charge_point, sample_evse),
    )
    signed_token = created.checkout_url.rsplit("/", 1)[-1]
    original_update_record = store.update_record

    def fail_result_projection(*args, **kwargs):
        raise CheckoutStoreUnavailable("simulated result projection outage")

    monkeypatch.setattr(store, "update_record", fail_result_projection)
    with pytest.raises(CheckoutServiceUnavailable):
        service.confirm(
            db_session,
            signed_token=signed_token,
            command=ConfirmCheckoutSessionCommand(
                card_token="tok_direct_recovery_123456789",
                payment_method_id="visa",
                payment_type_id="credit_card",
                issuer_id="123",
                installments=1,
            ),
        )

    persisted = store.get(created.checkout_session_id)
    assert persisted.data["results"]["payment_intent_id"] is None
    assert db_session.query(Order).filter(Order.app_user_id == user.id).count() == 1

    # Model the safe retry/recovery path after the Order commit.  The result
    # projection is still absent, so recovery must use the authenticated
    # checkout session ID and the trusted target fields, not payment_intent_id.
    monkeypatch.setattr(store, "update_record", original_update_record)
    recovered_order, recovered_intent_id = service._create_charging_payment_intent(
        db_session,
        confirmed=persisted,
    )
    assert recovered_order.pre_authorization["intent_id"] == recovered_intent_id
    assert db_session.query(Order).filter(Order.app_user_id == user.id).count() == 1


def test_hosted_checkout_http_routes_return_csp_and_303(
    client,
    db_session,
    sample_tenant,
    monkeypatch,
):
    import app.api.v1.app.payment_checkout as checkout_api

    user = _app_user(db_session, "hosted-http@example.test")
    service, store, _redis_client, _signer = _service(
        _settings(mercadopago_public_key="TEST-public-key")
    )
    provider = _TopUpProvider()
    monkeypatch.setattr(
        "app.services.payment_reconciliation.get_payment_provider_registry",
        lambda: type("Registry", (), {"get": lambda _self, _provider: provider})(),
    )
    monkeypatch.setattr(
        "app.services.payment_reconciliation.CheckoutSessionStore",
        lambda: store,
    )
    created = service.create(
        db_session,
        app_user_id=user.id,
        command=_wallet_command(),
    )
    signed_token = created.checkout_url.rsplit("/", 1)[-1]
    monkeypatch.setattr(checkout_api, "get_checkout_session_service", lambda: service)
    monkeypatch.setattr(
        checkout_api,
        "get_settings",
        lambda: SimpleNamespace(payment_rails_enabled=True),
    )

    page_response = client.get(
        f"/api/v1/app/payments/checkout/{signed_token}"
    )
    assert page_response.status_code == 200
    assert page_response.headers["cache-control"] == "no-store"
    assert page_response.headers["referrer-policy"] == "no-referrer"
    assert page_response.headers["x-content-type-options"] == "nosniff"
    assert page_response.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in page_response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in page_response.headers["content-security-policy"]
    assert "https://sdk.mercadopago.com" in page_response.headers[
        "content-security-policy"
    ]
    assert "https://api-static.mercadopago.com" in page_response.headers[
        "content-security-policy"
    ]
    assert "https://api.mercadolibre.com" in page_response.headers[
        "content-security-policy"
    ]
    assert "tok_test_123456789012345" not in page_response.text

    confirm_response = client.post(
        f"/api/v1/app/payments/checkout/{signed_token}/confirm",
        json={
            "card_token": "tok_test_123456789012345",
            "payment_method_id": "visa",
            "payment_type_id": "prepaid_card",
            "issuer_id": "123",
            "installments": 1,
        },
        follow_redirects=False,
    )
    assert confirm_response.status_code == 303
    assert confirm_response.headers["location"].startswith(
        "eslatin://payment-return?"
    )
    assert "tok_test_123456789012345" not in confirm_response.headers["location"]
    assert store.get(created.checkout_session_id).data["confirmation"][
        "provider_hints"
    ]["payment_type_id"] == "prepaid_card"


def test_hosted_checkout_get_errors_render_inert_spanish_state_pages(
    client,
    db_session,
    monkeypatch,
):
    import app.api.v1.app.payment_checkout as checkout_api

    user = _app_user(db_session, "hosted-state-pages@example.test")
    service, store, _redis_client, _signer = _service(
        _settings(mercadopago_public_key="TEST-public-key")
    )
    monkeypatch.setattr(checkout_api, "get_checkout_session_service", lambda: service)
    monkeypatch.setattr(
        checkout_api,
        "get_settings",
        lambda: SimpleNamespace(
            payment_rails_enabled=True,
            checkout_return_url_allowlist="eslatin://payment-return",
        ),
    )

    missing_token = "invalid-checkout-token"
    missing = client.get(f"/api/v1/app/payments/checkout/{missing_token}")
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-store"
    assert missing.headers["content-type"].startswith("text/html")
    assert "La sesión de pago no está disponible" in missing.text
    assert 'href="eslatin://payment-return"' in missing.text
    assert missing_token not in missing.text
    assert "https://sdk.mercadopago.com/js/v2" not in missing.text
    assert "card-number" not in missing.text
    assert "checkout-form" not in missing.text

    created = service.create(
        db_session,
        app_user_id=user.id,
        command=_wallet_command(),
    )
    signed_token = created.checkout_url.rsplit("/", 1)[-1]
    store.transition(created.checkout_session_id, CheckoutSessionStatus.READY)
    submitted = client.get(f"/api/v1/app/payments/checkout/{signed_token}")
    assert submitted.status_code == 409
    assert "Esta operación ya fue enviada" in submitted.text
    assert signed_token not in submitted.text
    assert "security-code" not in submitted.text

    def unavailable_service():
        raise CheckoutServiceUnavailable("simulated outage")

    monkeypatch.setattr(
        checkout_api,
        "get_checkout_session_service",
        unavailable_service,
    )
    unavailable = client.get(
        "/api/v1/app/payments/checkout/unavailable-checkout-token"
    )
    assert unavailable.status_code == 503
    assert "El pago no está disponible temporalmente" in unavailable.text
    assert "simulated outage" not in unavailable.text
    assert "secure-fields" not in unavailable.text
