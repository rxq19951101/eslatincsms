"""Shared direct-card charging payment creation and reconciliation.

The provider callback and the status/reconciliation paths deliberately use the
same state transition function.  Provider payloads are treated as untrusted
facts; only the order's immutable amount, server-side tenant and merchant
snapshot are allowed to drive business state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging_config import get_logger
from app.database.models import (
    AppUser,
    AppUserPaymentMethod,
    AppWalletTransaction,
    ChargePoint,
    ChargingSession,
    Invoice,
    Order,
    Payment,
    PaymentOrder,
    Tenant,
)
from app.domain.payment import transition_status
from app.services.payment_checkout.redis_store import (
    CheckoutSessionStore,
    CheckoutStoreError,
)
from app.services.payment_providers.base import (
    CreatePaymentCommand,
    PaymentCapabilityCommand,
    PaymentCapabilityResult,
    ProviderCapabilityError,
    PaymentProviderError,
    ProviderCreateResult,
    ProviderPaymentStatus,
    ProviderNextAction,
    CanonicalPaymentStatus,
)
from app.services.payment_providers.merchant_context import (
    MerchantAccountResolver,
    MerchantContext,
    MerchantContextError,
    PaymentPurpose,
    PlatformMerchantAccountResolver,
)
from app.services.payment_providers.registry import get_payment_provider_registry
from app.services.payment_method_codec import (
    SUPPORTED_PAYMENT_TYPES,
    decode_payment_method_brand,
)
from app.services.runtime_rail_control import RuntimeRailControlService


logger = get_logger("payment_reconciliation")

_PROVIDER_HINT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_PROVIDER_PAYMENT_TYPES = SUPPORTED_PAYMENT_TYPES


class PaymentReconciliationError(RuntimeError):
    """A provider fact cannot be safely applied to the payment order."""


@dataclass(frozen=True)
class ReconciliationResult:
    order_status: str
    api_status: str
    payment_order_id: str
    duplicate_approved: bool = False
    next_action: dict[str, str] | None = None


class PaymentReconciliationService:
    """Create direct-card payments and apply all provider results uniformly."""

    def __init__(
        self,
        *,
        merchant_resolver: MerchantAccountResolver | None = None,
        provider_registry=None,
        checkout_store: CheckoutSessionStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._merchant_resolver = merchant_resolver or PlatformMerchantAccountResolver()
        self._provider_registry = provider_registry or get_payment_provider_registry()
        self._checkout_store = checkout_store
        self._settings = settings or get_settings()

    def _payer_email(self, app_user_email: str) -> str:
        """Return the provider payer email without changing production identity.

        Mercado Pago's direct-card sandbox rejects ``<nickname>@testuser.com``
        payer emails, while production must use the real app user's email.
        Keep this compatibility rule at the provider boundary so domain and
        account data remain unchanged.
        """
        if self._settings.mercadopago_environment.strip().lower() == "sandbox":
            sandbox_email = self._settings.mercadopago_sandbox_payer_email.strip()
            if sandbox_email:
                return sandbox_email
        return app_user_email

    def _store(self) -> CheckoutSessionStore:
        return self._checkout_store or CheckoutSessionStore()

    def merchant_context_for_order(
        self,
        *,
        payment_order: PaymentOrder,
        purpose: PaymentPurpose = PaymentPurpose.RECONCILIATION,
    ) -> MerchantContext:
        metadata = payment_order.order_metadata or {}
        try:
            tenant_value = metadata.get("operator_tenant_id")
            tenant_id = UUID(str(tenant_value)) if tenant_value else None
            snapshot = metadata["merchant"]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PaymentReconciliationError("Payment merchant snapshot is incomplete") from exc
        if not isinstance(snapshot, Mapping):
            raise PaymentReconciliationError("Payment merchant snapshot is invalid")
        try:
            context = self._merchant_resolver.resolve(
                operator_tenant_id=tenant_id,
                payment_purpose=purpose,
            )
        except MerchantContextError as exc:
            raise PaymentReconciliationError("Unable to resolve payment merchant") from exc
        expected = context.safe_snapshot()
        for key in ("merchant_mode", "merchant_account_ref", "provider"):
            if snapshot.get(key) != expected.get(key):
                raise PaymentReconciliationError("Payment merchant snapshot mismatch")
        return context

    @staticmethod
    def _checkout_session_id(payment_order: PaymentOrder) -> str | None:
        metadata = payment_order.order_metadata or {}
        candidate = metadata.get("checkout_session_id")
        return str(candidate) if candidate else None

    @staticmethod
    def _provider_hints(db: Session, order: Order | None, app_user_id: UUID) -> dict[str, Any]:
        pre_authorization = order.pre_authorization if order else None
        if not isinstance(pre_authorization, Mapping):
            return {}
        payment_method = pre_authorization.get("payment_method")
        if not isinstance(payment_method, Mapping):
            return {}
        hints = dict(payment_method)
        if not hints.get("provider_payment_method_id") and hints.get("saved_payment_method_id"):
            try:
                saved_id = UUID(str(hints["saved_payment_method_id"]))
            except (TypeError, ValueError, AttributeError):
                return hints
            saved = db.query(AppUserPaymentMethod).filter(
                AppUserPaymentMethod.id == saved_id,
                AppUserPaymentMethod.app_user_id == app_user_id,
                AppUserPaymentMethod.provider == "mercadopago",
            ).first()
            if saved is not None:
                descriptor = decode_payment_method_brand(saved.payment_method_brand)
                hints["provider_payment_method_id"] = descriptor.brand
                hints["provider_payment_type_id"] = descriptor.payment_type
        return hints

    @staticmethod
    def _canonical_provider_hints(raw_hints: Mapping[str, Any]) -> dict[str, str]:
        method_id = raw_hints.get("provider_payment_method_id")
        if method_id is None:
            method_id = raw_hints.get("payment_method_id")
        payment_type_id = raw_hints.get("provider_payment_type_id")
        if payment_type_id is None:
            payment_type_id = raw_hints.get("payment_type_id")
        if (
            not isinstance(method_id, str)
            or not _PROVIDER_HINT_ID_PATTERN.fullmatch(method_id)
        ):
            raise PaymentReconciliationError(
                "Payment order provider payment method is invalid"
            )
        if (
            not isinstance(payment_type_id, str)
            or payment_type_id not in _PROVIDER_PAYMENT_TYPES
        ):
            raise PaymentReconciliationError(
                "Payment order provider payment type is invalid"
            )
        return {
            "provider_payment_method_id": method_id,
            "provider_payment_type_id": payment_type_id,
        }

    @classmethod
    def _payment_order_provider_hints(
        cls,
        db: Session,
        payment_order: PaymentOrder,
        app_user_id: UUID,
    ) -> dict[str, Any] | None:
        """Read only the server-validated provider hints carried by the order.

        ``None`` means this is a legacy order without a metadata hint block and
        permits the Charging Order fallback.  A present but invalid block fails
        closed instead of allowing the provider SDK to default to Visa.
        """
        metadata = payment_order.order_metadata or {}
        if "provider_hints" not in metadata:
            return None
        raw_hints = metadata.get("provider_hints")
        if not isinstance(raw_hints, Mapping):
            raise PaymentReconciliationError("Payment order provider hints are invalid")

        selected_id = raw_hints.get("selected_payment_method_id")
        if selected_id:
            try:
                saved_id = UUID(str(selected_id))
            except (TypeError, ValueError, AttributeError) as exc:
                raise PaymentReconciliationError(
                    "Payment order saved payment method is invalid"
                ) from exc
            saved = db.query(AppUserPaymentMethod).filter(
                AppUserPaymentMethod.id == saved_id,
                AppUserPaymentMethod.app_user_id == app_user_id,
                AppUserPaymentMethod.provider == "mercadopago",
            ).first()
            if saved is None:
                raise PaymentReconciliationError(
                    "Payment order saved payment method is unavailable"
                )
            descriptor = decode_payment_method_brand(saved.payment_method_brand)
            return cls._canonical_provider_hints(
                {
                    "provider_payment_method_id": descriptor.brand,
                    "provider_payment_type_id": descriptor.payment_type,
                }
            )

        return cls._canonical_provider_hints(raw_hints)

    @staticmethod
    def _begin_provider_operation(
        db: Session,
        *,
        payment_order: PaymentOrder,
        metadata: Mapping[str, Any],
    ) -> str:
        """Persist the provider operation and end the local transaction.

        Provider HTTP must never run while this Session owns a transaction or
        row lock.  The operation key is persisted before the commit so a
        retry can observe ``processing`` and reuse the same provider key.
        """
        operation_key = f"payment-order:{payment_order.id}"
        next_metadata = dict(metadata)
        next_metadata["provider_operation_key"] = operation_key
        next_metadata["provider_status"] = "processing"
        payment_order.order_metadata = next_metadata
        payment_order.status = transition_status(payment_order.status, "processing")
        db.commit()
        return operation_key

    @staticmethod
    def _legacy_status(status: str) -> str:
        """Project canonical adapter state into the unchanged P001 state set."""
        return {
            "provider_approved": "approved",
        }.get(status, status)

    def _create_payment(
        self,
        provider,
        command: CreatePaymentCommand,
        *,
        merchant_context: MerchantContext,
        operation_key: str,
    ) -> ProviderCreateResult:
        """Call the canonical capability, with an explicit P001 fallback.

        The fallback exists only for old test doubles and legacy providers. New
        adapters must implement ``create_recovery_payment`` and therefore do
        not expose provider IDs, SDK errors, or raw responses to the core.
        """
        capability = getattr(provider, "create_recovery_payment", None)
        if callable(capability):
            references = dict(command.metadata or {})
            if command.email:
                references["payer_email"] = command.email
            result: PaymentCapabilityResult = capability(
                PaymentCapabilityCommand(
                    amount=command.amount,
                    currency=command.currency,
                    purpose=command.metadata.get("payment_purpose") or command.order_type,
                    merchant_account_ref=merchant_context.merchant_account_ref,
                    references=references,
                    instrument_token=command.token,
                    payment_method_hint=command.payment_method_id,
                    payment_type_hint=command.metadata.get("provider_payment_type_id"),
                ),
                merchant_context=merchant_context,
                idempotency_key=operation_key,
            )
            next_action_url = None
            if result.next_action and result.next_action.type == "open_url":
                next_action_url = result.next_action.url
            return ProviderCreateResult(
                status=self._legacy_status(result.status),
                provider_order_ref=result.merchant_ref,
                provider_payment_id=result.provider_ref,
                next_action_url=next_action_url,
            )
        return provider.create_payment(command, merchant_context=merchant_context)

    def start_payment_order(self, db: Session, *, payment_order_id: UUID | str) -> ReconciliationResult:
        """Consume the one-time token, call the provider, then reconcile."""
        payment_order = db.query(PaymentOrder).filter(PaymentOrder.id == payment_order_id).first()
        if payment_order is None:
            raise PaymentReconciliationError("Payment order not found")
        if payment_order.status != "created":
            return self._result_from_order(payment_order)
        metadata = payment_order.order_metadata or {}
        payment_purpose = str(metadata.get("payment_purpose") or "charging_direct")
        try:
            purpose = PaymentPurpose(payment_purpose)
        except ValueError:
            return self._fail_order(
                db,
                payment_order_id=payment_order.id,
                reason="payment_purpose_invalid",
            )
        tenant_id = None
        tenant_value = metadata.get("operator_tenant_id")
        if tenant_value:
            try:
                tenant_id = UUID(str(tenant_value))
            except (TypeError, ValueError):
                return self._fail_order(
                    db,
                    payment_order_id=payment_order.id,
                    reason="payment_tenant_invalid",
                )
        site_id = None
        session_value = metadata.get("session_id")
        if session_value:
            try:
                session_id_uuid = UUID(str(session_value))
            except (TypeError, ValueError):
                session_id_uuid = None
            if session_id_uuid is not None:
                session = db.query(ChargingSession).filter(ChargingSession.id == session_id_uuid).first()
                if session is not None:
                    tenant_id = tenant_id or session.tenant_id
                    site_id = db.query(ChargePoint.site_id).filter(
                        ChargePoint.id == session.charge_point_id,
                        ChargePoint.tenant_id == session.tenant_id,
                    ).scalar()
        RuntimeRailControlService.require_payment_creation_open(
            db,
            provider=str(payment_order.payment_provider),
            tenant_id=tenant_id,
            site_id=site_id,
        )
        invoice_id = metadata.get("invoice_id")
        session_id = metadata.get("session_id")
        checkout_session_id = self._checkout_session_id(payment_order)

        if purpose is PaymentPurpose.WALLET_TOP_UP:
            app_user = db.query(AppUser).filter(
                AppUser.id == payment_order.app_user_id
            ).first()
            if app_user is None or not checkout_session_id:
                return self._fail_order(
                    db,
                    payment_order_id=payment_order.id,
                    reason="wallet_top_up_checkout_state_incomplete",
                )

            try:
                merchant_context = self.merchant_context_for_order(
                    payment_order=payment_order,
                    purpose=PaymentPurpose.WALLET_TOP_UP,
                )
                token = self._store().consume_card_token(checkout_session_id)
                hints = self._payment_order_provider_hints(
                    db,
                    payment_order,
                    app_user.id,
                )
                if hints is None:
                    raise PaymentReconciliationError(
                        "Payment order provider hints are unavailable"
                    )
                top_up_amount = Decimal(str(payment_order.amount))
                top_up_currency = payment_order.currency
                top_up_user_email = self._payer_email(app_user.email)
                top_up_provider = payment_order.payment_provider
                top_up_operator_tenant_id = metadata.get("operator_tenant_id")
                operation_key = self._begin_provider_operation(
                    db,
                    payment_order=payment_order,
                    metadata=metadata,
                )
                provider = self._provider_registry.get(top_up_provider)
                result = self._create_payment(
                    provider,
                    CreatePaymentCommand(
                        provider=top_up_provider,
                        order_type="top_up",
                        amount=top_up_amount,
                        currency=top_up_currency,
                        metadata={
                            "payment_purpose": PaymentPurpose.WALLET_TOP_UP.value,
                            "checkout_session_id": checkout_session_id,
                            "operator_tenant_id": top_up_operator_tenant_id,
                        },
                        email=top_up_user_email,
                        token=token,
                        payment_method_id=hints["provider_payment_method_id"],
                        idempotency_key=operation_key,
                        description="EsLatin Wallet Top-up",
                    ),
                    merchant_context=merchant_context,
                    operation_key=operation_key,
                )
                return self.reconcile(
                    db,
                    payment_order_id=payment_order.id,
                    status=result.status,
                    provider_payment_id=result.provider_payment_id,
                    external_reference=result.provider_order_ref,
                    amount=top_up_amount,
                    currency=top_up_currency,
                    next_action_url=result.next_action_url or result.redirect_url,
                )
            except (
                CheckoutStoreError,
                PaymentProviderError,
                ProviderCapabilityError,
                PaymentReconciliationError,
            ) as exc:
                logger.warning(
                    "Wallet top-up payment failed closed: payment_order_id=%s error=%s",
                    payment_order.id,
                    type(exc).__name__,
                )
                return self._fail_order(
                    db,
                    payment_order_id=payment_order.id,
                    reason="provider_or_token_failure",
                )
            except Exception as exc:
                logger.warning(
                    "Wallet top-up provider exception failed closed: payment_order_id=%s error=%s",
                    payment_order.id,
                    type(exc).__name__,
                )
                return self._fail_order(
                    db,
                    payment_order_id=payment_order.id,
                    reason="provider_or_token_failure",
                )

        if not invoice_id or not session_id or not checkout_session_id:
            # Legacy BE-5 fixtures may prepare an order before the hosted
            # checkout is attached.  It remains unpaid and is intentionally not
            # charged with guessed card data; BE-7 can create a fresh attempt.
            return self._result_from_order(payment_order)

        try:
            invoice_uuid = UUID(str(invoice_id))
            session_uuid = UUID(str(session_id))
        except (TypeError, ValueError, AttributeError):
            return self._fail_order(
                db,
                payment_order_id=payment_order.id,
                reason="Payment order business identifiers are invalid",
            )
        invoice = db.query(Invoice).filter(Invoice.id == invoice_uuid).first()
        session = db.query(ChargingSession).filter(ChargingSession.id == session_uuid).first()
        app_user = db.query(AppUser).filter(AppUser.id == payment_order.app_user_id).first()
        order = (
            db.query(Order)
            .filter(Order.session_id == session.id if session is not None else False)
            .first()
            if session is not None
            else None
        )
        if (
            invoice is None
            or session is None
            or app_user is None
            or (order is not None and order.app_user_id != app_user.id)
            or (order is not None and order.tenant_id != invoice.tenant_id)
            or session.tenant_id != invoice.tenant_id
            or (invoice.order_id is not None and (order is None or invoice.order_id != order.id))
            or (order is None and purpose is not PaymentPurpose.UNPAID_CHARGE)
        ):
            return self._fail_order(
                db,
                payment_order_id=payment_order.id,
                reason="Payment order business ownership is incomplete",
            )
        if Decimal(str(payment_order.amount)) != Decimal(str(invoice.total_amount)):
            return self._fail_order(
                db,
                payment_order_id=payment_order.id,
                reason="Payment order amount does not match invoice",
            )

        try:
            if UUID(str(metadata.get("operator_tenant_id"))) != invoice.tenant_id:
                return self._fail_order(
                    db,
                    payment_order_id=payment_order.id,
                    reason="Payment tenant ownership mismatch",
                )
        except (TypeError, ValueError, AttributeError):
            return self._fail_order(
                db,
                payment_order_id=payment_order.id,
                reason="Payment tenant snapshot is invalid",
            )

        try:
            merchant_context = self.merchant_context_for_order(
                payment_order=payment_order,
                purpose=purpose,
            )
            token = self._store().consume_card_token(checkout_session_id)
            metadata_hints = self._payment_order_provider_hints(
                db,
                payment_order,
                app_user.id,
            )
            hints = (
                metadata_hints
                if metadata_hints is not None
                else self._provider_hints(db, order, app_user.id)
            )
            hints = self._canonical_provider_hints(hints)
            charging_amount = Decimal(str(invoice.total_amount))
            charging_currency = payment_order.currency
            charging_provider = payment_order.payment_provider
            charging_order_type = payment_order.type
            charging_user_email = self._payer_email(app_user.email)
            charging_invoice_id = str(invoice.id)
            charging_session_id = str(session.id)
            charging_tenant_id = str(invoice.tenant_id)
            operation_key = self._begin_provider_operation(
                db,
                payment_order=payment_order,
                metadata=metadata,
            )
            provider = self._provider_registry.get(charging_provider)
            result = self._create_payment(
                provider,
                CreatePaymentCommand(
                    provider=charging_provider,
                    order_type=charging_order_type,
                    amount=charging_amount,
                    currency=charging_currency,
                    metadata={
                        "payment_purpose": purpose.value,
                        "invoice_id": charging_invoice_id,
                        "session_id": charging_session_id,
                        "operator_tenant_id": charging_tenant_id,
                    },
                    email=charging_user_email,
                    token=token,
                    payment_method_id=hints["provider_payment_method_id"],
                    idempotency_key=operation_key,
                    description="EsLatin charging payment",
                ),
                merchant_context=merchant_context,
                operation_key=operation_key,
            )
            return self.reconcile(
                db,
                payment_order_id=payment_order.id,
                status=result.status,
                provider_payment_id=result.provider_payment_id,
                external_reference=result.provider_order_ref,
                amount=charging_amount,
                currency=charging_currency,
                next_action_url=result.next_action_url or result.redirect_url,
            )
        except (PaymentProviderError, ProviderCapabilityError) as exc:
            recovery_attempt_id = metadata.get("recovery_attempt_id")
            if exc.retryable and recovery_attempt_id:
                try:
                    recovery_uuid = UUID(str(recovery_attempt_id))
                    from app.services.recovery_service import RecoveryService

                    RecoveryService().mark_unknown(
                        db,
                        attempt_id=recovery_uuid,
                        reason="provider_timeout_or_unknown",
                    )
                    payment_order.status = "processing"
                    payment_order.order_metadata = {
                        **dict(payment_order.order_metadata or {}),
                        "reconciliation_error": "provider_timeout_or_unknown",
                    }
                    db.commit()
                    return self._result_from_order(payment_order, api_status="processing")
                except Exception:
                    db.rollback()
            logger.warning(
                "Direct-card payment failed closed: payment_order_id=%s error=%s",
                payment_order.id,
                type(exc).__name__,
            )
            return self._fail_order(
                db,
                payment_order_id=payment_order.id,
                reason="provider_or_token_failure",
            )
        except (CheckoutStoreError, PaymentReconciliationError) as exc:
            logger.warning(
                "Direct-card payment failed closed: payment_order_id=%s error=%s",
                payment_order.id,
                type(exc).__name__,
            )
            return self._fail_order(
                db,
                payment_order_id=payment_order.id,
                reason="provider_or_token_failure",
            )
        except Exception as exc:
            logger.warning(
                "Direct-card provider exception failed closed: payment_order_id=%s error=%s",
                payment_order.id,
                type(exc).__name__,
            )
            return self._fail_order(
                db,
                payment_order_id=payment_order.id,
                reason="provider_or_token_failure",
            )

    def query_and_reconcile(self, db: Session, *, payment_order_id: UUID | str) -> ReconciliationResult:
        payment_order = db.query(PaymentOrder).filter(PaymentOrder.id == payment_order_id).first()
        if payment_order is None:
            raise PaymentReconciliationError("Payment order not found")
        provider = self._provider_registry.get(payment_order.payment_provider)
        provider_ref = (payment_order.order_metadata or {}).get("provider_reference")
        if not provider_ref:
            # Legacy P001 rows are read through the adapter-compatible field
            # until a future additive schema supplies a neutral column.
            provider_ref = payment_order.mercadopago_payment_id
        if not provider_ref:
            return self._result_from_order(payment_order)
        context = self.merchant_context_for_order(
            payment_order=payment_order,
            purpose=(
                PaymentPurpose.RECONCILIATION
                if payment_order.type == "charging"
                else PaymentPurpose.WALLET_TOP_UP
            ),
        )
        query_capability = getattr(provider, "query_payment", None)
        if callable(query_capability):
            canonical = query_capability(str(provider_ref), merchant_context=context)
            facts = ProviderPaymentStatus(
                status=self._legacy_status(canonical.status),
                provider_payment_id=canonical.provider_ref,
                external_reference=canonical.merchant_ref,
                amount=canonical.amount or Decimal(str(payment_order.amount)),
                currency=canonical.currency or payment_order.currency,
                next_action_url=(
                    canonical.next_action.url
                    if canonical.next_action and canonical.next_action.type == "open_url"
                    else None
                ),
            )
        else:
            facts = provider.get_payment_status(
                str(provider_ref),
                merchant_context=context,
            )
        return self.reconcile(
            db,
            payment_order_id=payment_order.id,
            status=facts.status,
            provider_payment_id=facts.provider_payment_id,
            external_reference=facts.external_reference,
            amount=facts.amount,
            currency=facts.currency,
            next_action_url=facts.next_action_url,
        )

    def reconcile(
        self,
        db: Session,
        *,
        payment_order_id: UUID | str,
        status: str,
        provider_payment_id: str | None,
        external_reference: str | None,
        amount: Decimal,
        currency: str,
        next_action_url: str | None = None,
    ) -> ReconciliationResult:
        order = (
            db.query(PaymentOrder)
            .filter(PaymentOrder.id == payment_order_id)
            .with_for_update()
            .one()
        )
        amount = Decimal(str(amount))
        if amount != Decimal(str(order.amount)) or currency.upper() != order.currency.upper():
            raise PaymentReconciliationError("Provider amount or currency mismatch")
        existing_provider_payment_id = (
            str(order.mercadopago_payment_id)
            if order.mercadopago_payment_id
            else None
        )
        if existing_provider_payment_id and provider_payment_id:
            if existing_provider_payment_id != str(provider_payment_id):
                raise PaymentReconciliationError("Provider payment ownership mismatch")
        if order.external_reference and external_reference:
            if str(order.external_reference) != str(external_reference):
                raise PaymentReconciliationError("Provider external reference mismatch")

        raw_status = str(status).lower()
        if raw_status == "provider_approved":
            raw_status = "approved"
        normalized = raw_status
        safe_action = self._validated_action(next_action_url)
        if normalized == "processing" and safe_action:
            normalized = "action_required"
        if normalized not in {
            "processing",
            "action_required",
            "approved",
            "declined",
            "expired",
            "error",
            "voided",
            "refunded",
            "unknown",
            "disputed",
            "mismatch",
        }:
            normalized = "error"
        if normalized == "approved" and not provider_payment_id:
            raise PaymentReconciliationError("Approved provider result has no payment id")
        if provider_payment_id:
            order.mercadopago_payment_id = str(provider_payment_id)
        if external_reference:
            order.external_reference = str(external_reference)
        metadata = dict(order.order_metadata or {})
        if provider_payment_id:
            # Canonical orchestration stores the opaque reference independently
            # of the legacy P001 projection column.
            metadata["provider_reference"] = str(provider_payment_id)
        metadata["provider_status"] = normalized
        if safe_action:
            metadata["next_action"] = {"type": "open_url", "url": safe_action}
        elif normalized not in {"processing", "action_required"}:
            metadata.pop("next_action", None)
        order.order_metadata = metadata

        old_status = order.status
        transition_applied = True
        target_status = "processing" if normalized == "action_required" else (
            "error" if normalized in {"unknown", "disputed", "mismatch"} else normalized
        )
        try:
            order.status = transition_status(old_status, target_status)
        except ValueError:
            # Late callbacks cannot roll back a terminal fact.  An approved
            # callback after another attempt already won is retained as a
            # provider fact but becomes an explicit exception below.
            order.status = old_status
            transition_applied = False
        if order.status != "processing":
            metadata.pop("next_action", None)
            order.order_metadata = metadata

        duplicate_approved = False
        duplicate_order_id = None
        invoice = self._invoice_for_order(db, order)
        session = self._session_for_order(db, order)
        recovery_attempt_id = metadata.get("recovery_attempt_id")
        recovery_applied = False
        if recovery_attempt_id:
            try:
                recovery_uuid = UUID(str(recovery_attempt_id))
            except (TypeError, ValueError, AttributeError) as exc:
                raise PaymentReconciliationError("Recovery attempt reference is invalid") from exc
            from app.services.recovery_service import RecoveryService

            duplicate_approved = RecoveryService().apply_card_result(
                db,
                attempt_id=recovery_uuid,
                payment_order_id=order.id,
                provider_status=(
                    "unknown" if normalized in {"unknown", "disputed", "mismatch"} else normalized
                ),
                provider_payment_ref=provider_payment_id,
                provider_amount=amount,
                provider_currency=currency,
            )
            recovery_applied = True
        if normalized == "approved" and order.status == "approved":
            order.paid_at = order.paid_at or datetime.now(timezone.utc)
            if recovery_applied:
                if duplicate_approved:
                    metadata["settlement_exception"] = "duplicate_approved"
                    metadata["settlement_exception_at"] = datetime.now(timezone.utc).isoformat()
                    metadata["refund_required"] = True
                    order.order_metadata = metadata
                    logger.error(
                        "Duplicate approved recovery requires manual review: payment_order_id=%s invoice_id=%s",
                        order.id,
                        invoice.id if invoice else None,
                    )
            elif invoice is not None and invoice.status == "paid":
                # The settlement response is reconciled synchronously before
                # Mercado Pago delivers its payment webhook.  If the webhook
                # carries the same provider payment ID already stored on this
                # order, it is the expected second observation of one charge,
                # not a second approved payment.  Only a different provider
                # payment ID remains a duplicate-payment/refund case.
                same_approved_payment = (
                    existing_provider_payment_id is not None
                    and provider_payment_id is not None
                    and existing_provider_payment_id == str(provider_payment_id)
                    and db.query(Payment)
                    .filter(
                        Payment.invoice_id == invoice.id,
                        Payment.transaction_id == str(provider_payment_id),
                        Payment.status == "completed",
                    )
                    .first()
                    is not None
                )
                if not same_approved_payment:
                    duplicate_approved = True
                    duplicate_order_id = order.id
                    metadata["settlement_exception"] = "duplicate_approved"
                    metadata["settlement_exception_at"] = datetime.now(timezone.utc).isoformat()
                    metadata["refund_required"] = True
                    order.order_metadata = metadata
                    logger.error(
                        "Duplicate approved payment requires refund or manual review: payment_order_id=%s invoice_id=%s",
                        order.id,
                        invoice.id,
                    )
                else:
                    logger.info(
                        "Repeated approved provider fact is idempotent: payment_order_id=%s provider_payment_id=%s",
                        order.id,
                        provider_payment_id,
                    )
            elif invoice is not None and session is not None:
                from app.services.billing_service import BillingService

                BillingService._complete_direct_card(
                    db,
                    invoice=invoice,
                    session=session,
                    order=self._business_order_for_session(db, session),
                    payment_order=order,
                    now=datetime.now(timezone.utc),
                )
            elif order.type == "top_up":
                app_user = db.query(AppUser).filter(
                    AppUser.id == order.app_user_id
                ).with_for_update().one()
                ledger_id = f"payment_topup_{order.id}"
                if db.query(AppWalletTransaction).filter(
                    AppWalletTransaction.transaction_number == ledger_id
                ).first() is None:
                    tenant = db.query(Tenant).order_by(Tenant.created_at.asc()).first()
                    if tenant is None:
                        raise PaymentReconciliationError("No operator tenant for top-up")
                    app_user.balance = Decimal(str(app_user.balance or 0)) + Decimal(str(order.amount))
                    db.add(AppWalletTransaction(
                        transaction_number=ledger_id,
                        app_user_id=app_user.id,
                        payment_order_id=order.id,
                        operator_tenant_id=tenant.id,
                        type="top_up",
                        amount=Decimal(str(order.amount)),
                        description="Wallet top-up",
                    ))
        elif transition_applied and normalized in {
            "declined",
            "expired",
            "error",
            "voided",
            "unknown",
            "disputed",
            "mismatch",
        }:
            if session is not None and session.payment_status != "paid":
                session.payment_status = "unpaid"
                session.payment_order_id = order.id
        elif transition_applied:
            if session is not None and session.payment_status != "paid":
                session.payment_status = "pending"
                session.payment_order_id = order.id

        projected_api_status = (
            "action_required"
            if normalized == "action_required" and order.status == "processing" and safe_action
            else order.status
        )
        self._publish_checkout_projection(
            order,
            api_status=projected_api_status,
            next_action=metadata.get("next_action"),
        )
        if not recovery_applied:
            from app.services.financial_eligibility import enqueue_financial_eligibility_recheck

            tenant_id = invoice.tenant_id if invoice is not None else None
            if tenant_id is None:
                tenant_value = (order.order_metadata or {}).get("operator_tenant_id")
                try:
                    tenant_id = UUID(str(tenant_value)) if tenant_value else None
                except (TypeError, ValueError, AttributeError):
                    tenant_id = None
            enqueue_financial_eligibility_recheck(
                db,
                app_user_id=order.app_user_id,
                tenant_id=tenant_id,
                source_type="payment_reconciliation",
                source_id=order.id,
                source_version=f"{order.status}:{normalized}:{provider_payment_id or ''}",
                reason_code="payment_fact_changed",
            )
        db.commit()
        if duplicate_order_id is not None and not recovery_applied:
            # Preserve BE-6's safe duplicate-approved marker even when the
            # provider cannot be refunded automatically.  The refund service
            # serializes the provider fact check and records manual review.
            try:
                from app.services.payment_refunds import PaymentRefundService

                PaymentRefundService(reconciliation=self).refund_payment_order(
                    db,
                    payment_order_id=duplicate_order_id,
                    amount=None,
                    idempotency_key=f"duplicate-approved:{duplicate_order_id}",
                )
            except Exception as exc:
                logger.error(
                    "Duplicate approved refund requires manual review: payment_order_id=%s error=%s",
                    duplicate_order_id,
                    type(exc).__name__,
                )
        return ReconciliationResult(
            order_status=order.status,
            api_status=projected_api_status,
            payment_order_id=str(order.id),
            duplicate_approved=duplicate_approved,
            next_action=metadata.get("next_action"),
        )

    def _fail_order(self, db: Session, *, payment_order_id: UUID, reason: str) -> ReconciliationResult:
        order = db.query(PaymentOrder).filter(PaymentOrder.id == payment_order_id).first()
        if order is None:
            raise PaymentReconciliationError("Payment order not found")
        metadata = dict(order.order_metadata or {})
        metadata["reconciliation_error"] = reason
        order.order_metadata = metadata
        order.status = "error" if order.status in {"created", "processing"} else order.status
        session = self._session_for_order(db, order)
        if session is not None and session.payment_status != "paid":
            session.payment_status = "unpaid"
            session.payment_order_id = order.id
        self._publish_checkout_projection(order, api_status="error", next_action=None)
        db.commit()
        return self._result_from_order(order, api_status="error")

    @staticmethod
    def _invoice_for_order(db: Session, order: PaymentOrder) -> Invoice | None:
        invoice_id = (order.order_metadata or {}).get("invoice_id")
        if not invoice_id:
            return None
        try:
            invoice_uuid = UUID(str(invoice_id))
        except (TypeError, ValueError, AttributeError):
            return None
        return db.query(Invoice).filter(Invoice.id == invoice_uuid).with_for_update().first()

    @staticmethod
    def _session_for_order(db: Session, order: PaymentOrder) -> ChargingSession | None:
        session_id = (order.order_metadata or {}).get("session_id")
        if not session_id:
            return None
        try:
            session_uuid = UUID(str(session_id))
        except (TypeError, ValueError, AttributeError):
            return None
        return db.query(ChargingSession).filter(ChargingSession.id == session_uuid).with_for_update().first()

    @staticmethod
    def _business_order_for_session(db: Session, session: ChargingSession) -> Order | None:
        return db.query(Order).filter(Order.session_id == session.id).with_for_update().first()

    def _validated_action(self, url: str | None) -> str | None:
        if not isinstance(url, str) or len(url) > 2048:
            return None
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        hosts = {
            item.strip().lower().lstrip(".")
            for item in self._settings.checkout_next_action_host_allowlist.split(",")
            if item.strip()
        }
        hostname = parsed.hostname.lower()
        if any(hostname == host or hostname.endswith("." + host) for host in hosts):
            return url
        return None

    def _publish_checkout_projection(
        self,
        order: PaymentOrder,
        *,
        api_status: str,
        next_action: Mapping[str, str] | None,
    ) -> None:
        checkout_id = self._checkout_session_id(order)
        if not checkout_id:
            return
        try:
            from app.services.payment_checkout.models import CheckoutSessionStatus

            target = CheckoutSessionStatus(api_status)
            record = self._store().get(checkout_id)
            results = dict(record.data.get("results") or {})
            results["payment_order_id"] = str(order.id)
            self._store().update_record(checkout_id, status=target, results=results)
        except Exception:
            # Redis is a projection only.  Provider/DB facts must still commit.
            logger.warning(
                "Unable to publish checkout payment projection: payment_order_id=%s error=%s",
                order.id,
                "checkout_projection_unavailable",
            )

    @staticmethod
    def _result_from_order(
        order: PaymentOrder,
        *,
        api_status: str | None = None,
    ) -> ReconciliationResult:
        metadata = order.order_metadata or {}
        return ReconciliationResult(
            order_status=order.status,
            api_status=api_status or str(metadata.get("provider_status") or order.status),
            payment_order_id=str(order.id),
            next_action=metadata.get("next_action"),
        )
