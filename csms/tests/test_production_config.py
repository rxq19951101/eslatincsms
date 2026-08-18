from app.core.config import Settings
from cryptography.fernet import Fernet
import pytest


def test_documentation_urls_accept_disabled_sentinels(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("ENCRYPTION_SALT", "test-production-salt")
    monkeypatch.setenv("OCPP_WS_REQUIRE_PRE_REGISTERED", "true")

    settings = Settings(
        environment="production",
        secret_key="production-test-secret-key-with-32-characters",
        docs_url="None",
        redoc_url="off",
    )

    assert settings.docs_url is None
    assert settings.redoc_url is None


def test_production_payment_rails_require_mercadopago_credentials(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("ENCRYPTION_SALT", "test-production-salt")
    monkeypatch.setenv("OCPP_WS_REQUIRE_PRE_REGISTERED", "true")

    with pytest.raises(ValueError, match="Mercado Pago credentials"):
        Settings(
            environment="production",
            secret_key="production-test-secret-key-with-32-characters",
            payment_rails_enabled=True,
            mercadopago_access_token="",
            mercadopago_public_key="",
            mercadopago_webhook_secret="",
        )

    configured = Settings(
        environment="production",
        secret_key="production-test-secret-key-with-32-characters",
        payment_rails_enabled=True,
        mercadopago_access_token="production-access-token",
        mercadopago_public_key="production-public-key",
        mercadopago_webhook_secret="production-webhook-secret",
        payment_token_encryption_key=Fernet.generate_key().decode("ascii"),
        checkout_signing_key="production-checkout-signing-key-at-least-32-characters",
        public_api_base_url="https://api.example.test",
    )
    assert configured.payment_rails_enabled is True


def test_production_payment_rails_require_checkout_security(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("ENCRYPTION_SALT", "test-production-salt")
    monkeypatch.setenv("OCPP_WS_REQUIRE_PRE_REGISTERED", "true")
    common = {
        "environment": "production",
        "secret_key": "production-test-secret-key-with-32-characters",
        "payment_rails_enabled": True,
        "mercadopago_access_token": "production-access-token",
        "mercadopago_public_key": "production-public-key",
        "mercadopago_webhook_secret": "production-webhook-secret",
        "public_api_base_url": "https://api.example.test",
    }
    payment_token_key = Fernet.generate_key().decode("ascii")

    with pytest.raises(ValueError, match="PAYMENT_TOKEN_ENCRYPTION_KEY"):
        Settings(**common, checkout_signing_key="x" * 32)
    with pytest.raises(ValueError, match="CHECKOUT_SIGNING_KEY"):
        Settings(**common, payment_token_encryption_key=payment_token_key)
    insecure = dict(common)
    insecure["public_api_base_url"] = "http://api.example.test"
    with pytest.raises(ValueError, match="must use HTTPS"):
        Settings(
            **insecure,
            payment_token_encryption_key=payment_token_key,
            checkout_signing_key="x" * 32,
        )
