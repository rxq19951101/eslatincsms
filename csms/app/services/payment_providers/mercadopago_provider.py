from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import urlparse

from app.services.mercadopago_service import get_mercadopago_service
from app.services.payment_method_codec import SUPPORTED_PAYMENT_TYPES
from app.services.payment_providers.base import (
    DisputeCapabilityFact,
    FundsCapabilityFact,
    PaymentCapabilityCommand,
    PaymentCapabilityResult,
    ProviderCardResult,
    ProviderCustomerResult,
    CreatePaymentCommand,
    ProviderCapabilityError,
    PaymentProviderError,
    ProviderCreateResult,
    ProviderPaymentStatus,
    RefundCapabilityCommand,
    RefundCapabilityFacts,
    RefundCapabilityResult,
    ProviderNextAction,
    ProviderRefundFacts,
    ProviderRefundResult,
)
from app.services.payment_providers.credential_resolver import (
    CredentialResolver,
    EnvironmentCredentialResolver,
)
from app.services.payment_providers.merchant_context import (
    MerchantAccountResolver,
    MerchantContext,
    PlatformMerchantAccountResolver,
)


_PROVIDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _safe_next_action_url(payment: dict) -> str | None:
    """Extract only a provider URL; host validation belongs to the app layer."""
    candidates = [
        payment.get("redirect_url"),
        payment.get("init_point"),
        (payment.get("point_of_interaction") or {}).get("transaction_data", {}).get(
            "external_resource_url"
        ),
        (payment.get("three_ds_info") or {}).get("external_resource_url"),
    ]
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        parsed = urlparse(candidate)
        if parsed.scheme == "https" and parsed.netloc:
            return candidate
    return None


