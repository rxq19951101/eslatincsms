"""Mercado Pago Customers/Cards and the local saved-payment projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.models import AppUser, AppUserPaymentMethod
from app.services.payment_method_codec import (
    PaymentMethodDescriptor,
    decode_payment_method_brand,
    encode_payment_method_brand,
)
from app.services.payment_providers.base import (
    CustomerCardProvider,
    PaymentProviderError,
    ProviderCardResult,
)
from app.services.payment_providers.merchant_context import (
    MerchantAccountResolver,
    PaymentPurpose,
    PlatformMerchantAccountResolver,
)


class PaymentMethodServiceError(RuntimeError):
    """Safe application error for saved-card operations."""


class PaymentMethodNotFound(PaymentMethodServiceError):
    pass


class PaymentMethodProviderUnavailable(PaymentMethodServiceError):
    pass


@dataclass(frozen=True)
class PaymentMethodView:
    id: str
    provider: str
    brand: str | None
    payment_type: str | None
    last_four: str | None
    is_default: bool


def payment_method_view(row: AppUserPaymentMethod) -> PaymentMethodView:
    descriptor: PaymentMethodDescriptor = decode_payment_method_brand(
        row.payment_method_brand
    )
    return PaymentMethodView(
        id=str(row.id),
        provider=str(row.provider),
        brand=descriptor.brand,
        payment_type=descriptor.payment_type,
        last_four=row.last_four,
        is_default=bool(row.is_default),
    )


class PaymentMethodService:
    def __init__(
        self,
        *,
        provider: CustomerCardProvider,
        merchant_resolver: MerchantAccountResolver | None = None,
    ) -> None:
        self._provider = provider
        self._merchant_resolver = merchant_resolver or PlatformMerchantAccountResolver()

    def list_for_user(self, db: Session, *, app_user_id: UUID) -> list[PaymentMethodView]:
        rows = (
            db.query(AppUserPaymentMethod)
            .filter(
                AppUserPaymentMethod.app_user_id == app_user_id,
                AppUserPaymentMethod.provider == "mercadopago",
            )
            .order_by(
                AppUserPaymentMethod.is_default.desc(),
                AppUserPaymentMethod.created_at.asc(),
                AppUserPaymentMethod.id.asc(),
            )
            .all()
        )
        return [payment_method_view(row) for row in rows]

    def save_card(
        self,
        db: Session,
        *,
        app_user_id: UUID,
        token: str,
        idempotency_key: str,
        payment_method_id: str | None,
        payment_type_id: str | None,
    ) -> PaymentMethodView:
        if not token or not idempotency_key:
            raise PaymentMethodServiceError("Card token and idempotency key are required")
        app_user = db.query(AppUser).filter(AppUser.id == app_user_id).first()
        if app_user is None:
            raise PaymentMethodServiceError("App user not found")
        rows = (
            db.query(AppUserPaymentMethod)
            .filter(
                AppUserPaymentMethod.app_user_id == app_user_id,
                AppUserPaymentMethod.provider == "mercadopago",
            )
            .with_for_update()
            .all()
        )
        customer_id = next(
            (str(row.mp_customer_id) for row in rows if row.mp_customer_id), None
        )
        context = self._merchant_resolver.resolve(
            operator_tenant_id=None,
            payment_purpose=PaymentPurpose.SAVE_CARD,
        )
        try:
            if customer_id is None:
                customer = self._provider.create_customer(
                    email=app_user.email,
                    idempotency_key=f"{idempotency_key}:customer",
                    merchant_context=context,
                )
                customer_id = customer.customer_id
            card: ProviderCardResult = self._provider.create_card(
                customer_id=customer_id,
                token=token,
                idempotency_key=f"{idempotency_key}:card",
                payment_method_id=payment_method_id,
                payment_type_id=payment_type_id,
                merchant_context=context,
            )
            stored_brand = encode_payment_method_brand(card.brand, card.payment_type)
        except (PaymentProviderError, ValueError) as exc:
            raise PaymentMethodProviderUnavailable(
                "Unable to save payment method"
            ) from exc

        if any(row.mp_card_id == card.card_id for row in rows):
            existing = next(row for row in rows if row.mp_card_id == card.card_id)
            return payment_method_view(existing)

        has_default = any(bool(row.is_default) for row in rows)
        row = AppUserPaymentMethod(
            app_user_id=app_user_id,
            provider="mercadopago",
            mp_customer_id=customer_id,
            mp_card_id=card.card_id,
            payment_method_brand=stored_brand,
            last_four=card.last_four,
            is_default=not rows or not has_default,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        if row.is_default:
            for existing in rows:
                existing.is_default = False
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
        except Exception as exc:
            db.rollback()
            raise PaymentMethodServiceError("Unable to persist payment method") from exc
        return payment_method_view(row)

    def set_default(
        self,
        db: Session,
        *,
        app_user_id: UUID,
        payment_method_id: UUID,
    ) -> PaymentMethodView:
        rows = (
            db.query(AppUserPaymentMethod)
            .filter(
                AppUserPaymentMethod.app_user_id == app_user_id,
                AppUserPaymentMethod.provider == "mercadopago",
            )
            .with_for_update()
            .all()
        )
        target = next((row for row in rows if row.id == payment_method_id), None)
        if target is None:
            raise PaymentMethodNotFound("Payment method not found")
        for row in rows:
            row.is_default = row.id == target.id
        try:
            db.commit()
            db.refresh(target)
        except Exception as exc:
            db.rollback()
            raise PaymentMethodServiceError("Unable to update payment method") from exc
        return payment_method_view(target)

    def delete(
        self,
        db: Session,
        *,
        app_user_id: UUID,
        payment_method_id: UUID,
        idempotency_key: str,
    ) -> None:
        if not idempotency_key:
            raise PaymentMethodServiceError("Idempotency key is required")
        rows = (
            db.query(AppUserPaymentMethod)
            .filter(
                AppUserPaymentMethod.app_user_id == app_user_id,
                AppUserPaymentMethod.provider == "mercadopago",
            )
            .with_for_update()
            .all()
        )
        target = next((row for row in rows if row.id == payment_method_id), None)
        if target is None:
            raise PaymentMethodNotFound("Payment method not found")
        context = self._merchant_resolver.resolve(
            operator_tenant_id=None,
            payment_purpose=PaymentPurpose.SAVE_CARD,
        )
        try:
            self._provider.delete_card(
                customer_id=str(target.mp_customer_id or ""),
                card_id=str(target.mp_card_id or ""),
                idempotency_key=idempotency_key,
                merchant_context=context,
            )
        except (PaymentProviderError, ValueError) as exc:
            raise PaymentMethodProviderUnavailable(
                "Unable to delete payment method"
            ) from exc

        was_default = bool(target.is_default)
        db.delete(target)
        remaining = [row for row in rows if row.id != target.id]
        if was_default and remaining:
            next_default = sorted(
                remaining,
                key=lambda row: (row.created_at or datetime.max.replace(tzinfo=timezone.utc), str(row.id)),
            )[0]
            for row in remaining:
                row.is_default = row.id == next_default.id
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise PaymentMethodServiceError("Unable to persist payment method deletion") from exc
