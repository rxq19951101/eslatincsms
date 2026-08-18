"""PAY-MP-001 secure checkout session create and query API."""

from __future__ import annotations

import secrets
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.validation import StrictRequestModel
from app.core.auth import get_current_user
from app.core.config import get_settings
from app.database.base import get_db
from app.database.models import AppUser, RecoveryAttempt
from app.services.payment_checkout.crypto import PaymentTokenCipher, PaymentTokenCryptoError
from app.services.payment_checkout.redis_store import CheckoutSessionStore, CheckoutStoreError
from app.services.payment_checkout.service import (
    ConfirmCheckoutSessionCommand,
    CheckoutAlreadyConfirmed,
    CheckoutServiceError,
    CheckoutSessionMissing,
    CheckoutSessionService,
    CheckoutServiceUnavailable,
    CheckoutTargetNotFound,
    CreateCheckoutSessionCommand,
    PaymentMethodMode,
)
from app.services.payment_checkout.hosted_page import (
    render_hosted_checkout_page,
    render_hosted_checkout_state_page,
)
from app.services.payment_checkout.signing import CheckoutSigningError, CheckoutURLSigner
from app.services.payment_providers.merchant_context import (
    PaymentPurpose,
    PlatformMerchantAccountResolver,
)


class CheckoutContractRoute(APIRoute):
    """Keep dependency and validation failures on the frozen error shape."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def contract_handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": {
                            "code": "VALIDATION_ERROR",
                            "message": "The checkout request is invalid.",
                        }
                    },
                )
            except HTTPException as exc:
                detail = exc.detail
                if not (
                    isinstance(detail, dict)
                    and isinstance(detail.get("code"), str)
                    and isinstance(detail.get("message"), str)
                ):
                    if exc.status_code == 401:
                        detail = {
                            "code": "AUTHENTICATION_INVALID",
                            "message": "Authentication is invalid.",
                        }
                    else:
                        detail = {
                            "code": "REQUEST_FAILED",
                            "message": "The checkout request could not be completed.",
                        }
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": detail},
                    headers=exc.headers,
                )

        return contract_handler


router = APIRouter(route_class=CheckoutContractRoute)

CheckoutPurpose = Literal[
    "save_card",
    "wallet_top_up",
    "charging_direct",
    "unpaid_charge",
]
CheckoutPaymentMethodMode = Literal["new_card", "saved_card"]


class CreateCheckoutSessionRequest(StrictRequestModel):
    purpose: CheckoutPurpose
    payment_method_mode: CheckoutPaymentMethodMode
    saved_payment_method_id: Optional[UUID] = None
    save_card: bool = False
    amount: Optional[Decimal] = Field(None, max_digits=12, decimal_places=2)
    currency: Literal["COP"] = "COP"
    charge_point_id: Optional[UUID] = None
    connector_id: Optional[int] = Field(None, ge=1)
    session_id: Optional[UUID] = None
    return_url: str = Field(..., min_length=1, max_length=500)
    idempotency_key: UUID

    @field_validator("amount", mode="before")
    @classmethod
    def require_decimal_string(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("amount must be a decimal string")
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("amount must be a decimal string") from exc
        if not amount.is_finite():
            raise ValueError("amount must be finite")
        return amount

    @field_validator("idempotency_key")
    @classmethod
    def require_uuid_v4(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("idempotency_key must be a UUID v4")
        return value


class CreateCheckoutSessionResponse(BaseModel):
    checkout_session_id: str
    checkout_url: str
    expires_at: str
    purpose: CheckoutPurpose
    recovery_attempt_id: Optional[str] = None


class CheckoutNextAction(BaseModel):
    type: Literal["open_url"]
    url: str


class CheckoutSessionResponse(BaseModel):
    id: str
    purpose: CheckoutPurpose
    status: Literal[
        "created",
        "ready",
        "processing",
        "action_required",
        "approved",
        "declined",
        "expired",
        "error",
    ]
    payment_intent_id: Optional[str] = None
    payment_order_id: Optional[str] = None
    saved_payment_method_id: Optional[str] = None
    next_action: Optional[CheckoutNextAction] = None
    expires_at: str
    recovery_attempt_id: Optional[str] = None


class ConfirmCheckoutRequest(StrictRequestModel):
    """Only the one-time token and non-sensitive Mercado Pago hints."""

    card_token: str = Field(..., min_length=16, max_length=2048)
    payment_method_id: Optional[str] = Field(None, min_length=1, max_length=128)
    payment_type_id: Optional[
        Literal["credit_card", "debit_card", "prepaid_card"]
    ] = None
    issuer_id: Optional[str] = Field(None, min_length=1, max_length=128)
    installments: int = Field(1, ge=1, le=1)


async def get_current_checkout_app_user(
    current_user_payload=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppUser:
    """Resolve the authenticated AppUser without importing legacy payment routes."""
    user_id = current_user_payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTHENTICATION_INVALID",
                "message": "Authentication is invalid.",
            },
        )
    try:
        normalized_user_id = UUID(str(user_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTHENTICATION_INVALID",
                "message": "Authentication is invalid.",
            },
        ) from exc
    app_user = db.query(AppUser).filter(AppUser.id == normalized_user_id).first()
    if app_user is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTHENTICATION_INVALID",
                "message": "Authentication is invalid.",
            },
        )
    return app_user


def get_checkout_session_service() -> CheckoutSessionService:
    settings = get_settings()
    try:
        cipher = PaymentTokenCipher(
            settings.payment_token_encryption_key.get_secret_value()
        )
        return CheckoutSessionService(
            store=CheckoutSessionStore(
                cipher=cipher,
                ttl_seconds=settings.checkout_session_ttl_seconds,
            ),
            signer=CheckoutURLSigner(
                settings.checkout_signing_key.get_secret_value()
            ),
            merchant_resolver=PlatformMerchantAccountResolver(),
            settings=settings,
        )
    except (PaymentTokenCryptoError, CheckoutSigningError, CheckoutStoreError) as exc:
        raise CheckoutServiceUnavailable("Checkout configuration is unavailable") from exc


def _error_response(error: CheckoutServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "detail": {
                "code": error.code,
                "message": error.public_message,
            }
        },
    )


def _payment_rails_disabled() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "detail": {
                "code": "PAYMENT_RAILS_DISABLED",
                "message": "Payment checkout is not enabled.",
            }
        },
    )


def _hosted_page_headers(script_nonce: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-Robots-Tag": "noindex, nofollow",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": (
            "default-src 'none'; "
            "base-uri 'none'; object-src 'none'; form-action 'self'; "
            "frame-ancestors 'none'; "
            f"script-src 'self' https://sdk.mercadopago.com 'nonce-{script_nonce}'; "
            "style-src 'unsafe-inline'; "
            "connect-src 'self' https://sdk.mercadopago.com "
            "https://api.mercadopago.com https://api.mercadopago.com.co "
            "https://api-static.mercadopago.com https://api.mercadolibre.com "
            "https://secure-fields.mercadopago.com https://secure-fields-stg.mercadopago.com; "
            "frame-src https://*.mercadopago.com https://*.mercadopago.com.co "
            "https://secure-fields.mercadopago.com https://secure-fields-stg.mercadopago.com"
        ),
    }


def _safe_hosted_return_url() -> str | None:
    configured = getattr(get_settings(), "checkout_return_url_allowlist", "")
    if not isinstance(configured, str):
        return None
    for value in configured.split(","):
        candidate = value.strip()
        parsed = urlparse(candidate)
        if (
            candidate
            and parsed.scheme == "eslatin"
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
        ):
            return candidate
    return None


def _hosted_state_response(error: CheckoutServiceError) -> HTMLResponse:
    if isinstance(error, (CheckoutSessionMissing, CheckoutTargetNotFound)):
        status_code = 404
        title = "La sesión de pago no está disponible"
        message = (
            "La sesión venció o ya no existe. Vuelve a la aplicación para "
            "iniciar el proceso de nuevo."
        )
    elif isinstance(error, CheckoutAlreadyConfirmed):
        status_code = 409
        title = "Esta operación ya fue enviada"
        message = (
            "Vuelve a la aplicación para consultar el resultado. No necesitas "
            "enviar otra vez los datos de la tarjeta."
        )
    else:
        status_code = 503
        title = "El pago no está disponible temporalmente"
        message = (
            "No pudimos abrir el pago en este momento. Inténtalo de nuevo desde "
            "la aplicación dentro de unos minutos."
        )
    script_nonce = secrets.token_urlsafe(18)
    return HTMLResponse(
        status_code=status_code,
        content=render_hosted_checkout_state_page(
            title=title,
            message=message,
            return_url=_safe_hosted_return_url(),
        ),
        headers=_hosted_page_headers(script_nonce),
    )


def _valid_recovery_attempt_id(
    db: Session,
    *,
    app_user_id: UUID,
    purpose: PaymentPurpose,
    recovery_attempt_id: str | None,
) -> str | None:
    """Return the additive P002 field only for an owned typed recovery attempt."""
    if purpose is not PaymentPurpose.UNPAID_CHARGE or not recovery_attempt_id:
        return None
    try:
        attempt_uuid = UUID(str(recovery_attempt_id))
    except (TypeError, ValueError, AttributeError):
        return None
    attempt = (
        db.query(RecoveryAttempt)
        .filter(
            RecoveryAttempt.id == attempt_uuid,
            RecoveryAttempt.app_user_id == app_user_id,
        )
        .first()
    )
    return str(attempt.id) if attempt is not None else None


@router.post(
    "/checkout-sessions",
    response_model=CreateCheckoutSessionResponse,
    summary="Create a secure payment checkout session",
)
def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
):
    if not get_settings().payment_rails_enabled:
        return _payment_rails_disabled()
    try:
        service = get_checkout_session_service()
        result = service.create(
            db,
            app_user_id=current_user.id,
            command=CreateCheckoutSessionCommand(
                purpose=PaymentPurpose(payload.purpose),
                payment_method_mode=PaymentMethodMode(payload.payment_method_mode),
                saved_payment_method_id=payload.saved_payment_method_id,
                save_card=payload.save_card,
                amount=payload.amount,
                currency=payload.currency,
                charge_point_id=payload.charge_point_id,
                connector_id=payload.connector_id,
                session_id=payload.session_id,
                return_url=payload.return_url,
                idempotency_key=str(payload.idempotency_key),
                recovery_attempt_id=None,
            ),
        )
    except CheckoutServiceError as exc:
        return _error_response(exc)
    body = {
        "checkout_session_id": result.checkout_session_id,
        "checkout_url": result.checkout_url,
        "expires_at": result.expires_at.isoformat().replace("+00:00", "Z"),
        "purpose": result.purpose.value,
    }
    recovery_attempt_id = _valid_recovery_attempt_id(
        db,
        app_user_id=current_user.id,
        purpose=result.purpose,
        recovery_attempt_id=result.recovery_attempt_id,
    )
    if recovery_attempt_id is not None:
        body["recovery_attempt_id"] = recovery_attempt_id
    return JSONResponse(content=body)


@router.get(
    "/checkout-sessions/{checkout_session_id}",
    response_model=CheckoutSessionResponse,
    summary="Read a secure payment checkout session",
)
def get_checkout_session(
    checkout_session_id: str = Path(..., min_length=16, max_length=128),
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
):
    try:
        service = get_checkout_session_service()
        result = service.get(
            app_user_id=current_user.id,
            checkout_session_id=checkout_session_id,
        )
    except CheckoutServiceError as exc:
        return _error_response(exc)
    body = {
        "id": result.id,
        "purpose": result.purpose.value,
        "status": result.status.value,
        "payment_intent_id": result.payment_intent_id,
        "payment_order_id": result.payment_order_id,
        "saved_payment_method_id": result.saved_payment_method_id,
        "next_action": result.next_action,
        "expires_at": result.expires_at.isoformat().replace("+00:00", "Z"),
    }
    recovery_attempt_id = _valid_recovery_attempt_id(
        db,
        app_user_id=current_user.id,
        purpose=result.purpose,
        recovery_attempt_id=result.recovery_attempt_id,
    )
    if recovery_attempt_id is not None:
        body["recovery_attempt_id"] = recovery_attempt_id
    return JSONResponse(content=body)


@router.get(
    "/checkout/{signed_token}",
    response_class=HTMLResponse,
    summary="Open the Mercado Pago hosted checkout page",
)
def open_hosted_checkout(
    signed_token: str = Path(..., min_length=1, max_length=2048),
    db: Session = Depends(get_db),
):
    if not get_settings().payment_rails_enabled:
        return _hosted_state_response(
            CheckoutServiceUnavailable("Payment checkout is not enabled")
        )
    try:
        service = get_checkout_session_service()
        page = service.get_hosted_page(db, signed_token=signed_token)
    except CheckoutServiceError as exc:
        return _hosted_state_response(exc)

    script_nonce = secrets.token_urlsafe(18)
    return HTMLResponse(
        content=render_hosted_checkout_page(
            page,
            signed_token=signed_token,
            script_nonce=script_nonce,
        ),
        headers=_hosted_page_headers(script_nonce),
    )


@router.post(
    "/checkout/{signed_token}/confirm",
    summary="Confirm a hosted checkout card token",
)
def confirm_hosted_checkout(
    payload: ConfirmCheckoutRequest,
    signed_token: str = Path(..., min_length=16, max_length=2048),
    db: Session = Depends(get_db),
):
    if not get_settings().payment_rails_enabled:
        return _payment_rails_disabled()
    try:
        service = get_checkout_session_service()
        result = service.confirm(
            db,
            signed_token=signed_token,
            command=ConfirmCheckoutSessionCommand(
                card_token=payload.card_token,
                payment_method_id=payload.payment_method_id,
                payment_type_id=payload.payment_type_id,
                issuer_id=payload.issuer_id,
                installments=payload.installments,
            ),
        )
    except CheckoutServiceError as exc:
        return _error_response(exc)
    return RedirectResponse(
        url=result.redirect_url,
        status_code=303,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )
