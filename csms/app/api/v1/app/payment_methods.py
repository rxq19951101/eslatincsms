"""Saved Mercado Pago payment-method management for App users."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.validation import StrictRequestModel
from app.core.auth import get_current_user
from app.core.config import get_settings
from app.database.base import get_db
from app.database.models import AppUser
from app.services.payment_methods import (
    PaymentMethodNotFound,
    PaymentMethodProviderUnavailable,
    PaymentMethodService,
    PaymentMethodServiceError,
)
from app.services.payment_providers.mercadopago_provider import MercadoPagoProvider


from fastapi.routing import APIRoute


class _PaymentMethodContractRoute(APIRoute):
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
                            "message": "The payment-method request is invalid.",
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
                    detail = {
                        "code": "REQUEST_FAILED",
                        "message": "The payment-method request could not be completed.",
                    }
                return JSONResponse(status_code=exc.status_code, content={"detail": detail})

        return contract_handler


router = APIRouter(route_class=_PaymentMethodContractRoute)


async def get_current_payment_app_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppUser:
    user_id = current_user_payload.get("user_id")
    try:
        normalized_id = UUID(str(user_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTHENTICATION_INVALID", "message": "Authentication is invalid."},
        ) from exc
    user = db.query(AppUser).filter(AppUser.id == normalized_id).first()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTHENTICATION_INVALID", "message": "Authentication is invalid."},
        )
    return user


def get_payment_method_service() -> PaymentMethodService:
    return PaymentMethodService(provider=MercadoPagoProvider())


class PaymentMethodItem(BaseModel):
    id: str
    provider: str
    brand: Optional[str] = None
    payment_type: Optional[str] = None
    last_four: Optional[str] = None
    is_default: bool = False


class PaymentMethodListResponse(BaseModel):
    items: list[PaymentMethodItem]


class SetDefaultPaymentMethodRequest(StrictRequestModel):
    is_default: bool


def _rails_disabled() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "detail": {
                "code": "PAYMENT_RAILS_DISABLED",
                "message": "Payment methods are not enabled.",
            }
        },
    )


def _view(item) -> PaymentMethodItem:
    return PaymentMethodItem(
        id=item.id,
        provider=item.provider,
        brand=item.brand,
        payment_type=item.payment_type,
        last_four=item.last_four,
        is_default=item.is_default,
    )


def _service_error(exc: PaymentMethodServiceError) -> HTTPException:
    if isinstance(exc, PaymentMethodNotFound):
        return HTTPException(
            status_code=404,
            detail={"code": "PAYMENT_METHOD_NOT_FOUND", "message": "Payment method not found."},
        )
    if isinstance(exc, PaymentMethodProviderUnavailable):
        return HTTPException(
            status_code=502,
            detail={"code": "PAYMENT_METHOD_PROVIDER_ERROR", "message": "Payment provider unavailable."},
        )
    return HTTPException(
        status_code=500,
        detail={"code": "PAYMENT_METHOD_ERROR", "message": "Payment method operation failed."},
    )


@router.get("", response_model=PaymentMethodListResponse, summary="List saved payment methods")
def list_payment_methods(
    current_user: AppUser = Depends(get_current_payment_app_user),
    db: Session = Depends(get_db),
    service: PaymentMethodService = Depends(get_payment_method_service),
) -> PaymentMethodListResponse:
    return PaymentMethodListResponse(
        items=[_view(item) for item in service.list_for_user(db, app_user_id=current_user.id)]
    )


@router.patch("/{payment_method_id}", response_model=PaymentMethodItem, summary="Set a default payment method")
def set_default_payment_method(
    payload: SetDefaultPaymentMethodRequest,
    payment_method_id: UUID,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8),
    current_user: AppUser = Depends(get_current_payment_app_user),
    db: Session = Depends(get_db),
    service: PaymentMethodService = Depends(get_payment_method_service),
):
    if not get_settings().payment_rails_enabled:
        return _rails_disabled()
    if payload.is_default is not True:
        raise HTTPException(
            status_code=400,
            detail={"code": "PAYMENT_METHOD_REQUEST_INVALID", "message": "Only setting a default card is supported."},
        )
    try:
        item = service.set_default(
            db, app_user_id=current_user.id, payment_method_id=payment_method_id
        )
    except PaymentMethodServiceError as exc:
        raise _service_error(exc) from exc
    return _view(item)


@router.delete("/{payment_method_id}", status_code=204, summary="Delete a saved payment method")
def delete_payment_method(
    payment_method_id: UUID,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8),
    current_user: AppUser = Depends(get_current_payment_app_user),
    db: Session = Depends(get_db),
    service: PaymentMethodService = Depends(get_payment_method_service),
):
    if not get_settings().payment_rails_enabled:
        return _rails_disabled()
    try:
        service.delete(
            db,
            app_user_id=current_user.id,
            payment_method_id=payment_method_id,
            idempotency_key=idempotency_key,
        )
    except PaymentMethodServiceError as exc:
        raise _service_error(exc) from exc
    return None
