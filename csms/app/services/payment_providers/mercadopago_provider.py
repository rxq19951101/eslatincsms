from __future__ import annotations

from app.services.mercadopago_service import get_mercadopago_service
from app.services.payment_providers.base import (
    CreatePaymentCommand,
    ProviderCreateResult,
)


class MercadoPagoProvider:
    provider_code = "mercadopago"

    def create_payment(self, command: CreatePaymentCommand) -> ProviderCreateResult:
        if not command.email or not command.token or not command.idempotency_key:
            raise ValueError("email, token and idempotency_key are required for Mercado Pago")

        mp_service = get_mercadopago_service()
        external_reference = mp_service.generate_external_reference()
        description = command.description
        if not description:
            if command.order_type == "top_up":
                description = "EsLatin Wallet Top-up"
            else:
                station_id = command.metadata.get("station_id", "Unknown")
                description = f"EsLatin Carga - Station {station_id}"

        mp_result = mp_service.create_payment(
            token=command.token,
            amount=command.amount,
            email=command.email,
            description=description,
            idempotency_key=command.idempotency_key,
            device_id=command.device_id,
            metadata=command.metadata,
            external_reference=external_reference,
            payment_method_id=command.payment_method_id,
        )
        if not mp_result.get("success"):
            raise ValueError(mp_result.get("error", "MercadoPago payment creation failed"))

        mp_status = mp_result.get("status")
        return ProviderCreateResult(
            status=mp_service.map_status(mp_status),
            provider_order_ref=external_reference,
            provider_payment_id=mp_result.get("payment_id"),
            raw_response=mp_result.get("response"),
        )

