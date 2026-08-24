"""Resolve provider credentials only at the provider adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import Settings, get_settings
from app.services.payment_providers.merchant_context import MerchantContext


class ProviderCredentialError(RuntimeError):
    """Safe configuration error that never includes credential values."""


@dataclass(frozen=True)
class ProviderCredentials:
    environment: str
    access_token: str = field(repr=False)
    public_key: str = field(repr=False)
    webhook_secret: str = field(repr=False)


class CredentialResolver(Protocol):
    def resolve(self, merchant_context: MerchantContext) -> ProviderCredentials:
        ...


class EnvironmentCredentialResolver:
    """C1 credential source backed by server-side environment settings."""

    PLATFORM_HANDLE = "env:mercadopago:platform"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    def resolve(self, merchant_context: MerchantContext) -> ProviderCredentials:
        if merchant_context.provider != "mercadopago":
            raise ProviderCredentialError("Unsupported credential provider")
        if merchant_context.credential_handle != self.PLATFORM_HANDLE:
            raise ProviderCredentialError("Unknown provider credential handle")

        settings = self._settings or get_settings()
        access_token = settings.mercadopago_access_token.get_secret_value().strip()
        public_key = settings.mercadopago_public_key.get_secret_value().strip()
        webhook_secret = settings.mercadopago_webhook_secret.get_secret_value().strip()
        if not access_token or not public_key or not webhook_secret:
            raise ProviderCredentialError("Mercado Pago credentials are not configured")

        return ProviderCredentials(
            environment=settings.mercadopago_environment,
            access_token=access_token,
            public_key=public_key,
            webhook_secret=webhook_secret,
        )
