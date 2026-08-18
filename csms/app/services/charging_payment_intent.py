"""Charging Payment Intent state and binding helpers.

The project deliberately has no PaymentIntent table in this release.  This
module keeps the versioned, non-sensitive intent document stored in
``orders.pre_authorization`` in one place so that the App API and the OCPP
session path apply the same validation and state transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.database.models import Order


PAYMENT_INTENT_SCHEMA_VERSION = 1
PAYMENT_INTENT_KIND = "charging_payment_intent"


class PaymentIntentError(ValueError):
    """A persisted intent is missing, malformed, or not usable."""

    code = "PAYMENT_INTENT_INVALID"


class PaymentIntentConflict(PaymentIntentError):
    """The intent cannot be claimed because another start owns the race."""

    code = "PAYMENT_INTENT_CONFLICT"


@dataclass(frozen=True)
class PaymentIntent:
    intent_id: str
    status: str
    app_user_id: UUID
    charge_point_id: UUID
    connector_id: int
    operator_tenant_id: UUID
    checkout_session_id: str
    expires_at: datetime
    session_id: UUID | None = None
    settlement_method: str = "direct_card"

    def __post_init__(self) -> None:
        if self.status not in {"ready", "start_requested", "bound", "expired"}:
            raise PaymentIntentError("Unsupported payment intent state")
        if self.connector_id <= 0:
            raise PaymentIntentError("Invalid payment intent connector")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise PaymentIntentError("Payment intent expiry must be timezone-aware")
        if self.settlement_method != "direct_card":
            raise PaymentIntentError("Invalid payment intent settlement method")

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.expires_at <= now.astimezone(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PAYMENT_INTENT_SCHEMA_VERSION,
            "kind": PAYMENT_INTENT_KIND,
            "intent_id": self.intent_id,
            "status": self.status,
            "app_user_id": str(self.app_user_id),
            "charge_point_id": str(self.charge_point_id),
            "connector_id": self.connector_id,
            "operator_tenant_id": str(self.operator_tenant_id),
            "checkout_session_id": self.checkout_session_id,
            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat(),
            "session_id": str(self.session_id) if self.session_id else None,
            "settlement_method": self.settlement_method,
        }

    def with_state(
        self,
        status: str,
        *,
        session_id: UUID | None = None,
    ) -> "PaymentIntent":
        allowed = {
            "ready": {"ready", "start_requested", "expired"},
            "start_requested": {"start_requested", "ready", "bound", "expired"},
            "bound": {"bound"},
            "expired": {"expired"},
        }
        if status not in allowed.get(self.status, set()):
            raise PaymentIntentError(
                f"Invalid payment intent transition: {self.status} -> {status}"
            )
        return replace(self, status=status, session_id=session_id or self.session_id)


def parse_payment_intent(value: Mapping[str, Any] | None) -> PaymentIntent | None:
    """Parse only the intent shape; unrelated legacy pre-authorization is ignored."""

    if not isinstance(value, Mapping) or value.get("kind") != PAYMENT_INTENT_KIND:
        return None
    try:
        if int(value["schema_version"]) != PAYMENT_INTENT_SCHEMA_VERSION:
            raise PaymentIntentError("Unsupported payment intent schema")
        expires_at = datetime.fromisoformat(str(value["expires_at"]))
        session_id = value.get("session_id")
        return PaymentIntent(
            intent_id=str(value["intent_id"]),
            status=str(value["status"]),
            app_user_id=UUID(str(value["app_user_id"])),
            charge_point_id=UUID(str(value["charge_point_id"])),
            connector_id=int(value["connector_id"]),
            operator_tenant_id=UUID(str(value["operator_tenant_id"])),
            checkout_session_id=str(value["checkout_session_id"]),
            expires_at=expires_at.astimezone(timezone.utc),
            session_id=UUID(str(session_id)) if session_id else None,
            settlement_method=str(value.get("settlement_method", "direct_card")),
        )
    except PaymentIntentError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise PaymentIntentError("Malformed payment intent") from exc


def create_payment_intent_data(
    *,
    app_user_id: UUID,
    charge_point_id: UUID,
    connector_id: int,
    operator_tenant_id: UUID,
    checkout_session_id: str,
    expires_at: datetime,
    payment_method: Mapping[str, Any],
    merchant_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the safe Order pre-authorization document for a direct-card intent."""

    intent = PaymentIntent(
        intent_id=str(uuid4()),
        status="ready",
        app_user_id=app_user_id,
        charge_point_id=charge_point_id,
        connector_id=connector_id,
        operator_tenant_id=operator_tenant_id,
        checkout_session_id=checkout_session_id,
        expires_at=expires_at.astimezone(timezone.utc),
    )
    return {
        **intent.to_dict(),
        "merchant": dict(merchant_snapshot),
        "payment_method": dict(payment_method),
    }


def find_intent_order(
    db: Session,
    *,
    intent_id: str | None = None,
    app_user_id: UUID,
    checkout_session_id: str | None = None,
    charge_point_id: UUID | None = None,
    operator_tenant_id: UUID | None = None,
    connector_id: int | None = None,
    lock: bool = False,
) -> tuple[Order, PaymentIntent] | None:
    """Find an intent through trusted ownership fields, never by client tenant alone."""

    if intent_id is None and checkout_session_id is None:
        raise PaymentIntentError("Intent lookup requires an intent or checkout session ID")

    query = db.query(Order).filter(Order.app_user_id == app_user_id)
    if charge_point_id is not None:
        query = query.filter(Order.charge_point_id == charge_point_id)
    if operator_tenant_id is not None:
        query = query.filter(Order.tenant_id == operator_tenant_id)
    if lock:
        query = query.with_for_update()
    for order in query.order_by(Order.created_at.desc()).all():
        try:
            intent = parse_payment_intent(order.pre_authorization)
        except PaymentIntentError:
            continue
        if intent is None:
            continue
        if intent_id is not None and intent.intent_id != intent_id:
            continue
        if (
            checkout_session_id is not None
            and intent.checkout_session_id != checkout_session_id
        ):
            continue
        if connector_id is not None and intent.connector_id != connector_id:
            continue
        if intent.app_user_id != app_user_id:
            continue
        return order, intent
    return None


def find_start_requested_order(
    db: Session,
    *,
    app_user_id: UUID,
    charge_point_id: UUID,
    operator_tenant_id: UUID,
    connector_id: int,
) -> tuple[Order, PaymentIntent] | None:
    """Return the sole intent allowed to bind the next StartTransaction."""

    query = (
        db.query(Order)
        .filter(
            Order.app_user_id == app_user_id,
            Order.tenant_id == operator_tenant_id,
            Order.charge_point_id == charge_point_id,
        )
        .with_for_update()
    )
    matches: list[tuple[Order, PaymentIntent]] = []
    for order in query.order_by(Order.created_at.desc()).all():
        try:
            intent = parse_payment_intent(order.pre_authorization)
        except PaymentIntentError:
            continue
        if (
            intent is not None
            and intent.status == "start_requested"
            and intent.connector_id == connector_id
        ):
            if intent.is_expired():
                raise PaymentIntentError("Payment intent expired before StartTransaction")
            matches.append((order, intent))
    if len(matches) > 1:
        raise PaymentIntentConflict("Multiple payment intents are awaiting this connector")
    return matches[0] if matches else None


def write_intent(order: Order, intent: PaymentIntent) -> None:
    """Write only the versioned safe intent document back to the Order."""

    current = dict(order.pre_authorization or {})
    current.update(intent.to_dict())
    order.pre_authorization = current
