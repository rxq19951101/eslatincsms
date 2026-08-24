from __future__ import annotations

from app.services.payment_providers.base import (
    CreatePaymentCommand,
    ProviderCreateResult,
)
from app.services.wompi_service import get_wompi_service


class WompiProvider:
    provider_code = "wompi"

    def create_payment(self, command: CreatePaymentCommand) -> ProviderCreateResult:
        wompi_service = get_wompi_service()
        reference = wompi_service.generate_reference()
        redirect_url = "https://your-app.com/payment/result"
        checkout_payload = wompi_service.create_payment_checkout_data(
            reference=reference,
            amount=command.amount,
            currency=command.currency,
            redirect_url=redirect_url,
        )
        return ProviderCreateResult(
            status="created",
            provider_order_ref=reference,
            redirect_url=redirect_url,
            checkout_payload=checkout_payload,
        )