class MercadoPagoProvider:
    provider_code = "mercadopago"

    def __init__(
        self,
        *,
        merchant_resolver: MerchantAccountResolver | None = None,
        credential_resolver: CredentialResolver | None = None,
    ) -> None:
        self._merchant_resolver = merchant_resolver or PlatformMerchantAccountResolver()
        self._credential_resolver = credential_resolver or EnvironmentCredentialResolver()

    @staticmethod
    def _canonical_status(status: str) -> str:
        normalized = str(status or "").lower()
        if normalized in {"processing", "in_process", "pending"}:
            return "processing"
        if normalized in {"action_required", "pending_challenge"}:
            return "action_required"
        if normalized in {"approved", "accredited", "captured"}:
            return "provider_approved"
        if normalized in {"declined", "rejected", "cancelled", "expired", "voided", "error"}:
            return "declined"
        if normalized in {"refunded", "partially_refunded"}:
            return "refunded"
        if normalized in {"charged_back", "disputed", "chargeback"}:
            return "disputed"
        return "unknown"

    @staticmethod
    def _canonical_error(exc: PaymentProviderError) -> ProviderCapabilityError:
        # Keep SDK/provider error codes inside this adapter.  The orchestration
        # layer receives only stable, provider-neutral reasons.
        reason = "provider_unavailable" if exc.retryable else "provider_rejected"
        return ProviderCapabilityError(reason, retryable=exc.retryable)

    def create_recovery_payment(
        self,
        command: PaymentCapabilityCommand,
        *,
        merchant_context: MerchantContext,
        idempotency_key: str,
    ) -> PaymentCapabilityResult:
        try:
            result = self.create_payment(
                CreatePaymentCommand(
                    provider=self.provider_code,
                    order_type=command.purpose,
                    amount=command.amount,
                    currency=command.currency,
                    metadata=dict(command.references),
                    email=command.references.get("payer_email"),
                    token=command.instrument_token,
                    payment_method_id=command.payment_method_hint,
                    idempotency_key=idempotency_key,
                ),
                merchant_context=merchant_context,
            )
        except PaymentProviderError as exc:
            raise self._canonical_error(exc) from exc
        next_action = (
            ProviderNextAction(type="open_url", url=result.next_action_url or result.redirect_url)
            if result.next_action_url or result.redirect_url
            else None
        )
        return PaymentCapabilityResult(
            status=self._canonical_status(result.status),
            provider_ref=result.provider_payment_id or result.provider_order_ref,
            merchant_ref=result.provider_order_ref,
            amount=command.amount,
            currency=command.currency,
            next_action=next_action,
        )

    def query_payment(
        self,
        provider_ref: str,
        *,
        merchant_context: MerchantContext,
    ) -> PaymentCapabilityResult:
        try:
            result = self.get_payment_status(provider_ref, merchant_context=merchant_context)
        except PaymentProviderError as exc:
            raise self._canonical_error(exc) from exc
        next_action = (
            ProviderNextAction(type="open_url", url=result.next_action_url)
            if result.next_action_url
            else None
        )
        return PaymentCapabilityResult(
            status=self._canonical_status(result.status),
            provider_ref=result.provider_payment_id,
            merchant_ref=result.external_reference,
            amount=result.amount,
            currency=result.currency,
            next_action=next_action,
        )

    def create_refund_capability(
        self,
        command: RefundCapabilityCommand,
        *,
        merchant_context: MerchantContext,
        idempotency_key: str,
    ) -> RefundCapabilityResult:
        try:
            result = self.create_refund(
                command.payment_ref,
                command.amount,
                idempotency_key=idempotency_key,
                merchant_context=merchant_context,
            )
        except PaymentProviderError as exc:
            raise self._canonical_error(exc) from exc
        return RefundCapabilityResult(
            status=("refunded" if str(result.status).lower() in {"approved", "refunded", "completed"} else "processing"),
            refund_ref=result.refund_id,
            amount=result.amount,
        )

    def query_refund_capability(
        self,
        provider_ref: str,
        *,
        merchant_context: MerchantContext,
    ) -> RefundCapabilityFacts:
        try:
            result = self.get_refund_facts(provider_ref, merchant_context=merchant_context)
        except PaymentProviderError as exc:
            raise self._canonical_error(exc) from exc
        return RefundCapabilityFacts(
            refunded_amount=result.refunded_amount,
            refund_refs=result.refund_ids,
        )

    def query_refund_facts(
        self,
        provider_ref: str,
        *,
        merchant_context: MerchantContext,
    ) -> RefundCapabilityFacts:
        return self.query_refund_capability(provider_ref, merchant_context=merchant_context)

    def normalize_dispute_fact(
        self,
        payload: dict,
        *,
        merchant_context: MerchantContext,
    ) -> DisputeCapabilityFact:
        # Dispute ingestion is intentionally only a canonical adapter seam in
        # BE-204.  The current automatic Payments integration has no approved
        # chargeback writer; unknown/unsupported facts remain fail-closed.
        provider_ref = payload.get("payment_ref") or payload.get("id")
        if not isinstance(provider_ref, str) or not provider_ref:
            raise ProviderCapabilityError("provider_fact_invalid")
        raw_status = str(payload.get("status") or "").lower()
        status = "reversed" if raw_status in {"reversed", "won"} else "disputed"
        if raw_status not in {"reversed", "won", "disputed", "charged_back", "chargeback", "hold", "in_process"}:
            status = "unknown"
        return DisputeCapabilityFact(
            payment_ref=provider_ref,
            status=status,
            amount=Decimal(str(payload["amount"])) if payload.get("amount") is not None else None,
            currency=str(payload["currency"]).upper() if payload.get("currency") else None,
            dispute_ref=str(payload["dispute_ref"]) if payload.get("dispute_ref") else None,
            reason_code=str(payload["reason_code"]) if payload.get("reason_code") else None,
        )

    def normalize_funds_fact(
        self,
        payload: dict,
        *,
        merchant_context: MerchantContext,
    ) -> FundsCapabilityFact:
        provider_ref = payload.get("payment_ref") or payload.get("id")
        if not isinstance(provider_ref, str) or not provider_ref:
            raise ProviderCapabilityError("provider_fact_invalid")
        raw_status = str(payload.get("status") or "").lower()
        status = raw_status if raw_status in {"released", "held", "unknown", "mismatch"} else "unknown"
        return FundsCapabilityFact(
            payment_ref=provider_ref,
            status=status,
            amount=Decimal(str(payload["amount"])) if payload.get("amount") is not None else None,
            currency=str(payload["currency"]).upper() if payload.get("currency") else None,
            funds_ref=str(payload["funds_ref"]) if payload.get("funds_ref") else None,
        )

    def ingest_dispute_fact(
        self,
        payload: dict,
        *,
        merchant_context: MerchantContext,
    ) -> DisputeCapabilityFact:
        return self.normalize_dispute_fact(payload, merchant_context=merchant_context)

    def ingest_funds_fact(
        self,
        payload: dict,
        *,
        merchant_context: MerchantContext,
    ) -> FundsCapabilityFact:
        return self.normalize_funds_fact(payload, merchant_context=merchant_context)

    def create_payment(
        self,
        command: CreatePaymentCommand,
        *,
        merchant_context: MerchantContext | None = None,
    ) -> ProviderCreateResult:
        if (
            not command.email
            or not command.token
            or not command.idempotency_key
        ):
            raise PaymentProviderError("mercadopago_invalid_payment_command")

        if merchant_context is None:
            legacy_resolver = self._merchant_resolver
            if not isinstance(legacy_resolver, PlatformMerchantAccountResolver):
                raise PaymentProviderError("merchant_context_required")
            merchant_context = legacy_resolver.resolve_legacy_platform_context()
        if merchant_context.provider != self.provider_code:
            raise PaymentProviderError("merchant_provider_mismatch")
        if (
            not isinstance(command.payment_method_id, str)
            or not _PROVIDER_ID_PATTERN.fullmatch(command.payment_method_id)
        ):
            raise PaymentProviderError("mercadopago_invalid_payment_command")

        mp_service = get_mercadopago_service(
            merchant_context=merchant_context,
            credential_resolver=self._credential_resolver,
        )
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
            raise PaymentProviderError(
                "mercadopago_payment_creation_failed",
                retryable=bool(mp_result.get("retryable")),
            )

        mp_status = mp_result.get("status")
        return ProviderCreateResult(
            status=mp_service.map_status(mp_status),
            provider_order_ref=external_reference,
            provider_payment_id=mp_result.get("payment_id"),
            next_action_url=mp_result.get("next_action_url"),
            raw_response=mp_result.get("response"),
        )

    def get_payment_status(
        self,
        payment_id: str,
        *,
        merchant_context: MerchantContext,
    ) -> ProviderPaymentStatus:
        if not payment_id or not _PROVIDER_ID_PATTERN.fullmatch(str(payment_id)):
            raise PaymentProviderError("mercadopago_invalid_payment_id")
        mp_service = self._service(merchant_context)
        result = mp_service.get_payment_status(str(payment_id))
        if not result.get("success") or not isinstance(result.get("payment"), dict):
            raise PaymentProviderError("mercadopago_status_query_failed", retryable=True)
        payment = result["payment"]
        try:
            amount = Decimal(str(payment["transaction_amount"]))
            currency = str(payment["currency_id"]).upper()
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise PaymentProviderError("mercadopago_status_response_invalid") from exc
        return ProviderPaymentStatus(
            status=mp_service.map_status(str(payment.get("status") or "")),
            provider_payment_id=str(payment.get("id") or payment_id),
            external_reference=(
                str(payment["external_reference"])
                if payment.get("external_reference") is not None
                else None
            ),
            amount=amount,
            currency=currency,
            next_action_url=_safe_next_action_url(payment),
        )

    def get_refund_facts(
        self,
        payment_id: str,
        *,
        merchant_context: MerchantContext,
    ) -> ProviderRefundFacts:
        if not payment_id or not _PROVIDER_ID_PATTERN.fullmatch(str(payment_id)):
            raise PaymentProviderError("mercadopago_invalid_payment_id")
        result = self._service(merchant_context).get_refund_facts(str(payment_id))
        if not result.get("success"):
            raise PaymentProviderError(
                str(result.get("error") or "mercadopago_refund_query_failed"),
                retryable=bool(result.get("retryable", True)),
            )
        try:
            amount = Decimal(str(result.get("refunded_amount", "0")))
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise PaymentProviderError("mercadopago_refund_response_invalid") from exc
        if amount < 0:
            raise PaymentProviderError("mercadopago_refund_response_invalid")
        refund_ids = result.get("refund_ids") or ()
        if not isinstance(refund_ids, (list, tuple)):
            raise PaymentProviderError("mercadopago_refund_response_invalid")
        return ProviderRefundFacts(
            refunded_amount=amount,
            refund_ids=tuple(str(item) for item in refund_ids),
        )

    def create_refund(
        self,
        payment_id: str,
        amount: Decimal,
        *,
        idempotency_key: str,
        merchant_context: MerchantContext,
    ) -> ProviderRefundResult:
        if (
            not payment_id
            or not _PROVIDER_ID_PATTERN.fullmatch(str(payment_id))
            or not idempotency_key
            or Decimal(str(amount)) <= 0
        ):
            raise PaymentProviderError("mercadopago_invalid_refund_command")
        result = self._service(merchant_context).create_refund(
            str(payment_id), Decimal(str(amount)), idempotency_key=idempotency_key
        )
        if not result.get("success"):
            raise PaymentProviderError(
                str(result.get("error") or "mercadopago_refund_failed"),
                retryable=True,
            )
        try:
            result_amount = Decimal(str(result.get("amount", amount)))
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise PaymentProviderError("mercadopago_refund_response_invalid") from exc
        if result_amount <= 0:
            raise PaymentProviderError("mercadopago_refund_response_invalid")
        return ProviderRefundResult(
            refund_id=(str(result["refund_id"]) if result.get("refund_id") else None),
            status=str(result.get("status") or "approved"),
            amount=result_amount,
        )

    def verify_webhook_signature(
        self,
        *,
        x_signature: str,
        x_request_id: str,
        data_id: str,
        merchant_context: MerchantContext,
    ) -> bool:
        return self._service(merchant_context).verify_webhook_signature(
            x_signature=x_signature,
            x_request_id=x_request_id,
            data_id=data_id,
        )

    def _service(self, merchant_context: MerchantContext):
        if merchant_context.provider != self.provider_code:
            raise PaymentProviderError("merchant_provider_mismatch")
        return get_mercadopago_service(
            merchant_context=merchant_context,
            credential_resolver=self._credential_resolver,
        )

    def create_customer(
        self,
        *,
        email: str,
        idempotency_key: str,
        merchant_context: MerchantContext,
    ) -> ProviderCustomerResult:
        result = self._service(merchant_context).create_customer(
            email=email, idempotency_key=idempotency_key
        )
        if not result.get("success") or not result.get("customer_id"):
            raise PaymentProviderError("mercadopago_customer_creation_failed", retryable=True)
        return ProviderCustomerResult(customer_id=str(result["customer_id"]))

    def create_card(
        self,
        *,
        customer_id: str,
        token: str,
        idempotency_key: str,
        payment_method_id: str | None,
        payment_type_id: str | None,
        merchant_context: MerchantContext,
    ) -> ProviderCardResult:
        result = self._service(merchant_context).create_card(
            customer_id=customer_id, token=token, idempotency_key=idempotency_key
        )
        if not result.get("success"):
            raise PaymentProviderError("mercadopago_card_creation_failed", retryable=True)
        card_id = result.get("card_id")
        brand = result.get("brand")
        card_type = result.get("payment_type")
        last_four = result.get("last_four")
        normalized_brand = brand.strip().lower() if isinstance(brand, str) else None
        normalized_type = (
            card_type.strip().lower() if isinstance(card_type, str) else None
        )
        normalized_method_hint = (
            payment_method_id.strip().lower()
            if isinstance(payment_method_id, str)
            else None
        )
        normalized_type_hint = (
            payment_type_id.strip().lower()
            if isinstance(payment_type_id, str)
            else None
        )
        if (
            not isinstance(card_id, str)
            or not _PROVIDER_ID_PATTERN.fullmatch(card_id)
            or normalized_brand is None
            or not _PROVIDER_ID_PATTERN.fullmatch(normalized_brand)
            or normalized_type not in SUPPORTED_PAYMENT_TYPES
            or (
                normalized_method_hint is not None
                and normalized_method_hint != normalized_brand
            )
            or (
                normalized_type_hint is not None
                and normalized_type_hint != normalized_type
            )
        ):
            raise PaymentProviderError("mercadopago_card_response_invalid")
        if not isinstance(last_four, str) or not last_four.isdigit() or len(last_four) != 4:
            raise PaymentProviderError("mercadopago_card_response_invalid")
        return ProviderCardResult(
            customer_id=customer_id,
            card_id=card_id,
            brand=normalized_brand,
            payment_type=normalized_type,
            last_four=last_four,
        )

    def delete_card(
        self,
        *,
        customer_id: str,
        card_id: str,
        idempotency_key: str,
        merchant_context: MerchantContext,
    ) -> None:
        result = self._service(merchant_context).delete_card(
            customer_id=customer_id,
            card_id=card_id,
            idempotency_key=idempotency_key,
        )
        if result.get("not_found"):
            return
        if not result.get("success"):
            raise PaymentProviderError("mercadopago_card_deletion_failed", retryable=True)
