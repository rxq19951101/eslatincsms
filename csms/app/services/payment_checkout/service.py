"""Application service for creating and reading secure checkout sessions."""

from __future__ import annotations

import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Callable
from urllib.parse import urlencode, urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.models import (
    AppUserPaymentMethod,
    ChargePoint,
    ChargingSession,
    EVSE,
    Invoice,
    Order,
    PaymentOrder,
    Site,
)
from app.services.charging_payment_intent import (
    PaymentIntentError,
    create_payment_intent_data,
    find_intent_order,
)
from app.services.payment_checkout.models import (
    CheckoutSessionRecord,
    CheckoutSessionStatus,
)
from app.services.payment_checkout.redis_store import (
    CheckoutIdempotencyConflict,
    CheckoutSessionCorrupt,
    CheckoutSessionNotFound,
    CheckoutSessionStore,
    CheckoutStoreError,
    CheckoutStoreUnavailable,
    CheckoutTokenAlreadyStored,
    CheckoutTransitionConflict,
)
from app.services.payment_checkout.signing import CheckoutSigningError, CheckoutURLSigner
from app.services.payment_providers.merchant_context import (
    MerchantAccountResolver,
    MerchantContextError,
    PaymentPurpose,
    PlatformMerchantAccountResolver,
)
from app.services.pricing_service import PricingMode, PricingService
from app.services.payment_methods import PaymentMethodService, PaymentMethodServiceError
from app.services.payment_method_codec import (
    SUPPORTED_PAYMENT_TYPES,
    decode_payment_method_brand,
)
from app.services.payment_providers.mercadopago_provider import MercadoPagoProvider
from app.services.payment_reconciliation import (
    PaymentReconciliationError,
    PaymentReconciliationService,
)
from app.services.runtime_rail_control import RailClosed, RailStateUnknown, RuntimeRailControlService


class PaymentMethodMode(str, Enum):
    NEW_CARD = "new_card"
    SAVED_CARD = "saved_card"


class CheckoutServiceError(RuntimeError):
    code = "CHECKOUT_ERROR"
    status_code = 500
    public_message = "Unable to process the checkout session."


class CheckoutRequestInvalid(CheckoutServiceError):
    code = "CHECKOUT_REQUEST_INVALID"
    status_code = 400
    public_message = "The checkout request is invalid."


class CheckoutTargetNotFound(CheckoutServiceError):
    code = "CHECKOUT_TARGET_NOT_FOUND"
    status_code = 404
    public_message = "The requested payment target was not found."


class CheckoutSessionMissing(CheckoutServiceError):
    code = "CHECKOUT_SESSION_NOT_FOUND"
    status_code = 404
    public_message = "Checkout session not found."


class CheckoutRequestConflict(CheckoutServiceError):
    code = "CHECKOUT_IDEMPOTENCY_CONFLICT"
    status_code = 409
    public_message = "The idempotency key was already used for another request."


class CheckoutServiceUnavailable(CheckoutServiceError):
    code = "CHECKOUT_UNAVAILABLE"
    status_code = 503
    public_message = "Checkout is temporarily unavailable."


class CheckoutRailClosed(CheckoutServiceError):
    code = "RAIL_CLOSED"
    status_code = 503
    public_message = "The payment rail is closed."


class CheckoutRailStateUnknown(CheckoutServiceError):
    code = "RAIL_STATE_UNKNOWN"
    status_code = 503
    public_message = "The payment rail state is temporarily unknown."


class CheckoutAlreadyConfirmed(CheckoutServiceError):
    code = "CHECKOUT_ALREADY_CONFIRMED"
    status_code = 409
    public_message = "This checkout session has already been confirmed."


@dataclass(frozen=True)
class CreateCheckoutSessionCommand:
    purpose: PaymentPurpose
    payment_method_mode: PaymentMethodMode
    saved_payment_method_id: UUID | None
    save_card: bool
    amount: Decimal | None
    currency: str
    charge_point_id: UUID | None
    connector_id: int | None
    session_id: UUID | None
    return_url: str
    idempotency_key: str
    recovery_attempt_id: UUID | None = None


@dataclass(frozen=True)
class CheckoutSessionCreated:
    checkout_session_id: str
    checkout_url: str
    expires_at: datetime
    purpose: PaymentPurpose
    reused: bool
    recovery_attempt_id: str | None = None


@dataclass(frozen=True)
class CheckoutSessionView:
    id: str
    purpose: PaymentPurpose
    status: CheckoutSessionStatus
    payment_intent_id: str | None
    payment_order_id: str | None
    saved_payment_method_id: str | None
    next_action: dict[str, str] | None
    expires_at: datetime
    recovery_attempt_id: str | None = None


@dataclass(frozen=True)
class HostedCheckoutPage:
    checkout_session_id: str
    purpose: PaymentPurpose
    payment_method_mode: PaymentMethodMode
    save_card: bool
    amount: str | None
    public_key: str
    saved_provider_card_id: str | None
    saved_card_brand: str | None
    saved_card_payment_type: str | None
    saved_card_last_four: str | None
    return_url: str


@dataclass(frozen=True)
class ConfirmCheckoutSessionCommand:
    card_token: str
    payment_method_id: str | None
    payment_type_id: str | None
    issuer_id: str | None
    installments: int


@dataclass(frozen=True)
class CheckoutSessionConfirmed:
    checkout_session_id: str
    purpose: PaymentPurpose
    status: CheckoutSessionStatus
    redirect_url: str


