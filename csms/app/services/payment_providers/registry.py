from __future__ import annotations

from typing import Dict

from app.services.payment_providers.base import PaymentProvider


class PaymentProviderRegistry:
    def __init__(self) -> None:
        self._providers: Dict[str, PaymentProvider] = {}

    def register(self, provider: PaymentProvider) -> None:
        self._providers[provider.provider_code] = provider

    def get(self, provider_code: str) -> PaymentProvider:
        provider = self._providers.get(provider_code)
        if not provider:
            raise ValueError(f"Unsupported payment provider: {provider_code}")
        return provider


_registry: PaymentProviderRegistry | None = None


def get_payment_provider_registry() -> PaymentProviderRegistry:
    global _registry
    if _registry is None:
        from app.services.payment_providers.mercadopago_provider import MercadoPagoProvider
        from app.services.payment_providers.wompi_provider import WompiProvider

        _registry = PaymentProviderRegistry()
        _registry.register(WompiProvider())
        _registry.register(MercadoPagoProvider())
    return _registry

