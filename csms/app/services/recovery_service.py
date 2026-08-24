"""PAY-MP-002 recovery attempts and payment allocations.

This module is the typed authority for the P002 unpaid-charge flow.  It is
deliberately separate from the legacy wallet settlement helper: P001 data is
not rewritten while recovery facts are appended to the BE-201 tables.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    AppUser,
    AppUserPaymentMethod,
    AppWalletTransaction,
    ChargePoint,
    ChargingSession,
    Invoice,
    OutboxEvent,
    PaymentAllocation,
    PaymentOrder,
    RecoveryAttempt,
)
from app.services.payment_providers.merchant_context import (
    MerchantContextError,
    PaymentPurpose,
    PlatformMerchantAccountResolver,
)
from app.services.runtime_rail_control import RuntimeRailControlService, RailClosed, RailStateUnknown


COP = "COP"
MONEY = Decimal("0.01")
RECOVERY_METHODS = {"wallet", "new_card", "saved_card"}


class RecoveryError(RuntimeError):
    code = "RECOVERY_ERROR"
    status_code = 500
    retryable = False

    def __init__(self, message: str | None = None):
        super().__init__(message or self.code)


class RecoveryTargetInvalid(RecoveryError):
    code = "RECOVERY_TARGET_INVALID"
    status_code = 404


class RecoveryNotAllowed(RecoveryError):
    code = "RECOVERY_NOT_ALLOWED"
    status_code = 409


class RecoveryConflict(RecoveryError):
    code = "RECOVERY_CONFLICT"
    status_code = 409


class IdempotencyConflict(RecoveryError):
    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409


class RecoveryUnknown(RecoveryError):
    code = "RECOVERY_UNKNOWN"
    status_code = 503
    retryable = True


class RecoveryRailClosed(RecoveryError):
    code = "RAIL_CLOSED"
    status_code = 503
    retryable = False


class RecoveryDeploymentDisabled(RecoveryError):
    """Existing deployment gate; deliberately distinct from scoped rail state."""

    code = "PAYMENT_RAILS_DISABLED"
    status_code = 403
    retryable = False


@dataclass(frozen=True)
class RecoveryPrepared:
    attempt: RecoveryAttempt
    payment_order: PaymentOrder | None = None
    reused: bool = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: Any) -> Decimal:
    amount = Decimal(str(value)).quantize(MONEY)
    if not amount.is_finite():
        raise ValueError("invalid monetary value")
    return amount


def _fingerprint(
    invoice_id: UUID, method: str, saved_payment_method_id: UUID | None
) -> str:
    payload = {
        "invoice_id": str(invoice_id),
        "method": method,
        "saved_payment_method_id": (
            str(saved_payment_method_id) if saved_payment_method_id else None
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _audit(attempt_id: UUID) -> str:
    return f"pay-mp-002:recovery:{attempt_id}"


def _outbox(
    db: Session,
    *,
    tenant_id: UUID,
    aggregate_type: str,
    aggregate_id: UUID | str,
    event_type: str,
    idempotency_key: str,
    status: str,
    version: int,
    payload: Mapping[str, Any],
) -> None:
    db.add(
        OutboxEvent(
            tenant_id=tenant_id,
            scope_type="tenant",
            scope_ref=f"tenant:{tenant_id}",
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id),
            event_type=event_type,
            idempotency_key=idempotency_key,
            status="pending",
            payload={
                "event_id": str(uuid4()),
                "schema_version": 1,
                "aggregate_type": aggregate_type,
                "id": str(aggregate_id),
                "scope_type": "tenant",
                "scope_ref": f"tenant:{tenant_id}",
                "status": status,
                "version": version,
                "occurred_at_utc": _now().isoformat(),
                **dict(payload),
            },
        )
    )


class RecoveryService:
    """Use cases for typed, full-invoice recovery."""

    @staticmethod
    def _load_target(
        db: Session, *, app_user_id: UUID, invoice_id: UUID, lock: bool = True
    ) -> tuple[AppUser, ChargingSession, Invoice]:
        user_query = db.query(AppUser).filter(AppUser.id == app_user_id)
        invoice_query = db.query(Invoice).filter(Invoice.id == invoice_id)
        if lock:
            user_query = user_query.with_for_update()
            invoice_query = invoice_query.with_for_update()
        user = user_query.first()
        invoice = invoice_query.first()
        session = (
            db.query(ChargingSession)
            .filter(
                ChargingSession.id == invoice.session_id,
                ChargingSession.app_user_id == app_user_id,
                ChargingSession.tenant_id == invoice.tenant_id,
            )
            .with_for_update()
            .first()
            if invoice is not None
            else None
        )
        if user is None or invoice is None or session is None:
            raise RecoveryTargetInvalid("Recovery target is not available")
        if invoice.status != "pending" or _money(invoice.total_amount) <= 0:
            raise RecoveryNotAllowed("Invoice is not recoverable")
        return user, session, invoice

    @staticmethod
    def _existing(
        db: Session,
        *,
        app_user_id: UUID,
        idempotency_key: str,
        fingerprint: str,
    ) -> RecoveryAttempt | None:
        existing = (
            db.query(RecoveryAttempt)
            .filter(
                RecoveryAttempt.app_user_id == app_user_id,
                RecoveryAttempt.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing is not None and existing.request_fingerprint != fingerprint:
            raise IdempotencyConflict("Idempotency key fingerprint does not match")
        return existing

    @staticmethod
    def _committed(db: Session, invoice_id: UUID) -> PaymentAllocation | None:
        return (
            db.query(PaymentAllocation)
            .filter(
                PaymentAllocation.invoice_id == invoice_id,
                PaymentAllocation.status == "committed",
            )
            .with_for_update()
            .first()
        )

    @staticmethod
    def _attempt_number(db: Session, invoice_id: UUID) -> int:
        last = (
            db.query(RecoveryAttempt)
            .filter(RecoveryAttempt.invoice_id == invoice_id)
            .order_by(RecoveryAttempt.attempt_number.desc())
            .with_for_update()
            .first()
        )
        return (last.attempt_number if last else 0) + 1

    @staticmethod
    def _saved_card(
        db: Session, *, app_user_id: UUID, method_id: UUID | None
    ) -> AppUserPaymentMethod:
        if method_id is None:
            raise RecoveryTargetInvalid("Saved payment method is required")
        saved = (
            db.query(AppUserPaymentMethod)
            .filter(
                AppUserPaymentMethod.id == method_id,
                AppUserPaymentMethod.app_user_id == app_user_id,
                AppUserPaymentMethod.provider == "mercadopago",
            )
            .first()
        )
        if saved is None:
            raise RecoveryTargetInvalid("Saved payment method is not available")
        return saved

    @staticmethod
    def _merchant(tenant_id: UUID) -> dict[str, str]:
        try:
            context = PlatformMerchantAccountResolver().resolve(
                operator_tenant_id=tenant_id,
                payment_purpose=PaymentPurpose.UNPAID_CHARGE,
            )
        except MerchantContextError as exc:
            raise RecoveryUnknown("Recovery merchant is unavailable") from exc
        return context.safe_snapshot()

    def prepare(
        self,
        db: Session,
        *,
        app_user_id: UUID,
        invoice_id: UUID,
        method: str,
        saved_payment_method_id: UUID | None,
        idempotency_key: str,
    ) -> RecoveryPrepared:
        if method not in RECOVERY_METHODS:
            raise RecoveryTargetInvalid("Unsupported recovery method")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise RecoveryTargetInvalid("Idempotency-Key is required")
        fingerprint = _fingerprint(invoice_id, method, saved_payment_method_id)
        existing = self._existing(
            db,
            app_user_id=app_user_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
        if existing is not None:
            order = self._payment_order_for_attempt(db, existing.id)
            return RecoveryPrepared(existing, order, reused=True)

        user, session, invoice = self._load_target(
            db, app_user_id=app_user_id, invoice_id=invoice_id
        )
        committed = self._committed(db, invoice.id)
        if committed is not None:
            raise RecoveryNotAllowed("Invoice already has a committed allocation")
        if method == "saved_card":
            self._saved_card(
                db, app_user_id=app_user_id, method_id=saved_payment_method_id
            )
        if method != "wallet":
            site_id = (
                db.query(ChargePoint.site_id)
                .filter(
                    ChargePoint.id == session.charge_point_id,
                    ChargePoint.tenant_id == session.tenant_id,
                )
                .scalar()
            )
            try:
                merchant = self._merchant(invoice.tenant_id)
                RuntimeRailControlService.require_payment_creation_open(
                    db,
                    provider=str(merchant["provider"]),
                    tenant_id=invoice.tenant_id,
                    site_id=site_id,
                )
            except (RailClosed, RailStateUnknown) as exc:
                raise RecoveryRailClosed(str(exc)) from exc
        target = _money(invoice.total_amount)
        attempt_id = uuid4()
        now = _now()
        attempt = RecoveryAttempt(
            id=attempt_id,
            tenant_id=invoice.tenant_id,
            app_user_id=user.id,
            invoice_id=invoice.id,
            session_id=session.id,
            attempt_number=self._attempt_number(db, invoice.id),
            method=method,
            provider="mercadopago" if method != "wallet" else None,
            provider_account_ref=(
                self._merchant(invoice.tenant_id).get("merchant_account_ref")
                if method != "wallet"
                else None
            ),
            provider_operation_key=(
                f"recovery-attempt:{attempt_id}" if method != "wallet" else None
            ),
            target_amount=target,
            allocated_amount=Decimal("0.00"),
            currency=COP,
            status="processing" if method == "wallet" else "action_required",
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            audit_reference=_audit(attempt_id),
            expires_at=now + timedelta(minutes=30),
        )
        db.add(attempt)
        payment_order = None
        if method != "wallet":
            payment_order = PaymentOrder(
                app_user_id=user.id,
                type="charging",
                amount=target,
                currency=COP,
                payment_provider="mercadopago",
                idempotency_key=f"unpaid-charge:{invoice.id}:{attempt_id}",
                status="created",
                expires_at=now + timedelta(minutes=30),
                payment_deadline_at=now + timedelta(minutes=60),
                order_metadata={
                    "schema_version": 1,
                    "payment_purpose": PaymentPurpose.UNPAID_CHARGE.value,
                    "settlement_method": "direct_card",
                    "recovery_attempt_id": str(attempt_id),
                    "invoice_id": str(invoice.id),
                    "session_id": str(session.id),
                    "operator_tenant_id": str(invoice.tenant_id),
                    "merchant": self._merchant(invoice.tenant_id),
                    "provider_hints": {},
                },
            )
            db.add(payment_order)
        _outbox(
            db,
            tenant_id=invoice.tenant_id,
            aggregate_type="recovery_attempt",
            aggregate_id=attempt.id,
            event_type="recovery.attempt.created",
            idempotency_key=f"recovery-created:{attempt.id}",
            status=attempt.status,
            version=attempt.version,
            payload={
                "entity_reference": str(invoice.id),
                "invoice_id": str(invoice.id),
                "session_id": str(session.id),
                "amount": format(target, ".2f"),
                "currency": COP,
                "method": method,
                "reason_code": "recovery_started",
                "idempotency_key": idempotency_key,
            },
        )
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            replay = self._existing(
                db,
                app_user_id=app_user_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )
            if replay is not None:
                return RecoveryPrepared(
                    replay, self._payment_order_for_attempt(db, replay.id), True
                )
            raise RecoveryConflict("Recovery attempt could not be created") from exc
        return RecoveryPrepared(attempt, payment_order, False)

    @staticmethod
    def _payment_order_for_attempt(
        db: Session, attempt_id: UUID
    ) -> PaymentOrder | None:
        candidates = (
            db.query(PaymentOrder)
            .filter(PaymentOrder.payment_provider == "mercadopago")
            .order_by(PaymentOrder.created_at.desc())
            .all()
        )
        for order in candidates:
            if str((order.order_metadata or {}).get("recovery_attempt_id")) == str(
                attempt_id
            ):
                return order
        return None

    def attach_checkout(
        self,
        db: Session,
        *,
        attempt_id: UUID,
        checkout_session_id: str,
        checkout_url: str,
        expires_at: datetime,
    ) -> None:
        attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.id == attempt_id).with_for_update().one()
        order = self._payment_order_for_attempt(db, attempt_id)
        if order is None:
            raise RecoveryTargetInvalid("Recovery payment order is unavailable")
        metadata = dict(order.order_metadata or {})
        metadata.update(
            {
                "checkout_session_id": checkout_session_id,
                "checkout_url": checkout_url,
                "checkout_expires_at": expires_at.astimezone(timezone.utc).isoformat(),
            }
        )
        order.order_metadata = metadata
        db.commit()

    def settle_wallet(
        self,
        db: Session,
        *,
        attempt_id: UUID,
    ) -> RecoveryAttempt:
        attempt = (
            db.query(RecoveryAttempt)
            .filter(RecoveryAttempt.id == attempt_id)
            .with_for_update()
            .one_or_none()
        )
        if attempt is None:
            raise RecoveryTargetInvalid("Recovery attempt is not available")
        if attempt.method != "wallet":
            return attempt
        if attempt.status == "allocated":
            return attempt
        user, session, invoice = self._load_target(
            db, app_user_id=attempt.app_user_id, invoice_id=attempt.invoice_id
        )
        committed = self._committed(db, invoice.id)
        if committed is not None:
            attempt.status = "duplicate_approved"
            attempt.reason_code = "duplicate_approval"
            attempt.version += 1
            db.commit()
            return attempt
        target = _money(invoice.total_amount)
        balance = _money(user.balance or 0)
        if balance < target:
            attempt.status = "declined"
            attempt.reason_code = "insufficient_wallet_balance"
            attempt.version += 1
            _outbox(
                db,
                tenant_id=attempt.tenant_id,
                aggregate_type="recovery_attempt",
                aggregate_id=attempt.id,
                event_type="recovery.attempt.state_changed",
                idempotency_key=f"recovery-state:{attempt.id}:{attempt.version}",
                status=attempt.status,
                version=attempt.version,
                payload={"reason_code": attempt.reason_code},
            )
            db.commit()
            return attempt
        wallet_key = f"recovery-wallet:{attempt.id}"
        existing_tx = (
            db.query(AppWalletTransaction)
            .filter(AppWalletTransaction.app_user_id == user.id, AppWalletTransaction.idempotency_key == wallet_key)
            .with_for_update()
            .first()
        )
        if existing_tx is not None:
            raise RecoveryConflict("Wallet recovery transaction exists without allocation")
        allocation = PaymentAllocation(
            tenant_id=attempt.tenant_id,
            invoice_id=invoice.id,
            recovery_attempt_id=attempt.id,
            wallet_transaction_id=None,
            method="wallet",
            provider="app_wallet",
            amount=target,
            currency=COP,
            status="committed",
            audit_reference=_audit(attempt.id),
            committed_at=_now(),
        )
        db.add(allocation)
        db.flush()
        user.balance = balance - target
        tx = AppWalletTransaction(
            transaction_number=f"recovery-wallet:{attempt.id}",
            app_user_id=user.id,
            invoice_id=invoice.id,
            operator_tenant_id=invoice.tenant_id,
            type="charge",
            amount=-target,
            description="PAY-MP-002 unpaid charge recovery",
            idempotency_key=wallet_key,
        )
        db.add(tx)
        db.flush()
        allocation.wallet_transaction_id = tx.id
        attempt.status = "allocated"
        attempt.allocated_amount = target
        attempt.completed_at = _now()
        attempt.version += 1
        _outbox(
            db,
            tenant_id=attempt.tenant_id,
            aggregate_type="payment_allocation",
            aggregate_id=allocation.id,
            event_type="payment.allocation.committed",
            idempotency_key=f"allocation-committed:{allocation.id}",
            status=allocation.status,
            version=allocation.winner_version,
            payload={
                "entity_reference": str(invoice.id),
                "invoice_id": str(invoice.id),
                "recovery_attempt_id": str(attempt.id),
                "amount": format(target, ".2f"),
                "currency": COP,
                "method": "wallet",
                "reason_code": "recovery_allocated",
                "idempotency_key": attempt.idempotency_key,
            },
        )
        from app.services.financial_eligibility import enqueue_financial_eligibility_recheck

        enqueue_financial_eligibility_recheck(
            db,
            app_user_id=attempt.app_user_id,
            tenant_id=attempt.tenant_id,
            source_type="payment_allocation",
            source_id=allocation.id,
            source_version=allocation.winner_version,
            reason_code="allocation_changed",
        )
        db.commit()
        return attempt

    def apply_card_result(
        self,
        db: Session,
        *,
        attempt_id: UUID,
        payment_order_id: UUID,
        provider_status: str,
        provider_payment_ref: str | None,
        provider_amount: Decimal,
        provider_currency: str,
    ) -> bool:
        """Apply an already validated provider fact; return duplicate winner flag."""
        attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.id == attempt_id).with_for_update().one()
        invoice = db.query(Invoice).filter(Invoice.id == attempt.invoice_id).with_for_update().one()
        attempt.provider_payment_ref = provider_payment_ref or attempt.provider_payment_ref
        normalized = provider_status.lower()
        if normalized == "approved":
            if _money(provider_amount) != _money(attempt.target_amount) or provider_currency.upper() != COP:
                attempt.status = "unknown"
                attempt.reason_code = "provider_amount_or_currency_mismatch"
                attempt.version += 1
                from app.services.financial_eligibility import enqueue_financial_eligibility_recheck

                enqueue_financial_eligibility_recheck(
                    db,
                    app_user_id=attempt.app_user_id,
                    tenant_id=attempt.tenant_id,
                    source_type="recovery_attempt",
                    source_id=attempt.id,
                    source_version=attempt.version,
                    reason_code=attempt.reason_code,
                )
                return False
            winner = self._committed(db, invoice.id)
            if winner is not None and winner.recovery_attempt_id != attempt.id:
                attempt.status = "duplicate_approved"
                attempt.reason_code = "duplicate_approval"
                attempt.allocated_amount = Decimal("0.00")
                attempt.version += 1
                from app.services.financial_eligibility import enqueue_financial_eligibility_recheck

                enqueue_financial_eligibility_recheck(
                    db,
                    app_user_id=attempt.app_user_id,
                    tenant_id=attempt.tenant_id,
                    source_type="recovery_attempt",
                    source_id=attempt.id,
                    source_version=attempt.version,
                    reason_code=attempt.reason_code,
                )
                return True
            existing = db.query(PaymentAllocation).filter(PaymentAllocation.recovery_attempt_id == attempt.id).with_for_update().first()
            if existing is None:
                allocation = PaymentAllocation(
                    tenant_id=attempt.tenant_id,
                    invoice_id=attempt.invoice_id,
                    recovery_attempt_id=attempt.id,
                    payment_order_id=payment_order_id,
                    method=attempt.method,
                    provider=attempt.provider or "mercadopago",
                    amount=_money(attempt.target_amount),
                    currency=COP,
                    status="committed",
                    audit_reference=_audit(attempt.id),
                    committed_at=_now(),
                )
                db.add(allocation)
                db.flush()
                _outbox(
                    db,
                    tenant_id=attempt.tenant_id,
                    aggregate_type="payment_allocation",
                    aggregate_id=allocation.id,
                    event_type="payment.allocation.committed",
                    idempotency_key=f"allocation-committed:{allocation.id}",
                    status="committed",
                    version=allocation.winner_version,
                    payload={
                        "entity_reference": str(invoice.id),
                        "invoice_id": str(invoice.id),
                        "recovery_attempt_id": str(attempt.id),
                        "amount": format(_money(attempt.target_amount), ".2f"),
                        "currency": COP,
                        "method": attempt.method,
                        "reason_code": "recovery_allocated",
                        "idempotency_key": attempt.idempotency_key,
                    },
                )
                from app.services.financial_eligibility import enqueue_financial_eligibility_recheck

                enqueue_financial_eligibility_recheck(
                    db,
                    app_user_id=attempt.app_user_id,
                    tenant_id=attempt.tenant_id,
                    source_type="payment_allocation",
                    source_id=allocation.id,
                    source_version=allocation.winner_version,
                    reason_code="allocation_changed",
                )
            attempt.status = "allocated"
            attempt.allocated_amount = _money(attempt.target_amount)
            attempt.completed_at = _now()
            attempt.reason_code = "recovery_allocated"
        elif normalized in {"processing", "action_required"}:
            attempt.status = "action_required" if normalized == "action_required" else "processing"
            attempt.reason_code = "recovery_processing"
        elif normalized in {"declined", "expired", "voided"}:
            attempt.status = "declined" if normalized == "declined" else "expired"
            attempt.reason_code = f"provider_{normalized}"
        else:
            attempt.status = "unknown"
            attempt.reason_code = "provider_status_unknown"
        attempt.version += 1
        from app.services.financial_eligibility import enqueue_financial_eligibility_recheck

        enqueue_financial_eligibility_recheck(
            db,
            app_user_id=attempt.app_user_id,
            tenant_id=attempt.tenant_id,
            source_type="recovery_attempt",
            source_id=attempt.id,
            source_version=attempt.version,
            reason_code=attempt.reason_code or "recovery_state_changed",
        )
        return False

    def mark_unknown(self, db: Session, *, attempt_id: UUID, reason: str) -> None:
        attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.id == attempt_id).with_for_update().one_or_none()
        if attempt is None or attempt.status == "allocated":
            return
        attempt.status = "unknown"
        attempt.reason_code = reason
        attempt.version += 1
        _outbox(
            db,
            tenant_id=attempt.tenant_id,
            aggregate_type="recovery_attempt",
            aggregate_id=attempt.id,
            event_type="recovery.attempt.state_changed",
            idempotency_key=f"recovery-state:{attempt.id}:{attempt.version}",
            status=attempt.status,
            version=attempt.version,
            payload={"reason_code": reason},
        )
        from app.services.financial_eligibility import enqueue_financial_eligibility_recheck

        enqueue_financial_eligibility_recheck(
            db,
            app_user_id=attempt.app_user_id,
            tenant_id=attempt.tenant_id,
            source_type="recovery_attempt",
            source_id=attempt.id,
            source_version=attempt.version,
            reason_code=reason,
        )