_CARD_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._-]{16,2048}$")
_PROVIDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class CheckoutSessionService:
    """Validate trusted payment targets before writing short-lived Redis state."""

    def __init__(
        self,
        *,
        store: CheckoutSessionStore,
        signer: CheckoutURLSigner,
        merchant_resolver: MerchantAccountResolver | None = None,
        settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
        payment_method_service: PaymentMethodService | None = None,
    ) -> None:
        self._store = store
        self._signer = signer
        self._merchant_resolver = merchant_resolver or PlatformMerchantAccountResolver()
        self._settings = settings or get_settings()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._payment_method_service = payment_method_service
        self._return_urls = {
            item.strip()
            for item in self._settings.checkout_return_url_allowlist.split(",")
            if item.strip()
        }
        if not self._return_urls:
            raise CheckoutServiceUnavailable("Checkout return URL allowlist is empty")
        self._next_action_hosts = {
            item.strip().lower().lstrip(".")
            for item in self._settings.checkout_next_action_host_allowlist.split(",")
            if item.strip()
        }
        if not self._next_action_hosts:
            raise CheckoutServiceUnavailable("Checkout next-action allowlist is empty")
        self._public_base_url = self._validate_public_base_url(
            self._settings.public_api_base_url
        )

    def create(
        self,
        db: Session,
        *,
        app_user_id: UUID,
        command: CreateCheckoutSessionCommand,
    ) -> CheckoutSessionCreated:
        self._validate_token_purpose(command)
        now = self._now()
        client_subject = self._client_subject(command)
        fingerprint = self._store.request_fingerprint(client_subject)
        try:
            existing = self._store.get_by_idempotency(
                app_user_id=str(app_user_id),
                idempotency_key=command.idempotency_key,
                request_fingerprint=fingerprint,
            )
        except CheckoutIdempotencyConflict as exc:
            raise CheckoutRequestConflict("Checkout idempotency conflict") from exc
        except (CheckoutStoreUnavailable, CheckoutSessionCorrupt) as exc:
            raise CheckoutServiceUnavailable("Checkout state is unavailable") from exc
        except CheckoutStoreError as exc:
            raise CheckoutServiceUnavailable("Unable to read checkout idempotency state") from exc
        if existing is not None:
            return self._created_response(existing, reused=True)

        data, operator_tenant_id = self._validated_session_data(
            db,
            app_user_id=app_user_id,
            command=command,
        )
        try:
            merchant_context = self._merchant_resolver.resolve(
                operator_tenant_id=operator_tenant_id,
                payment_purpose=command.purpose,
            )
        except MerchantContextError as exc:
            raise CheckoutServiceUnavailable("Unable to resolve checkout merchant") from exc

        nonce = secrets.token_urlsafe(18)
        data["merchant"] = merchant_context.safe_snapshot()
        data["operator_tenant_id"] = (
            str(operator_tenant_id) if operator_tenant_id is not None else None
        )
        data["signing_nonce"] = nonce
        data["results"] = {
            "payment_intent_id": None,
            "payment_order_id": None,
            "saved_payment_method_id": None,
        }
        record = CheckoutSessionRecord(
            opaque_id=secrets.token_urlsafe(24),
            app_user_id=str(app_user_id),
            purpose=command.purpose,
            status=CheckoutSessionStatus.CREATED,
            request_fingerprint=fingerprint,
            created_at=now,
            expires_at=now
            + timedelta(seconds=self._settings.checkout_session_ttl_seconds),
            data=data,
        )
        try:
            saved = self._store.save(
                record,
                idempotency_key=command.idempotency_key,
            )
        except CheckoutIdempotencyConflict as exc:
            raise CheckoutRequestConflict("Checkout idempotency conflict") from exc
        except (CheckoutStoreUnavailable, CheckoutSessionCorrupt) as exc:
            raise CheckoutServiceUnavailable("Checkout state is unavailable") from exc
        except CheckoutStoreError as exc:
            raise CheckoutServiceUnavailable("Unable to create checkout session") from exc

        return self._created_response(saved.record, reused=saved.reused)

    def _created_response(
        self,
        persisted: CheckoutSessionRecord,
        *,
        reused: bool,
    ) -> CheckoutSessionCreated:
        persisted_nonce = persisted.data.get("signing_nonce")
        if not isinstance(persisted_nonce, str):
            raise CheckoutServiceUnavailable("Checkout signing state is unavailable")
        try:
            signed_token = self._signer.sign(
                opaque_id=persisted.opaque_id,
                expires_at=persisted.expires_at,
                nonce=persisted_nonce,
            )
        except CheckoutSigningError as exc:
            raise CheckoutServiceUnavailable("Unable to sign checkout URL") from exc
        return CheckoutSessionCreated(
            checkout_session_id=persisted.opaque_id,
            checkout_url=(
                f"{self._public_base_url}/api/v1/app/payments/checkout/{signed_token}"
            ),
            expires_at=persisted.expires_at,
            purpose=persisted.purpose,
            reused=reused,
            recovery_attempt_id=(
                str(persisted.data["recovery_attempt_id"])
                if persisted.data.get("recovery_attempt_id")
                else None
            ),
        )

    def get(self, *, app_user_id: UUID, checkout_session_id: str) -> CheckoutSessionView:
        try:
            record = self._store.get(checkout_session_id)
        except CheckoutSessionNotFound as exc:
            raise CheckoutSessionMissing("Checkout session not found") from exc
        except (CheckoutStoreUnavailable, CheckoutSessionCorrupt) as exc:
            raise CheckoutServiceUnavailable("Checkout state is unavailable") from exc
        except CheckoutStoreError as exc:
            raise CheckoutServiceUnavailable("Unable to read checkout session") from exc
        if record.app_user_id != str(app_user_id):
            raise CheckoutSessionMissing("Checkout session not found")

        results = record.data.get("results")
        if not isinstance(results, dict):
            results = {}
        next_action = None
        if record.status is CheckoutSessionStatus.ACTION_REQUIRED:
            candidate = record.data.get("next_action")
            if (
                isinstance(candidate, dict)
                and candidate.get("type") == "open_url"
                and isinstance(candidate.get("url"), str)
            ):
                next_action = {
                    "type": "open_url",
                    "url": self._validated_next_action_url(candidate["url"]),
                }
            else:
                raise CheckoutServiceUnavailable(
                    "Checkout next action is unavailable"
                )
        return CheckoutSessionView(
            id=record.opaque_id,
            purpose=record.purpose,
            status=record.status,
            payment_intent_id=self._optional_string(results.get("payment_intent_id")),
            payment_order_id=self._optional_string(results.get("payment_order_id")),
            saved_payment_method_id=self._optional_string(
                results.get("saved_payment_method_id")
            ),
            next_action=next_action,
            expires_at=record.expires_at,
            recovery_attempt_id=(
                str(record.data["recovery_attempt_id"])
                if record.data.get("recovery_attempt_id")
                else None
            ),
        )

    def get_hosted_page(
        self,
        db: Session,
        *,
        signed_token: str,
    ) -> HostedCheckoutPage:
        record = self._verified_record(signed_token)
        if record.status is not CheckoutSessionStatus.CREATED:
            raise CheckoutAlreadyConfirmed("Checkout session is not confirmable")
        try:
            payment_method_mode = PaymentMethodMode(
                str(record.data["payment_method_mode"])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CheckoutServiceUnavailable(
                "Checkout payment method state is unavailable"
            ) from exc

        save_card = record.data.get("save_card")
        if not isinstance(save_card, bool):
            raise CheckoutServiceUnavailable("Checkout card purpose is unavailable")
        if record.purpose is PaymentPurpose.SAVE_CARD:
            if payment_method_mode is not PaymentMethodMode.NEW_CARD or not save_card:
                raise CheckoutServiceUnavailable("Checkout card purpose is unavailable")
        elif save_card:
            raise CheckoutServiceUnavailable("Checkout card purpose is unavailable")

        public_key = self._settings.mercadopago_public_key.get_secret_value().strip()
        if not public_key:
            raise CheckoutServiceUnavailable("Mercado Pago public key is unavailable")

        provider_card_id = None
        card_brand = None
        card_payment_type = None
        card_last_four = None
        if payment_method_mode is PaymentMethodMode.SAVED_CARD:
            payment_method = self._saved_payment_method(db, record)
            provider_card_id = (payment_method.mp_card_id or "").strip()
            if not provider_card_id or not _PROVIDER_ID_PATTERN.fullmatch(
                provider_card_id
            ):
                raise CheckoutServiceUnavailable(
                    "Saved payment method provider state is unavailable"
                )
            decoded_card = decode_payment_method_brand(
                payment_method.payment_method_brand
            )
            card_brand = self._optional_safe_label(
                decoded_card.brand,
                maximum=64,
            )
            if decoded_card.payment_type in SUPPORTED_PAYMENT_TYPES:
                card_payment_type = decoded_card.payment_type
            card_last_four = self._optional_safe_label(
                payment_method.last_four, maximum=4
            )

        return_url = record.data.get("return_url")
        if not isinstance(return_url, str) or return_url not in self._return_urls:
            raise CheckoutServiceUnavailable("Checkout return URL is unavailable")

        return HostedCheckoutPage(
            checkout_session_id=record.opaque_id,
            purpose=record.purpose,
            payment_method_mode=payment_method_mode,
            save_card=save_card,
            amount=(
                str(record.data["amount"])
                if isinstance(record.data.get("amount"), str)
                else None
            ),
            public_key=public_key,
            saved_provider_card_id=provider_card_id,
            saved_card_brand=card_brand,
            saved_card_payment_type=card_payment_type,
            saved_card_last_four=card_last_four,
            return_url=return_url,
        )

    def confirm(
        self,
        db: Session,
        *,
        signed_token: str,
        command: ConfirmCheckoutSessionCommand,
    ) -> CheckoutSessionConfirmed:
        record = self._verified_record(signed_token)
        if record.status is not CheckoutSessionStatus.CREATED:
            raise CheckoutAlreadyConfirmed("Checkout session is not confirmable")
        if not _CARD_TOKEN_PATTERN.fullmatch(command.card_token):
            raise CheckoutRequestInvalid("Invalid provider card token")
        if command.installments != 1:
            raise CheckoutRequestInvalid("Installments are not supported")

        try:
            payment_method_mode = PaymentMethodMode(
                str(record.data["payment_method_mode"])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CheckoutServiceUnavailable(
                "Checkout payment method state is unavailable"
            ) from exc

        provider_hints: dict[str, object] = {"installments": 1}
        if payment_method_mode is PaymentMethodMode.SAVED_CARD:
            if any(
                value is not None
                for value in (
                    command.payment_method_id,
                    command.payment_type_id,
                    command.issuer_id,
                )
            ):
                raise CheckoutRequestInvalid(
                    "Saved payment method facts cannot be overridden"
                )
            self._saved_payment_method(db, record)
            provider_hints["selected_payment_method_id"] = record.data.get(
                "selected_payment_method_id"
            )
        else:
            if (
                command.payment_method_id is None
                or not _PROVIDER_ID_PATTERN.fullmatch(command.payment_method_id)
                or command.payment_type_id not in SUPPORTED_PAYMENT_TYPES
            ):
                raise CheckoutRequestInvalid("Invalid provider payment method")
            provider_hints["payment_method_id"] = command.payment_method_id
            provider_hints["payment_type_id"] = command.payment_type_id
            if command.issuer_id is not None:
                if not _PROVIDER_ID_PATTERN.fullmatch(command.issuer_id):
                    raise CheckoutRequestInvalid("Invalid provider issuer")
                provider_hints["issuer_id"] = command.issuer_id

        confirmation = {
            "confirmed_at": self._now().isoformat(),
            "purpose_result_route": self._purpose_result_route(record.purpose),
            "save_card": bool(record.data.get("save_card", False)),
            "provider_hints": provider_hints,
        }
        try:
            confirmed = self._store.confirm(
                record.opaque_id,
                card_token=command.card_token,
                confirmation=confirmation,
            )
        except (CheckoutTokenAlreadyStored, CheckoutTransitionConflict) as exc:
            raise CheckoutAlreadyConfirmed("Checkout session is not confirmable") from exc
        except CheckoutSessionNotFound as exc:
            raise CheckoutSessionMissing("Checkout session not found") from exc
        except (CheckoutStoreUnavailable, CheckoutSessionCorrupt) as exc:
            raise CheckoutServiceUnavailable("Checkout state is unavailable") from exc
        except CheckoutStoreError as exc:
            raise CheckoutServiceUnavailable("Unable to confirm checkout session") from exc

        if confirmed.purpose is PaymentPurpose.WALLET_TOP_UP:
            try:
                payment_order = self._create_wallet_top_up_payment_order(
                    db,
                    confirmed=confirmed,
                )
                db.add(payment_order)
                db.commit()

                PaymentReconciliationService().start_payment_order(
                    db,
                    payment_order_id=payment_order.id,
                )
                confirmed = self._store.get(confirmed.opaque_id)
            except (
                CheckoutStoreError,
                CheckoutServiceUnavailable,
                PaymentReconciliationError,
                ValueError,
            ) as exc:
                db.rollback()
                try:
                    self._store().transition(
                        confirmed.opaque_id, CheckoutSessionStatus.ERROR
                    )
                except CheckoutStoreError:
                    pass
                raise CheckoutServiceUnavailable(
                    "Unable to create wallet top-up payment"
                ) from exc
            except RailStateUnknown as exc:
                db.rollback()
                raise CheckoutRailStateUnknown(str(exc)) from exc
            except RailClosed as exc:
                db.rollback()
                raise CheckoutRailClosed(str(exc)) from exc

        if confirmed.purpose is PaymentPurpose.SAVE_CARD:
            try:
                card_token = self._store.consume_card_token(confirmed.opaque_id)
                payment_method_service = self._payment_method_service
                if payment_method_service is None:
                    payment_method_service = PaymentMethodService(
                        provider=MercadoPagoProvider()
                    )
                saved = payment_method_service.save_card(
                    db,
                    app_user_id=UUID(confirmed.app_user_id),
                    token=card_token,
                    idempotency_key=f"checkout:{confirmed.opaque_id}",
                    payment_method_id=command.payment_method_id,
                    payment_type_id=command.payment_type_id,
                )
                confirmed = self._store.update_record(
                    confirmed.opaque_id,
                    status=CheckoutSessionStatus.APPROVED,
                    results={"saved_payment_method_id": saved.id},
                )
            except (
                CheckoutStoreError,
                PaymentMethodServiceError,
                ValueError,
            ) as exc:
                try:
                    self._store.transition(
                        confirmed.opaque_id, CheckoutSessionStatus.ERROR
                    )
                except CheckoutStoreError:
                    pass
                raise CheckoutServiceUnavailable(
                    "Unable to save payment method"
                ) from exc

        if confirmed.purpose is PaymentPurpose.CHARGING_DIRECT:
            try:
                intent_order, intent_id = self._create_charging_payment_intent(
                    db,
                    confirmed=confirmed,
                )
                results = dict(confirmed.data.get("results") or {})
                results["payment_intent_id"] = intent_id
                confirmed = self._store.update_record(
                    confirmed.opaque_id,
                    status=CheckoutSessionStatus.READY,
                    results=results,
                )
            except (
                CheckoutStoreError,
                PaymentIntentError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                try:
                    self._store.transition(
                        confirmed.opaque_id, CheckoutSessionStatus.ERROR
                    )
                except CheckoutStoreError:
                    pass
                raise CheckoutServiceUnavailable(
                    "Unable to create charging payment intent"
                ) from exc

        if confirmed.purpose is PaymentPurpose.UNPAID_CHARGE:
            try:
                payment_order = self._create_unpaid_payment_order(
                    db,
                    confirmed=confirmed,
                )
                db.commit()
                result = PaymentReconciliationService().start_payment_order(
                    db,
                    payment_order_id=payment_order.id,
                )
                current = self._store().get(confirmed.opaque_id)
                results = dict(current.data.get("results") or {})
                results["payment_order_id"] = str(payment_order.id)
                checkout_status = {
                    "processing": CheckoutSessionStatus.PROCESSING,
                    "action_required": CheckoutSessionStatus.ACTION_REQUIRED,
                    "approved": CheckoutSessionStatus.APPROVED,
                    "declined": CheckoutSessionStatus.DECLINED,
                    "expired": CheckoutSessionStatus.EXPIRED,
                    "error": CheckoutSessionStatus.ERROR,
                }.get(result.api_status, CheckoutSessionStatus.PROCESSING)
                confirmed = self._store().update_record(
                    confirmed.opaque_id,
                    status=checkout_status,
                    results=results,
                )
            except (
                CheckoutStoreError,
                CheckoutTargetNotFound,
                CheckoutServiceUnavailable,
                PaymentIntentError,
                ValueError,
            ) as exc:
                try:
                    self._store().transition(
                        confirmed.opaque_id, CheckoutSessionStatus.ERROR
                    )
                except CheckoutStoreError:
                    pass
                raise CheckoutServiceUnavailable(
                    "Unable to create unpaid-charge payment"
                ) from exc
            except RailStateUnknown as exc:
                db.rollback()
                raise CheckoutRailStateUnknown(str(exc)) from exc
            except RailClosed as exc:
                db.rollback()
                raise CheckoutRailClosed(str(exc)) from exc

        return CheckoutSessionConfirmed(
            checkout_session_id=confirmed.opaque_id,
            purpose=confirmed.purpose,
            status=confirmed.status,
            redirect_url=self._deep_link_redirect(confirmed),
        )

    def _create_wallet_top_up_payment_order(
        self,
        db: Session,
        *,
        confirmed: CheckoutSessionRecord,
    ) -> PaymentOrder:
        data = confirmed.data
        try:
            amount = self._money(Decimal(str(data["amount"])))
            currency = str(data["currency"]).upper()
            merchant = data["merchant"]
            confirmation = data["confirmation"]
            provider_hints = confirmation["provider_hints"]
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise CheckoutServiceUnavailable(
                "Wallet top-up payment state is incomplete"
            ) from exc

        if currency != "COP":
            raise CheckoutServiceUnavailable("Wallet top-up currency is invalid")
        if not isinstance(merchant, dict) or not isinstance(provider_hints, dict):
            raise CheckoutServiceUnavailable("Wallet top-up merchant state is invalid")
        tenant_id = None
        if data.get("operator_tenant_id"):
            try:
                tenant_id = UUID(str(data["operator_tenant_id"]))
            except (TypeError, ValueError) as exc:
                raise CheckoutServiceUnavailable("Wallet top-up tenant state is invalid") from exc
        try:
            RuntimeRailControlService.require_payment_creation_open(
                db, provider=str(merchant.get("provider") or "mercadopago"), tenant_id=tenant_id
            )
        except RailClosed:
            raise
        except RailStateUnknown:
            raise

        now = self._now()
        return PaymentOrder(
            app_user_id=UUID(confirmed.app_user_id),
            type="top_up",
            amount=amount,
            currency=currency,
            payment_provider="mercadopago",
            idempotency_key=f"checkout:{confirmed.opaque_id}",
            status="created",
            expires_at=confirmed.expires_at,
            payment_deadline_at=None,
            order_metadata={
                "schema_version": 1,
                "payment_purpose": PaymentPurpose.WALLET_TOP_UP.value,
                "checkout_session_id": confirmed.opaque_id,
                "operator_tenant_id": data.get("operator_tenant_id"),
                "merchant": merchant,
                "provider_hints": provider_hints,
                "created_at": now.isoformat(),
            },
        )

    def _create_unpaid_payment_order(
        self,
        db: Session,
        *,
        confirmed: CheckoutSessionRecord,
    ) -> PaymentOrder:
        """Create one independent direct-card retry from the Invoice fact."""
        data = confirmed.data
        try:
            app_user_id = UUID(confirmed.app_user_id)
            session_id = UUID(str(data["session_id"]))
            invoice_id = UUID(str(data["invoice_id"]))
            tenant_id = UUID(str(data["operator_tenant_id"]))
            merchant = data["merchant"]
            amount = Decimal(str(data["amount"])).quantize(Decimal("0.01"))
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise CheckoutServiceUnavailable("Unpaid-charge payment state is invalid") from exc
        if not isinstance(merchant, dict) or merchant.get("provider") != "mercadopago":
            raise CheckoutServiceUnavailable("Unpaid-charge merchant state is invalid")
        session = db.query(ChargingSession).filter(
            ChargingSession.id == session_id,
            ChargingSession.app_user_id == app_user_id,
            ChargingSession.tenant_id == tenant_id,
            ChargingSession.payment_status == "unpaid",
        ).with_for_update().first()
        invoice = db.query(Invoice).filter(
            Invoice.id == invoice_id,
            Invoice.session_id == session_id,
            Invoice.tenant_id == tenant_id,
            Invoice.status == "pending",
        ).with_for_update().first()
        if session is None or invoice is None or amount != Decimal(str(invoice.total_amount)):
            raise CheckoutTargetNotFound("Unpaid charging invoice not found")
        if amount <= Decimal("0.00"):
            raise CheckoutTargetNotFound("Unpaid charging invoice not found")
        site_id = db.query(ChargePoint.site_id).filter(
            ChargePoint.id == session.charge_point_id,
            ChargePoint.tenant_id == session.tenant_id,
        ).scalar()
        RuntimeRailControlService.require_payment_creation_open(
            db, provider="mercadopago", tenant_id=tenant_id, site_id=site_id
        )

        raw_provider_hints = (data.get("confirmation") or {}).get("provider_hints") or {}
        if not isinstance(raw_provider_hints, dict):
            raise CheckoutServiceUnavailable("Unpaid-charge provider state is invalid")
        provider_hints = {}
        if raw_provider_hints.get("payment_method_id") is not None:
            provider_hints["provider_payment_method_id"] = raw_provider_hints[
                "payment_method_id"
            ]
        if raw_provider_hints.get("payment_type_id") is not None:
            provider_hints["provider_payment_type_id"] = raw_provider_hints[
                "payment_type_id"
            ]
        if data.get("payment_method_mode") == PaymentMethodMode.SAVED_CARD.value:
            selected_id = data.get("selected_payment_method_id")
            saved = db.query(AppUserPaymentMethod).filter(
                AppUserPaymentMethod.id == selected_id,
                AppUserPaymentMethod.app_user_id == app_user_id,
                AppUserPaymentMethod.provider == "mercadopago",
            ).first()
            if saved is None:
                raise CheckoutTargetNotFound("Saved payment method not found")
            descriptor = decode_payment_method_brand(saved.payment_method_brand)
            provider_hints["provider_payment_method_id"] = descriptor.brand
            provider_hints["provider_payment_type_id"] = descriptor.payment_type

        recovery_attempt_id = data.get("recovery_attempt_id")
        if recovery_attempt_id:
            idempotency_key = f"unpaid-charge:{invoice.id}:{recovery_attempt_id}"
        else:
            idempotency_key = f"unpaid-charge:{invoice.id}:{confirmed.opaque_id}"
        existing = db.query(PaymentOrder).filter(
            PaymentOrder.app_user_id == app_user_id,
            PaymentOrder.idempotency_key == idempotency_key,
        ).with_for_update().first()
        if existing is not None:
            if Decimal(str(existing.amount)) != amount:
                raise CheckoutServiceUnavailable("Unpaid-charge payment amount mismatch")
            metadata = dict(existing.order_metadata or {})
            metadata.update(
                {
                    "checkout_session_id": confirmed.opaque_id,
                    "provider_hints": provider_hints,
                }
            )
            existing.order_metadata = metadata
            db.flush()
            return existing
        now = self._now()
        order = PaymentOrder(
            app_user_id=app_user_id,
            type="charging",
            amount=amount,
            currency="COP",
            payment_provider="mercadopago",
            idempotency_key=idempotency_key,
            status="created",
            expires_at=now + timedelta(minutes=30),
            payment_deadline_at=now + timedelta(minutes=60),
            order_metadata={
                "schema_version": 1,
                "payment_purpose": PaymentPurpose.UNPAID_CHARGE.value,
                "settlement_method": "direct_card",
                "invoice_id": str(invoice.id),
                "session_id": str(session.id),
                "operator_tenant_id": str(tenant_id),
                "checkout_session_id": confirmed.opaque_id,
                "recovery_attempt_id": str(recovery_attempt_id) if recovery_attempt_id else None,
                "merchant": {
                    key: merchant[key]
                    for key in ("merchant_mode", "merchant_account_ref", "provider")
                    if key in merchant
                },
                "provider_hints": provider_hints,
            },
        )
        db.add(order)
        db.flush()
        return order

    def _create_charging_payment_intent(
        self,
        db: Session,
        *,
        confirmed: CheckoutSessionRecord,
    ) -> tuple[Order, str]:
        data = confirmed.data
        try:
            app_user_id = UUID(confirmed.app_user_id)
            charge_point_id = UUID(str(data["charge_point_id"]))
            operator_tenant_id = UUID(str(data["operator_tenant_id"]))
            connector_id = int(data["connector_id"])
            merchant_snapshot = data["merchant"]
            if not isinstance(merchant_snapshot, dict):
                raise TypeError("Invalid merchant snapshot")
            payment_method_mode = str(data["payment_method_mode"])
            selected_payment_method_id = data.get("selected_payment_method_id")
            confirmation = data.get("confirmation") or {}
            provider_hints = confirmation.get("provider_hints") or {}
            if not isinstance(provider_hints, dict):
                raise TypeError("Invalid provider hints")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PaymentIntentError("Charging intent target is incomplete") from exc

        # A Redis confirm is single-use, but this lookup also makes the DB side
        # safe if a caller retries after the Order commit and before the Redis
        # result projection.
        # ``intent_id`` is intentionally not used for recovery: before the
        # first Redis result projection it is None by definition.  The
        # checkout session ID is authenticated Redis state and is bound to all
        # trusted target fields above.
        existing = find_intent_order(
            db,
            app_user_id=app_user_id,
            checkout_session_id=confirmed.opaque_id,
            charge_point_id=charge_point_id,
            operator_tenant_id=operator_tenant_id,
            connector_id=connector_id,
        )
        if existing is not None:
            return existing[0], existing[1].intent_id

        site_id = db.query(ChargePoint.site_id).filter(
            ChargePoint.id == charge_point_id,
            ChargePoint.tenant_id == operator_tenant_id,
        ).scalar()
        RuntimeRailControlService.require_payment_creation_open(
            db, provider=str(merchant_snapshot.get("provider") or "mercadopago"),
            tenant_id=operator_tenant_id, site_id=site_id,
        )

        payment_method = {
            "mode": payment_method_mode,
            "saved_payment_method_id": (
                str(selected_payment_method_id)
                if selected_payment_method_id is not None
                else None
            ),
            "provider_payment_method_id": provider_hints.get("payment_method_id"),
            "provider_payment_type_id": provider_hints.get("payment_type_id"),
            "save_card": bool(data.get("save_card", False)),
        }
        pre_authorization = create_payment_intent_data(
            app_user_id=app_user_id,
            charge_point_id=charge_point_id,
            connector_id=connector_id,
            operator_tenant_id=operator_tenant_id,
            checkout_session_id=confirmed.opaque_id,
            expires_at=confirmed.expires_at,
            payment_method=payment_method,
            merchant_snapshot=merchant_snapshot,
        )
        pre_authorization["pricing"] = data.get("pricing")
        user_uuid = str(app_user_id).replace("-", "")
        order = Order(
            tenant_id=operator_tenant_id,
            charge_point_id=charge_point_id,
            user_id=str(app_user_id),
            app_user_id=app_user_id,
            id_tag=f"APP{user_uuid[:17]}",
            status="pending",
            pre_authorization=pre_authorization,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order, str(pre_authorization["intent_id"])

    def verify_signed_token(self, signed_token: str):
        """BE-2C entry point: verify signature before loading Redis state."""
        return self._signer.verify(signed_token)

    def _verified_record(self, signed_token: str) -> CheckoutSessionRecord:
        try:
            verified = self._signer.verify(signed_token)
            record = self._store.get(verified.opaque_id)
        except CheckoutSigningError as exc:
            raise CheckoutSessionMissing("Checkout session not found") from exc
        except CheckoutSessionNotFound as exc:
            raise CheckoutSessionMissing("Checkout session not found") from exc
        except (CheckoutStoreUnavailable, CheckoutSessionCorrupt) as exc:
            raise CheckoutServiceUnavailable("Checkout state is unavailable") from exc
        except CheckoutStoreError as exc:
            raise CheckoutServiceUnavailable("Unable to read checkout session") from exc

        stored_nonce = record.data.get("signing_nonce")
        same_expiry = int(record.expires_at.timestamp()) == int(
            verified.expires_at.timestamp()
        )
        if (
            not isinstance(stored_nonce, str)
            or not hmac.compare_digest(stored_nonce, verified.nonce)
            or not same_expiry
        ):
            raise CheckoutSessionMissing("Checkout session not found")
        return record

    def _saved_payment_method(
        self,
        db: Session,
        record: CheckoutSessionRecord,
    ) -> AppUserPaymentMethod:
        selected_id = record.data.get("selected_payment_method_id")
        try:
            payment_method_id = UUID(str(selected_id))
            app_user_id = UUID(record.app_user_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise CheckoutServiceUnavailable(
                "Saved payment method state is unavailable"
            ) from exc
        payment_method = (
            db.query(AppUserPaymentMethod)
            .filter(
                AppUserPaymentMethod.id == payment_method_id,
                AppUserPaymentMethod.app_user_id == app_user_id,
                AppUserPaymentMethod.provider == "mercadopago",
            )
            .first()
        )
        if payment_method is None:
            raise CheckoutTargetNotFound("Saved payment method not found")
        return payment_method

    @staticmethod
    def _purpose_result_route(purpose: PaymentPurpose) -> str:
        return {
            PaymentPurpose.SAVE_CARD: "save_card",
            PaymentPurpose.CHARGING_DIRECT: "charging_payment_intent",
            PaymentPurpose.WALLET_TOP_UP: "payment_order",
            PaymentPurpose.UNPAID_CHARGE: "payment_order",
        }[purpose]

    def _deep_link_redirect(self, record: CheckoutSessionRecord) -> str:
        return_url = record.data.get("return_url")
        if not isinstance(return_url, str) or return_url not in self._return_urls:
            raise CheckoutServiceUnavailable("Checkout return URL is unavailable")
        query = urlencode(
            {
                "checkout_session_id": record.opaque_id,
                "status": record.status.value,
            }
        )
        return f"{return_url}?{query}"

    def _validated_session_data(
        self,
        db: Session,
        *,
        app_user_id: UUID,
        command: CreateCheckoutSessionCommand,
    ) -> tuple[dict[str, object], UUID | None]:
        if command.return_url not in self._return_urls:
            raise CheckoutRequestInvalid("Return URL is not allowed")
        if command.currency != "COP":
            raise CheckoutRequestInvalid("Unsupported checkout currency")

        selected_payment_method_id = self._validate_payment_method(
            db,
            app_user_id=app_user_id,
            command=command,
        )
        data: dict[str, object] = {
            "payment_method_mode": command.payment_method_mode.value,
            "selected_payment_method_id": selected_payment_method_id,
            "save_card": bool(command.save_card),
            "currency": "COP",
            "return_url": command.return_url,
        }
        if command.recovery_attempt_id is not None:
            data["recovery_attempt_id"] = str(command.recovery_attempt_id)

        if command.purpose is PaymentPurpose.SAVE_CARD:
            if (
                command.amount is not None
                or command.charge_point_id is not None
                or command.connector_id is not None
                or command.session_id is not None
                or command.payment_method_mode is not PaymentMethodMode.NEW_CARD
            ):
                raise CheckoutRequestInvalid("Invalid save-card checkout target")
            return data, None

        if command.purpose is PaymentPurpose.WALLET_TOP_UP:
            if (
                command.amount is None
                or command.charge_point_id is not None
                or command.connector_id is not None
                or command.session_id is not None
            ):
                raise CheckoutRequestInvalid("Invalid wallet top-up checkout target")
            amount = self._money(command.amount)
            minimum = self._money(self._settings.wallet_top_up_min_amount)
            maximum = self._money(self._settings.wallet_top_up_max_amount)
            if amount < minimum or amount > maximum:
                raise CheckoutRequestInvalid("Wallet top-up amount is outside allowed limits")
            data["amount"] = format(amount, ".2f")
            return data, None

        if command.purpose is PaymentPurpose.CHARGING_DIRECT:
            if (
                command.amount is not None
                or command.session_id is not None
                or command.charge_point_id is None
                or command.connector_id is None
            ):
                raise CheckoutRequestInvalid("Invalid direct-charging checkout target")
            charge_point = (
                db.query(ChargePoint)
                .join(Site, ChargePoint.site_id == Site.id)
                .filter(
                    ChargePoint.id == command.charge_point_id,
                    Site.tenant_id == ChargePoint.tenant_id,
                    ChargePoint.is_active.is_(True),
                    ChargePoint.commissioning_status == "commissioned",
                    Site.is_active.is_(True),
                )
                .first()
            )
            if charge_point is None:
                raise CheckoutTargetNotFound("Charge point not found")
            evse = (
                db.query(EVSE)
                .filter(
                    EVSE.tenant_id == charge_point.tenant_id,
                    EVSE.charge_point_id == charge_point.id,
                    EVSE.evse_id == command.connector_id,
                )
                .first()
            )
            if evse is None:
                raise CheckoutTargetNotFound("Connector not found")
            pricing = PricingService.resolve(
                db,
                charge_point.tenant_id,
                charge_point.id,
                self._now(),
            )
            if pricing.pricing_mode is not PricingMode.PAID:
                raise CheckoutRequestInvalid("Charging price must be paid")
            data.update(
                {
                    "charge_point_id": str(charge_point.id),
                    "connector_id": int(evse.evse_id),
                    "pricing": pricing.as_dict(),
                }
            )
            return data, charge_point.tenant_id

        if command.purpose is PaymentPurpose.UNPAID_CHARGE:
            if (
                command.amount is not None
                or command.charge_point_id is not None
                or command.connector_id is not None
                or command.session_id is None
            ):
                raise CheckoutRequestInvalid("Invalid unpaid-charge checkout target")
            session = (
                db.query(ChargingSession)
                .filter(
                    ChargingSession.id == command.session_id,
                    ChargingSession.app_user_id == app_user_id,
                    ChargingSession.payment_status == "unpaid",
                )
                .first()
            )
            if session is None:
                raise CheckoutTargetNotFound("Unpaid charging session not found")
            invoice = (
                db.query(Invoice)
                .filter(
                    Invoice.session_id == session.id,
                    Invoice.tenant_id == session.tenant_id,
                    Invoice.status == "pending",
                )
                .first()
            )
            if invoice is None or self._money(invoice.total_amount) <= Decimal("0.00"):
                raise CheckoutTargetNotFound("Unpaid charging invoice not found")
            data.update(
                {
                    "session_id": str(session.id),
                    "invoice_id": str(invoice.id),
                    "amount": format(self._money(invoice.total_amount), ".2f"),
                    "charge_point_id": str(session.charge_point_id),
                }
            )
            return data, session.tenant_id

        raise CheckoutRequestInvalid("Unsupported checkout purpose")

    @staticmethod
    def _validate_token_purpose(command: CreateCheckoutSessionCommand) -> None:
        """Freeze one checkout and one provider token to one business purpose."""

        if command.purpose is PaymentPurpose.SAVE_CARD:
            if (
                command.payment_method_mode is not PaymentMethodMode.NEW_CARD
                or command.saved_payment_method_id is not None
                or command.save_card is not True
            ):
                raise CheckoutRequestInvalid("Invalid save-card checkout mode")
            return
        if command.save_card:
            raise CheckoutRequestInvalid(
                "Saving a card is only available in a save-card checkout"
            )

    def _validate_payment_method(
        self,
        db: Session,
        *,
        app_user_id: UUID,
        command: CreateCheckoutSessionCommand,
    ) -> str | None:
        if command.payment_method_mode is PaymentMethodMode.NEW_CARD:
            if command.saved_payment_method_id is not None:
                raise CheckoutRequestInvalid("Saved payment method is not allowed")
            return None
        if command.saved_payment_method_id is None:
            raise CheckoutRequestInvalid("Saved payment method is required")
        if command.save_card:
            raise CheckoutRequestInvalid("An already saved card cannot be saved again")
        payment_method = (
            db.query(AppUserPaymentMethod)
            .filter(
                AppUserPaymentMethod.id == command.saved_payment_method_id,
                AppUserPaymentMethod.app_user_id == app_user_id,
                AppUserPaymentMethod.provider == "mercadopago",
            )
            .first()
        )
        if payment_method is None:
            raise CheckoutTargetNotFound("Saved payment method not found")
        return str(payment_method.id)

    def _client_subject(self, command: CreateCheckoutSessionCommand) -> dict[str, object]:
        amount = self._money(command.amount) if command.amount is not None else None
        return {
            "purpose": command.purpose.value,
            "payment_method_mode": command.payment_method_mode.value,
            "saved_payment_method_id": (
                str(command.saved_payment_method_id)
                if command.saved_payment_method_id is not None
                else None
            ),
            "save_card": bool(command.save_card),
            "amount": format(amount, ".2f") if amount is not None else None,
            "currency": command.currency,
            "charge_point_id": (
                str(command.charge_point_id) if command.charge_point_id else None
            ),
            "connector_id": command.connector_id,
            "session_id": str(command.session_id) if command.session_id else None,
            "return_url": command.return_url,
            "recovery_attempt_id": (
                str(command.recovery_attempt_id)
                if command.recovery_attempt_id is not None
                else None
            ),
        }

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        try:
            normalized = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise CheckoutRequestInvalid("Invalid monetary amount") from exc
        if not normalized.is_finite() or normalized.as_tuple().exponent < -2:
            raise CheckoutRequestInvalid("Amounts must use at most two decimal places")
        return normalized.quantize(Decimal("0.01"))

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return str(value) if isinstance(value, (str, UUID)) else None

    @staticmethod
    def _optional_safe_label(value: object, *, maximum: int) -> str | None:
        if not isinstance(value, str):
            return None
        candidate = value.strip()
        if (
            not candidate
            or len(candidate) > maximum
            or any(ord(character) < 32 for character in candidate)
        ):
            return None
        return candidate

    @staticmethod
    def _validate_public_base_url(value: str) -> str:
        candidate = value.strip().rstrip("/")
        parsed = urlparse(candidate)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise CheckoutServiceUnavailable("Public checkout base URL is invalid")
        return candidate

    def _validated_next_action_url(self, value: str) -> str:
        parsed = urlparse(value)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        trusted_host = any(
            hostname == allowed or hostname.endswith(f".{allowed}")
            for allowed in self._next_action_hosts
        )
        if (
            parsed.scheme != "https"
            or not trusted_host
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise CheckoutServiceUnavailable("Checkout next action is not trusted")
        return value

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise CheckoutServiceUnavailable("Checkout clock must be timezone-aware")
        return value.astimezone(timezone.utc)
