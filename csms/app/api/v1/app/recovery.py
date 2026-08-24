"""PAY-MP-002 typed unpaid-charge recovery API."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.v1.app.payment_checkout import (
    get_checkout_session_service,
    get_current_checkout_app_user,
)
from app.api.validation import StrictRequestModel
from app.core.config import get_settings
from app.database.base import get_db
from app.database.models import (
    AppUser,
    AppUserPaymentMethod,
    ChargingSession,
    Invoice,
    PaymentAllocation,
    PaymentOrder,
    RecoveryAttempt,
)
from app.services.payment_checkout.service import (
    CheckoutServiceError,
    CreateCheckoutSessionCommand,
    PaymentMethodMode,
)
from app.services.payment_providers.merchant_context import PaymentPurpose
from app.services.recovery_service import (
    IdempotencyConflict,
    RecoveryError,
    RecoveryDeploymentDisabled,
    RecoveryRailClosed,
    RecoveryService,
    RecoveryTargetInvalid,
)
from app.services.financial_eligibility import FinancialEligibilityEvaluator


router = APIRouter()


class RecoveryAttemptRequest(StrictRequestModel):
    method: Literal["wallet", "new_card", "saved_card"]
    saved_payment_method_id: UUID | None = None


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def _error(exc: RecoveryError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _return_url() -> str:
    for candidate in str(get_settings().checkout_return_url_allowlist or "").split(","):
        candidate = candidate.strip()
        if candidate.startswith("eslatin://"):
            return candidate
    return "eslatin://payment-result"


def _allocation(db: Session, attempt_id: UUID) -> PaymentAllocation | None:
    return (
        db.query(PaymentAllocation)
        .filter(PaymentAllocation.recovery_attempt_id == attempt_id)
        .order_by(PaymentAllocation.created_at.desc())
        .first()
    )


def _payment_order(db: Session, attempt_id: UUID) -> PaymentOrder | None:
    orders = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.payment_provider == "mercadopago")
        .order_by(PaymentOrder.created_at.desc())
        .all()
    )
    for order in orders:
        if str((order.order_metadata or {}).get("recovery_attempt_id")) == str(attempt_id):
            return order
    return None


def _attempt_projection(db: Session, attempt: RecoveryAttempt) -> dict[str, Any]:
    allocation = _allocation(db, attempt.id)
    order = _payment_order(db, attempt.id)
    public_status = {
        "provider_approved": "approved",
        "allocated": "allocated",
        "duplicate_approved": "manual_review",
    }.get(attempt.status, attempt.status)
    allocation_status = None
    if allocation is not None:
        allocation_status = {
            "committed": "confirmed",
            "needs_review": "unknown",
        }.get(allocation.status, allocation.status)
    checkout_url = None
    checkout_id = None
    expires_at = attempt.expires_at
    if order is not None:
        metadata = order.order_metadata or {}
        checkout_url = metadata.get("checkout_url")
        checkout_id = metadata.get("checkout_session_id")
        if metadata.get("checkout_expires_at"):
            try:
                expires_at = datetime.fromisoformat(str(metadata["checkout_expires_at"]))
            except ValueError:
                pass
    if checkout_url and not isinstance(checkout_url, str):
        checkout_url = None
    next_action = {"type": "open_checkout", "checkout_session_id": checkout_id, "url": checkout_url, "expires_at": _iso(expires_at)} if checkout_url else None
    if attempt.status in {"unknown", "duplicate_approved"}:
        next_action = {"type": "contact_support"}
    elif attempt.status in {"processing", "action_required"} and not next_action:
        next_action = {"type": "poll", "poll_after_seconds": 5}
    financial = FinancialEligibilityEvaluator.evaluate(
        db, app_user_id=attempt.app_user_id
    ).public_projection()
    return {
        "attempt_id": str(attempt.id),
        "invoice_id": str(attempt.invoice_id),
        "target_amount": format(Decimal(str(attempt.target_amount)), ".2f"),
        "currency": attempt.currency,
        "method": attempt.method,
        "status": public_status,
        "payment_order_id": str(order.id) if order else None,
        "allocation": {
            "status": allocation_status or "pending",
            "amount": format(Decimal(str(allocation.amount)), ".2f") if allocation else "0.00",
            "confirmed_at": _iso(allocation.committed_at) if allocation else None,
        },
        "financial_eligibility": financial,
        "next_action": next_action,
        "support_reference": None,
        "allowed_actions": (
            ["refresh", "contact_support"]
            if attempt.status in {"unknown", "duplicate_approved"}
            else ["refresh", "contact_support"]
            if attempt.status in {"allocated", "declined", "failed", "expired", "cancelled"}
            else ["refresh", "open_checkout", "contact_support"]
        ),
        "version": attempt.version,
        "created_at": _iso(attempt.created_at),
        "updated_at": _iso(attempt.updated_at),
    }


def _invoice_projection(db: Session, invoice: Invoice) -> dict[str, Any]:
    session = db.query(ChargingSession).filter(ChargingSession.id == invoice.session_id).first()
    committed = (
        db.query(PaymentAllocation)
        .filter(PaymentAllocation.invoice_id == invoice.id, PaymentAllocation.status == "committed")
        .first()
    )
    total = Decimal(str(invoice.total_amount)).quantize(Decimal("0.01"))
    allocated = Decimal(str(committed.amount)).quantize(Decimal("0.01")) if committed else Decimal("0.00")
    active = (
        db.query(RecoveryAttempt)
        .filter(
            RecoveryAttempt.invoice_id == invoice.id,
            RecoveryAttempt.status.in_(["created", "processing", "action_required", "provider_approved"]),
        )
        .order_by(RecoveryAttempt.updated_at.desc(), RecoveryAttempt.id.desc())
        .first()
    )
    return {
        "invoice_id": str(invoice.id),
        "invoice_reference": invoice.invoice_number,
        "session_id": str(invoice.session_id),
        "site": None,
        "charge_point_reference": str(session.charge_point_id) if session else None,
        "connector_id": None,
        "started_at": _iso(session.start_time) if session else None,
        "ended_at": _iso(session.end_time) if session else None,
        "energy_kwh": format(Decimal(str(invoice.energy_kwh)), ".3f"),
        "original_amount": format(total, ".2f"),
        "allocated_amount": format(allocated, ".2f"),
        "refunded_amount": "0.00",
        "outstanding_amount": format(max(total - allocated, Decimal("0.00")), ".2f"),
        "currency": "COP",
        "blocking_reason": "open_invoice" if not committed else "recovery_processing",
        "recovery_status": (
            {"provider_approved": "approved", "duplicate_approved": "manual_review"}.get(
                active.status, active.status
            )
            if active
            else None
        ),
        "active_recovery_attempt_id": str(active.id) if active else None,
        "d1_status": "blocked",
        "allowed_actions": ["view", "start_recovery", "contact_support"] if not committed else ["view", "contact_support"],
        "updated_at": _iso(invoice.updated_at),
    }


@router.get("/unpaid-charges", summary="List typed unpaid invoices")
def list_unpaid_charges(
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
):
    del cursor  # Cursor is reserved for the frozen projection; ordering is deterministic now.
    rows = (
        db.query(Invoice)
        .join(ChargingSession, ChargingSession.id == Invoice.session_id)
        .filter(
            ChargingSession.app_user_id == current_user.id,
            Invoice.status == "pending",
        )
        .order_by(Invoice.updated_at.desc(), Invoice.id.desc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [_invoice_projection(db, invoice) for invoice in rows],
        "page": {"next_cursor": None, "has_more": has_more},
    }


@router.get("/unpaid-charges/{invoice_id}", summary="Read typed unpaid invoice")
def get_unpaid_charge(
    invoice_id: UUID = Path(...),
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
):
    invoice = (
        db.query(Invoice)
        .join(ChargingSession, ChargingSession.id == Invoice.session_id)
        .filter(Invoice.id == invoice_id, ChargingSession.app_user_id == current_user.id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND", "message": "Resource not found."})
    summary = _invoice_projection(db, invoice)
    methods = [
        {"method": "wallet", "enabled": True, "disabled_reason_code": None},
        {"method": "new_card", "enabled": bool(get_settings().payment_rails_enabled), "disabled_reason_code": None if get_settings().payment_rails_enabled else "rail_closed"},
    ]
    saved_methods = (
        db.query(AppUserPaymentMethod)
        .filter(
            AppUserPaymentMethod.app_user_id == current_user.id,
            AppUserPaymentMethod.provider == "mercadopago",
        )
        .order_by(
            AppUserPaymentMethod.is_default.desc(),
            AppUserPaymentMethod.created_at.asc(),
            AppUserPaymentMethod.id.asc(),
        )
        .all()
    )
    methods.extend(
        {
            "method": "saved_card",
            "enabled": bool(get_settings().payment_rails_enabled),
            "disabled_reason_code": None if get_settings().payment_rails_enabled else "rail_closed",
            "saved_payment_method_ref": {
                "id": str(saved.id),
                "brand": saved.payment_method_brand,
                "last_four": saved.last_four,
                "is_default": bool(saved.is_default),
            },
        }
        for saved in saved_methods
    )
    financial = FinancialEligibilityEvaluator.evaluate(
        db, app_user_id=current_user.id
    ).public_projection()
    return {**summary, "available_methods": methods, "active_recovery_attempt": (
        _attempt_projection(db, db.get(RecoveryAttempt, UUID(summary["active_recovery_attempt_id"])))
        if summary["active_recovery_attempt_id"] else None
    ), "timeline": [], "financial_eligibility": financial, "support_case_refs": []}


@router.post("/unpaid-charges/{invoice_id}/recovery-attempts", status_code=201, summary="Create typed recovery attempt")
def create_recovery_attempt(
    payload: RecoveryAttemptRequest,
    invoice_id: UUID = Path(...),
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    service = RecoveryService()
    try:
        if payload.method != "wallet" and not get_settings().payment_rails_enabled:
            raise RecoveryDeploymentDisabled("Payment rails are disabled by deployment policy")
        prepared = service.prepare(
            db,
            app_user_id=current_user.id,
            invoice_id=invoice_id,
            method=payload.method,
            saved_payment_method_id=payload.saved_payment_method_id,
            idempotency_key=idempotency_key,
        )
        attempt = prepared.attempt
        if payload.method == "wallet" and attempt.status != "allocated":
            attempt = service.settle_wallet(db, attempt_id=attempt.id)
        elif payload.method != "wallet" and not (
            prepared.payment_order
            and (prepared.payment_order.order_metadata or {}).get("checkout_url")
        ):
            checkout = get_checkout_session_service().create(
                db,
                app_user_id=current_user.id,
                command=CreateCheckoutSessionCommand(
                    purpose=PaymentPurpose.UNPAID_CHARGE,
                    payment_method_mode=PaymentMethodMode(payload.method),
                    saved_payment_method_id=payload.saved_payment_method_id,
                    save_card=False,
                    amount=None,
                    currency="COP",
                    charge_point_id=None,
                    connector_id=None,
                    session_id=attempt.session_id,
                    return_url=_return_url(),
                    idempotency_key=f"recovery-checkout:{attempt.id}",
                    recovery_attempt_id=attempt.id,
                ),
            )
            service.attach_checkout(
                db,
                attempt_id=attempt.id,
                checkout_session_id=checkout.checkout_session_id,
                checkout_url=checkout.checkout_url,
                expires_at=checkout.expires_at,
            )
        db.expire_all()
        attempt = db.get(RecoveryAttempt, attempt.id)
        return _attempt_projection(db, attempt)
    except RecoveryError as exc:
        db.rollback()
        raise _error(exc)
    except CheckoutServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail={"code": "PROVIDER_UNAVAILABLE", "message": str(exc)}) from exc


@router.get("/recovery-attempts/{attempt_id}", summary="Read typed recovery attempt")
def get_recovery_attempt(
    attempt_id: UUID = Path(...),
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
):
    attempt = (
        db.query(RecoveryAttempt)
        .filter(RecoveryAttempt.id == attempt_id, RecoveryAttempt.app_user_id == current_user.id)
        .first()
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND", "message": "Resource not found."})
    return _attempt_projection(db, attempt)
