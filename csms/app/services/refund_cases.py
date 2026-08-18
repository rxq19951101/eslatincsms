"""PAY-MP-002 refund and chargeback authority.

This module owns the typed BE-207 facts.  Provider calls are deliberately made
after the approval transaction has committed; only a provider-confirmed query
fact can move a refund attempt to a completed state.  The existing
``PaymentRefundService`` remains the P001 compatibility path and is not used
as the P002 authority.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from sqlalchemy.orm import Session

from app.database.base import tenant_id_context
from app.database.models import (
    AdminUser,
    AppUser,
    AppWalletTransaction,
    AuditLog,
    ChargebackCase,
    Invoice,
    PaymentAllocation,
    PaymentOrder,
    RefundApproval,
    RefundAttempt,
    RefundCase,
)
from app.services.financial_eligibility import enqueue_financial_eligibility_recheck
from app.services.payment_providers.base import (
    ProviderCapabilityError,
    RefundCapabilityCommand,
    RefundCapabilityFacts,
    RefundCapabilityResult,
)
from app.services.payment_providers.merchant_context import PaymentPurpose
from app.services.payment_reconciliation import PaymentReconciliationError, PaymentReconciliationService


SYSTEM_ACTOR_ID = uuid5(NAMESPACE_URL, "https://eslatin.com.co/system/payment-facts")
REFUND_CASE_STATUSES = {
    "submitted", "under_review", "approved", "provider_processing",
    "partially_refunded", "refunded", "rejected", "manual_review", "unknown",
}
CHARGEBACK_STATUSES = {
    "received", "under_review", "hold", "representment", "won", "lost",
    "reversed", "unknown",
}
CONFIRMED_REFUND_ATTEMPT_STATUSES = {"partially_refunded", "refunded"}
FINAL_CHARGEBACK_STATUSES = {"won", "lost", "reversed"}


class RefundCaseError(RuntimeError):
    code = "REQUEST_INVALID"
    status_code = 422
    retryable = False


class RefundNotFound(RefundCaseError):
    code = "RESOURCE_NOT_FOUND"
    status_code = 404


class RefundPermissionDenied(RefundCaseError):
    code = "PERMISSION_DENIED"
    status_code = 403


class RefundIdempotencyConflict(RefundCaseError):
    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409


class RefundVersionConflict(RefundCaseError):
    code = "RESOURCE_VERSION_CONFLICT"
    status_code = 409


class RefundApprovalConflict(RefundCaseError):
    code = "APPROVAL_CONFLICT"
    status_code = 409


class RefundInvalidTarget(RefundCaseError):
    code = "REQUEST_INVALID"
    status_code = 422


class RefundCursorInvalid(RefundCaseError):
    code = "CURSOR_INVALID"
    status_code = 409


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError) as exc:
        raise RefundInvalidTarget("Invalid monetary value") from exc
    if not amount.is_finite() or amount < 0:
        raise RefundInvalidTarget("Invalid monetary value")
    return amount


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _safe_uuid(value: UUID | str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise RefundNotFound("Resource not found") from exc


def _safe_reference(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:255] if text else None


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _opaque_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        offset = int(decoded["offset"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError, binascii.Error) as exc:
        raise RefundCursorInvalid("Cursor is invalid") from exc
    if offset < 0:
        raise RefundCaseError("Cursor is invalid")
    return offset


def _audit_metadata(log: AuditLog) -> dict[str, Any]:
    return dict(log.audit_metadata) if isinstance(log.audit_metadata, Mapping) else {}


class RefundCaseService:
    """Application service for typed RefundCase/ChargebackCase facts."""

    def __init__(self, *, reconciliation: PaymentReconciliationService | None = None) -> None:
        self._reconciliation = reconciliation or PaymentReconciliationService()

    @staticmethod
    def _scope_tenant(admin: AdminUser | None, requested: UUID | None = None) -> UUID | None:
        if admin is not None and admin.is_super_admin:
            return requested
        current = tenant_id_context.get()
        if current is None:
            raise RefundPermissionDenied("Tenant context required")
        if requested is not None and requested != current:
            raise RefundPermissionDenied("Resource is outside the tenant scope")
        return current

    @staticmethod
    def _audit(
        db: Session,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        actor_type: str,
        action: str,
        resource_type: str,
        resource_id: UUID | str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        result: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditLog:
        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            before_data=dict(before) if before is not None else None,
            after_data=dict(after) if after is not None else None,
            audit_metadata={"result": result, **dict(metadata or {})},
        )
        db.add(audit)
        db.flush()
        return audit

    @staticmethod
    def _find_idempotent_audit(
        db: Session,
        *,
        tenant_id: UUID,
        action: str,
        resource_type: str,
        idempotency_hash: str,
    ) -> AuditLog | None:
        logs = (
            db.query(AuditLog)
            .filter(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action == action,
                AuditLog.resource_type == resource_type,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(100)
            .all()
        )
        for log in logs:
            if _audit_metadata(log).get("idempotency_hash") == idempotency_hash:
                return log
        return None

    @staticmethod
    def _case_from_audit(log: AuditLog | None, db: Session) -> RefundCase | None:
        if log is None or not log.resource_id:
            return None
        try:
            return db.query(RefundCase).filter(RefundCase.id == UUID(log.resource_id)).first()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _allocation_context(db: Session, allocation_id: UUID, tenant_id: UUID | None = None):
        query = db.query(PaymentAllocation).filter(PaymentAllocation.id == allocation_id)
        if tenant_id is not None:
            query = query.filter(PaymentAllocation.tenant_id == tenant_id)
        allocation = query.with_for_update().first()
        if allocation is None or allocation.status != "committed":
            raise RefundInvalidTarget("Refund target is not a confirmed payment allocation")
        invoice = (
            db.query(Invoice)
            .filter(Invoice.id == allocation.invoice_id, Invoice.tenant_id == allocation.tenant_id)
            .with_for_update()
            .first()
        )
        if invoice is None:
            raise RefundInvalidTarget("Refund target is not available")
        app_user_id = None
        if allocation.recovery_attempt_id:
            from app.database.models import RecoveryAttempt
            recovery = db.query(RecoveryAttempt).filter(RecoveryAttempt.id == allocation.recovery_attempt_id).first()
            app_user_id = recovery.app_user_id if recovery else None
        if app_user_id is None and allocation.payment_order_id:
            order = db.query(PaymentOrder).filter(PaymentOrder.id == allocation.payment_order_id).first()
            app_user_id = order.app_user_id if order else None
        if app_user_id is None:
            raise RefundInvalidTarget("Refund target owner is unavailable")
        return allocation, invoice, app_user_id

    @staticmethod
    def _confirmed_for_allocation(db: Session, allocation_id: UUID) -> Decimal:
        cases = db.query(RefundCase).filter(RefundCase.payment_allocation_id == allocation_id).all()
        if not cases:
            return Decimal("0.00")
        total = Decimal("0.00")
        for case in cases:
            attempts = db.query(RefundAttempt).filter(RefundAttempt.refund_case_id == case.id).all()
            total += sum((_money(row.amount) for row in attempts if row.status in CONFIRMED_REFUND_ATTEMPT_STATUSES), Decimal("0.00"))
        return total

    @staticmethod
    def _confirmed_for_case(db: Session, case_id: UUID) -> Decimal:
        rows = db.query(RefundAttempt).filter(RefundAttempt.refund_case_id == case_id).all()
        return sum((_money(row.amount) for row in rows if row.status in CONFIRMED_REFUND_ATTEMPT_STATUSES), Decimal("0.00"))

    def _server_target(self, db: Session, allocation_id: UUID, requested: Decimal, tenant_id: UUID | None):
        allocation, invoice, app_user_id = self._allocation_context(db, allocation_id, tenant_id)
        paid = _money(allocation.amount)
        confirmed = self._confirmed_for_allocation(db, allocation.id)
        remaining = paid - confirmed
        if remaining <= 0 or requested <= 0 or requested > remaining:
            raise RefundInvalidTarget("Requested refund exceeds the confirmed paid amount")
        if allocation.currency != "COP" or invoice.tenant_id != allocation.tenant_id:
            raise RefundInvalidTarget("Refund currency or ownership is invalid")
        return allocation, invoice, app_user_id, paid, confirmed, remaining

    def _projection_timeline(self, db: Session, resource_type: str, resource_id: UUID) -> list[dict[str, Any]]:
        logs = (
            db.query(AuditLog)
            .filter(AuditLog.resource_type == resource_type, AuditLog.resource_id == str(resource_id))
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        result = []
        for log in logs:
            metadata = _audit_metadata(log)
            after = log.after_data if isinstance(log.after_data, Mapping) else {}
            result.append({
                "event_id": str(log.id),
                "type": log.action,
                "status": after.get("status"),
                "occurred_at": _iso(log.created_at),
                "actor": self._actor_projection(db, log.actor_id),
                "reason_code": after.get("reason_code") or metadata.get("reason_code"),
                "reference": log.resource_id,
            })
        return result

    @staticmethod
    def _actor_projection(db: Session, actor_id: UUID | None) -> dict[str, Any] | None:
        if actor_id is None or actor_id == SYSTEM_ACTOR_ID:
            return None
        actor = db.query(AdminUser).filter(AdminUser.id == actor_id).first()
        if actor is None:
            return {"id": str(actor_id), "display_name": "authorized actor", "role_label": "admin"}
        return {"id": str(actor.id), "display_name": actor.full_name or actor.username, "role_label": "admin"}

    def project_refund(self, db: Session, case: RefundCase, *, current_actor_id: UUID | None = None) -> dict[str, Any]:
        approval = (
            db.query(RefundApproval).filter(RefundApproval.refund_case_id == case.id)
            .order_by(RefundApproval.created_at.desc()).first()
        )
        attempts = db.query(RefundAttempt).filter(RefundAttempt.refund_case_id == case.id).order_by(RefundAttempt.created_at.desc()).all()
        provider_ref = next((row.provider_refund_ref for row in attempts if row.provider_refund_ref), None)
        allowed = ["view", "refresh"]
        if approval and approval.status == "pending" and case.status in {"submitted", "under_review"}:
            if current_actor_id is None or current_actor_id != approval.initiator_admin_id:
                allowed += ["approve", "reject"]
        approval_projection = {
            "status": approval.status if approval else "not_required",
            "initiator": self._actor_projection(db, approval.initiator_admin_id) if approval else None,
            "approver": self._actor_projection(db, approval.approver_admin_id) if approval and approval.approver_admin_id else None,
            "requested_at": _iso(approval.requested_at) if approval else None,
            "decided_at": _iso(approval.decided_at) if approval else None,
            "expires_at": _iso(approval.expires_at) if approval else None,
            "version": approval.version if approval else 1,
        }
        return {
            "case_id": str(case.id),
            "target": {"resource_type": "payment_allocation", "resource_id": str(case.payment_allocation_id)},
            "requested_amount": format(_money(case.requested_amount), ".2f"),
            "approved_amount": format(_money(case.approved_amount), ".2f"),
            "confirmed_refunded_amount": format(_money(case.refunded_amount), ".2f"),
            "currency": case.currency,
            "status": case.status if case.status in REFUND_CASE_STATUSES else "unknown",
            "approval": approval_projection,
            "provider_reference": provider_ref,
            "timeline": self._projection_timeline(db, "refund_case", case.id),
            "audit_references": [case.audit_reference] + [row.audit_reference for row in attempts if row.audit_reference],
            "allowed_actions": allowed,
            "version": case.version,
            "created_at": _iso(case.created_at),
            "updated_at": _iso(case.updated_at),
        }

    def project_chargeback(self, db: Session, case: ChargebackCase) -> dict[str, Any]:
        logs = (
            db.query(AuditLog).filter(
                AuditLog.resource_type == "chargeback_case",
                AuditLog.resource_id == str(case.id),
            ).order_by(AuditLog.created_at.desc()).all()
        )
        fact = {}
        for log in logs:
            metadata = _audit_metadata(log)
            if isinstance(metadata.get("canonical_fact"), Mapping):
                fact = dict(metadata["canonical_fact"])
                break
        status = case.status if case.status in CHARGEBACK_STATUSES else "unknown"
        funds_state = fact.get("funds_state") or ({
            "received": "held", "under_review": "held", "hold": "held",
            "representment": "held", "lost": "held", "won": "released",
            "reversed": "released", "unknown": "unknown",
        }.get(status, "unknown"))
        return {
            "case_id": str(case.id),
            "payment_reference": fact.get("payment_reference") or case.provider_dispute_ref,
            "invoice_reference": fact.get("invoice_reference") or str(case.invoice_id),
            "amount": format(_money(case.disputed_amount), ".2f"),
            "currency": case.currency,
            "status": status,
            "deadline_at": fact.get("deadline_at"),
            "funds_state": funds_state,
            "timeline": self._projection_timeline(db, "chargeback_case", case.id),
            "allowed_actions": ["view", "refresh"],
            "version": case.version,
            "created_at": _iso(case.created_at),
            "updated_at": _iso(case.updated_at),
        }

    def create_refund_case(
        self,
        db: Session,
        *,
        actor: AdminUser,
        allocation_id: UUID | str,
        requested_amount: Decimal,
        currency: str,
        reason_code: str,
        reason: str,
        idempotency_key: str,
    ) -> RefundCase:
        if not idempotency_key or len(idempotency_key.strip()) > 255:
            raise RefundInvalidTarget("Idempotency-Key is required")
        allocation_uuid = _safe_uuid(allocation_id)
        requested = _money(requested_amount)
        request_payload = {
            "target": {"resource_type": "payment_allocation", "resource_id": str(allocation_uuid)},
            "requested_amount": format(requested, ".2f"), "currency": currency,
            "reason_code": reason_code, "reason": reason,
        }
        fingerprint = _fingerprint(request_payload)
        idem_hash = hashlib.sha256(idempotency_key.strip().encode("utf-8")).hexdigest()
        tenant_hint = None if actor.is_super_admin else self._scope_tenant(actor)
        existing_audit = self._find_idempotent_audit(
            db, tenant_id=tenant_hint if tenant_hint is not None else allocation_uuid,  # replaced after target resolution
            action="refund.case.submitted", resource_type="refund_case", idempotency_hash=idem_hash,
        ) if tenant_hint is not None else None
        if existing_audit is not None:
            if _audit_metadata(existing_audit).get("request_fingerprint") != fingerprint:
                raise RefundIdempotencyConflict("Idempotency-Key was reused with a different request")
            case = self._case_from_audit(existing_audit, db)
            if case is not None:
                return case

        tenant_filter = tenant_hint
        allocation, invoice, app_user_id, paid, confirmed, remaining = self._server_target(
            db, allocation_uuid, requested, tenant_filter
        )
        existing_audit = self._find_idempotent_audit(
            db, tenant_id=allocation.tenant_id, action="refund.case.submitted",
            resource_type="refund_case", idempotency_hash=idem_hash,
        )
        if existing_audit is not None:
            if _audit_metadata(existing_audit).get("request_fingerprint") != fingerprint:
                raise RefundIdempotencyConflict("Idempotency-Key was reused with a different request")
            case = self._case_from_audit(existing_audit, db)
            if case is not None:
                return case

        if currency != allocation.currency:
            raise RefundInvalidTarget("Refund currency does not match the paid allocation")
        case = RefundCase(
            tenant_id=allocation.tenant_id,
            app_user_id=app_user_id,
            invoice_id=invoice.id,
            payment_allocation_id=allocation.id,
            requested_amount=requested,
            approved_amount=Decimal("0.00"),
            refunded_amount=Decimal("0.00"),
            currency=currency,
            reason_code=reason_code,
            status="submitted",
            audit_reference=f"pay-mp-002:refund:{uuid4()}",
        )
        db.add(case)
        db.flush()
        approval = RefundApproval(
            tenant_id=allocation.tenant_id,
            refund_case_id=case.id,
            initiator_admin_id=actor.id,
            requested_amount=requested,
            currency=currency,
            status="pending",
            expires_at=_now(),
            audit_reference=f"pay-mp-002:refund-approval:{uuid4()}",
        )
        approval.expires_at = _now().replace(microsecond=0)
        from datetime import timedelta
        approval.expires_at = approval.expires_at + timedelta(hours=24)
        db.add(approval)
        self._audit(
            db, tenant_id=allocation.tenant_id, actor_id=actor.id, actor_type="admin",
            action="refund.case.submitted", resource_type="refund_case", resource_id=case.id,
            before=None,
            after={"status": case.status, "requested_amount": format(requested, ".2f"), "reason_code": reason_code},
            result="accepted",
            metadata={"idempotency_hash": idem_hash, "request_fingerprint": fingerprint, "reason": reason[:500]},
        )
        db.commit()
        db.refresh(case)
        return case

    def _provider_payment(self, db: Session, allocation: PaymentAllocation) -> tuple[PaymentOrder, Any, Any]:
        if not allocation.payment_order_id:
            raise RefundCaseError("Provider payment reference is unavailable")
        order = db.query(PaymentOrder).filter(PaymentOrder.id == allocation.payment_order_id).first()
        if order is None:
            raise RefundCaseError("Provider payment reference is unavailable")
        payment_ref = (order.order_metadata or {}).get("provider_reference") or order.mercadopago_payment_id
        if not payment_ref:
            raise RefundCaseError("Provider payment reference is unavailable")
        context = self._reconciliation.merchant_context_for_order(payment_order=order, purpose=PaymentPurpose.REFUND)
        provider = self._reconciliation._provider_registry.get(order.payment_provider)
        return order, provider, (str(payment_ref), context)

    @staticmethod
    def _provider_facts(provider: Any, payment_ref: str, context: Any) -> RefundCapabilityFacts:
        capability = getattr(provider, "query_refund_capability", None) or getattr(provider, "query_refund_facts", None)
        if not callable(capability):
            raise RefundCaseError("Provider refund query is unavailable")
        return capability(payment_ref, merchant_context=context)

    @staticmethod
    def _provider_create(provider: Any, *, payment_ref: str, amount: Decimal, currency: str, context: Any, operation_key: str, case_id: UUID) -> RefundCapabilityResult:
        capability = getattr(provider, "create_refund_capability", None)
        if callable(capability):
            return capability(
                RefundCapabilityCommand(
                    payment_ref=payment_ref, amount=amount, currency=currency,
                    merchant_account_ref=context.merchant_account_ref,
                    references={"refund_case_id": str(case_id)},
                ),
                merchant_context=context, idempotency_key=operation_key,
            )
        raise RefundCaseError("Provider refund capability is unavailable")

    def _finish_attempt(
        self, db: Session, case_id: UUID, attempt_id: UUID, *, status: str,
        reason_code: str | None = None, provider_ref: str | None = None,
        actor_id: UUID = SYSTEM_ACTOR_ID,
    ) -> RefundCase:
        case = db.query(RefundCase).filter(RefundCase.id == case_id).with_for_update().first()
        attempt = db.query(RefundAttempt).filter(RefundAttempt.id == attempt_id).with_for_update().first()
        if case is None or attempt is None:
            raise RefundNotFound("Refund case not found")
        before = {"status": case.status, "attempt_status": attempt.status}
        attempt.status = status
        attempt.reason_code = reason_code
        attempt.provider_refund_ref = provider_ref
        attempt.version += 1
        attempt.completed_at = _now() if status in {"refunded", "partially_refunded", "failed", "manual_review"} else None
        case.status = "refunded" if status == "refunded" else "partially_refunded" if status == "partially_refunded" else "manual_review" if status == "manual_review" else "unknown"
        case.version += 1
        case.refunded_amount = self._confirmed_for_case(db, case.id)
        case.resolved_at = _now() if case.status in {"refunded", "manual_review"} else None
        after = {"status": case.status, "attempt_status": attempt.status, "reason_code": reason_code}
        self._audit(
            db, tenant_id=case.tenant_id, actor_id=actor_id, actor_type="system",
            action="refund.case.state_changed", resource_type="refund_case", resource_id=case.id,
            before=before, after=after, result="recorded", metadata={"attempt_id": str(attempt.id)},
        )
        if status in CONFIRMED_REFUND_ATTEMPT_STATUSES or status in {"unknown", "manual_review"}:
            allocation = db.query(PaymentAllocation).filter(PaymentAllocation.id == case.payment_allocation_id).first()
            if allocation and allocation.payment_order_id and case.status == "refunded":
                order = db.query(PaymentOrder).filter(PaymentOrder.id == allocation.payment_order_id).with_for_update().first()
                if order is not None and order.status in {"approved", "refunded"}:
                    order.status = "refunded"
                invoice = db.query(Invoice).filter(Invoice.id == case.invoice_id).with_for_update().first()
                if invoice is not None and self._confirmed_for_allocation(db, allocation.id) >= _money(allocation.amount):
                    invoice.status = "refunded"
            enqueue_financial_eligibility_recheck(
                db, app_user_id=case.app_user_id, tenant_id=case.tenant_id,
                source_type="refund_case", source_id=case.id,
                source_version=case.version,
                reason_code="refund_fact_changed" if status in CONFIRMED_REFUND_ATTEMPT_STATUSES else "refund_fact_unknown",
            )
        db.commit()
        db.refresh(case)
        return case

    def approve_refund_case(
        self, db: Session, *, actor: AdminUser, case_id: UUID | str,
        decision: str, expected_version: int, reason: str, idempotency_key: str,
    ) -> RefundCase:
        case_uuid = _safe_uuid(case_id)
        case = db.query(RefundCase).filter(RefundCase.id == case_uuid).with_for_update().first()
        if case is None or (not actor.is_super_admin and case.tenant_id != tenant_id_context.get()):
            raise RefundNotFound("Resource not found")
        idem_hash = hashlib.sha256(idempotency_key.strip().encode("utf-8")).hexdigest() if idempotency_key else ""
        fingerprint = _fingerprint({"case_id": str(case.id), "decision": decision, "expected_version": expected_version, "reason": reason})
        replay = self._find_idempotent_audit(
            db, tenant_id=case.tenant_id, action="refund.case.decision_recorded",
            resource_type="refund_case", idempotency_hash=idem_hash,
        ) if idem_hash else None
        if replay:
            if _audit_metadata(replay).get("request_fingerprint") != fingerprint:
                raise RefundIdempotencyConflict("Idempotency-Key was reused with a different decision")
            replay_case = self._case_from_audit(replay, db)
            if replay_case:
                return replay_case
        if expected_version != case.version:
            raise RefundVersionConflict("Refund case version is stale")
        approval = db.query(RefundApproval).filter(RefundApproval.refund_case_id == case.id).with_for_update().order_by(RefundApproval.created_at.desc()).first()
        if approval is None or approval.status != "pending":
            raise RefundApprovalConflict("Refund approval is no longer pending")
        if _utc(approval.expires_at) <= _now():
            approval.status = "expired"
            case.status = "manual_review"
            case.version += 1
            db.commit()
            raise RefundApprovalConflict("Refund approval has expired")
        if approval.initiator_admin_id == actor.id:
            raise RefundApprovalConflict("A different authorized actor must approve the refund")
        if decision not in {"approve", "reject"}:
            raise RefundInvalidTarget("Decision must be approve or reject")
        if decision == "reject":
            before = {"status": case.status, "approval": approval.status}
            approval.status = "rejected"
            approval.approver_admin_id = actor.id
            approval.decided_at = _now()
            approval.version += 1
            case.status = "rejected"
            case.version += 1
            self._audit(db, tenant_id=case.tenant_id, actor_id=actor.id, actor_type="admin", action="refund.case.decision_recorded", resource_type="refund_case", resource_id=case.id, before=before, after={"status": case.status, "decision": decision}, result="rejected", metadata={"idempotency_hash": idem_hash, "request_fingerprint": fingerprint, "reason": reason[:500]})
            db.commit()
            db.refresh(case)
            return case

        allocation, invoice, app_user_id, paid, confirmed, remaining = self._server_target(db, case.payment_allocation_id, _money(case.requested_amount), case.tenant_id)
        if _money(case.requested_amount) > remaining:
            raise RefundApprovalConflict("Confirmed refunds leave insufficient remaining amount")
        before = {"status": case.status, "approval": approval.status, "approved_amount": format(_money(case.approved_amount), ".2f")}
        approval.status = "approved"
        approval.approver_admin_id = actor.id
        approval.decided_at = _now()
        approval.version += 1
        case.approved_amount = _money(case.requested_amount)
        case.status = "provider_processing"
        case.version += 1
        provider_name = allocation.provider or "wallet"
        provider_account_ref = "wallet"
        if allocation.payment_order_id:
            order = db.query(PaymentOrder).filter(PaymentOrder.id == allocation.payment_order_id).first()
            provider_name = (order.payment_provider if order else provider_name) or provider_name
            provider_account_ref = ((order.order_metadata or {}).get("merchant", {}).get("merchant_account_ref") if order else None) or provider_account_ref
        attempt = RefundAttempt(
            tenant_id=case.tenant_id, refund_case_id=case.id, attempt_number=db.query(RefundAttempt).filter(RefundAttempt.refund_case_id == case.id).count() + 1,
            provider=provider_name, provider_account_ref=provider_account_ref,
            provider_operation_key=f"refund-case:{case.id}:v{case.version}", amount=_money(case.requested_amount), currency=case.currency,
            status="processing", audit_reference=f"pay-mp-002:refund-attempt:{uuid4()}",
        )
        db.add(attempt)
        self._audit(db, tenant_id=case.tenant_id, actor_id=actor.id, actor_type="admin", action="refund.case.decision_recorded", resource_type="refund_case", resource_id=case.id, before=before, after={"status": case.status, "decision": decision, "approved_amount": format(_money(case.approved_amount), ".2f")}, result="approved", metadata={"idempotency_hash": idem_hash, "request_fingerprint": fingerprint, "reason": reason[:500], "provider_operation_key": attempt.provider_operation_key})
        db.commit()
        db.refresh(attempt)

        if allocation.method == "wallet" and allocation.wallet_transaction_id:
            user = db.query(AppUser).filter(AppUser.id == app_user_id).with_for_update().first()
            if user is None:
                return self._finish_attempt(db, case.id, attempt.id, status="manual_review", reason_code="wallet_user_missing")
            user.balance = _money(user.balance) + _money(attempt.amount)
            db.add(AppWalletTransaction(app_user_id=user.id, payment_order_id=allocation.payment_order_id, invoice_id=None, operator_tenant_id=case.tenant_id, type="refund", amount=attempt.amount, description="Confirmed charging refund", idempotency_key=attempt.provider_operation_key))
            return self._finish_attempt(db, case.id, attempt.id, status="refunded", reason_code="wallet_ledger_confirmed")

        try:
            order, provider, (payment_ref, context) = self._provider_payment(db, allocation)
            before_facts = self._provider_facts(provider, payment_ref, context)
            before_amount = _money(before_facts.refunded_amount)
            created = self._provider_create(provider, payment_ref=payment_ref, amount=_money(attempt.amount), currency=case.currency, context=context, operation_key=attempt.provider_operation_key, case_id=case.id)
            if created.status in {"unknown", "processing"}:
                return self._finish_attempt(db, case.id, attempt.id, status="unknown", reason_code="provider_unknown", provider_ref=created.refund_ref)
            if created.status == "mismatch":
                return self._finish_attempt(db, case.id, attempt.id, status="manual_review", reason_code="provider_amount_mismatch", provider_ref=created.refund_ref)
            after_facts = self._provider_facts(provider, payment_ref, context)
            after_amount = _money(after_facts.refunded_amount)
            if after_amount != before_amount + _money(attempt.amount) or after_amount > paid:
                return self._finish_attempt(db, case.id, attempt.id, status="manual_review", reason_code="provider_amount_mismatch", provider_ref=created.refund_ref)
            status = "refunded" if after_amount >= paid else "partially_refunded"
            provider_ref = created.refund_ref or (after_facts.refund_refs[-1] if after_facts.refund_refs else None)
            return self._finish_attempt(db, case.id, attempt.id, status=status, reason_code="provider_confirmed", provider_ref=provider_ref)
        except (ProviderCapabilityError, PaymentReconciliationError, RefundCaseError) as exc:
            return self._finish_attempt(db, case.id, attempt.id, status="unknown" if getattr(exc, "retryable", False) else "manual_review", reason_code="provider_timeout" if getattr(exc, "retryable", False) else "provider_unavailable")
        except Exception:
            return self._finish_attempt(db, case.id, attempt.id, status="unknown", reason_code="provider_timeout")

    def list_refund_cases(self, db: Session, *, admin: AdminUser, status: str | None, tenant_id: UUID | None, cursor: str | None, limit: int, current_actor_id: UUID | None = None):
        offset = _decode_cursor(cursor)
        scope = self._scope_tenant(admin, tenant_id)
        query = db.query(RefundCase)
        if scope is not None:
            query = query.filter(RefundCase.tenant_id == scope)
        if status:
            query = query.filter(RefundCase.status == status)
        rows = query.order_by(RefundCase.updated_at.desc(), RefundCase.id.desc()).offset(offset).limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        return {"items": [self.project_refund(db, row, current_actor_id=current_actor_id) for row in rows], "page": {"next_cursor": _opaque_cursor(offset + limit) if has_more else None, "has_more": has_more}}

    def get_refund_case(self, db: Session, *, admin: AdminUser, case_id: UUID | str, current_actor_id: UUID | None = None) -> RefundCase:
        case = db.query(RefundCase).filter(RefundCase.id == _safe_uuid(case_id)).first()
        if case is None or (not admin.is_super_admin and case.tenant_id != tenant_id_context.get()):
            raise RefundNotFound("Resource not found")
        return case

    def list_chargeback_cases(self, db: Session, *, admin: AdminUser, status: str | None, deadline_from: str | None = None, deadline_to: str | None = None, cursor: str | None, limit: int):
        offset = _decode_cursor(cursor)
        scope = self._scope_tenant(admin)
        query = db.query(ChargebackCase)
        if scope is not None:
            query = query.filter(ChargebackCase.tenant_id == scope)
        if status:
            query = query.filter(ChargebackCase.status == status)
        projected = [(row, self.project_chargeback(db, row)) for row in query.all()]
        if deadline_from is not None:
            projected = [(row, item) for row, item in projected if item["deadline_at"] is not None and item["deadline_at"] >= deadline_from]
        if deadline_to is not None:
            projected = [(row, item) for row, item in projected if item["deadline_at"] is not None and item["deadline_at"] <= deadline_to]
        projected.sort(key=lambda pair: (pair[1]["deadline_at"] is None, pair[1]["deadline_at"] or "", str(pair[0].id)))
        page_rows = projected[offset:offset + limit + 1]
        has_more = len(page_rows) > limit
        page_rows = page_rows[:limit]
        return {"items": [item for _, item in page_rows], "page": {"next_cursor": _opaque_cursor(offset + limit) if has_more else None, "has_more": has_more}}

    def get_chargeback_case(self, db: Session, *, admin: AdminUser, case_id: UUID | str) -> ChargebackCase:
        case = db.query(ChargebackCase).filter(ChargebackCase.id == _safe_uuid(case_id)).first()
        if case is None or (not admin.is_super_admin and case.tenant_id != tenant_id_context.get()):
            raise RefundNotFound("Resource not found")
        return case

    def ingest_chargeback_fact(
        self, db: Session, *, provider: str, payment_ref: str, disputed_amount: Decimal,
        currency: str, status: str, dispute_ref: str, reason_code: str | None = None,
        deadline_at: str | None = None, funds_state: str | None = None,
        evidence_reference: str | None = None, source_reference: str | None = None,
    ) -> ChargebackCase:
        order = db.query(PaymentOrder).filter(PaymentOrder.payment_provider == provider, PaymentOrder.mercadopago_payment_id == payment_ref).first()
        if order is None:
            raise RefundNotFound("Payment reference not found")
        allocation = db.query(PaymentAllocation).filter(PaymentAllocation.payment_order_id == order.id, PaymentAllocation.status == "committed").first()
        if allocation is None:
            raise RefundInvalidTarget("Chargeback target is not a confirmed allocation")
        invoice = db.query(Invoice).filter(Invoice.id == allocation.invoice_id).first()
        if invoice is None:
            raise RefundInvalidTarget("Chargeback invoice is unavailable")
        from app.database.models import RecoveryAttempt
        recovery = db.query(RecoveryAttempt).filter(RecoveryAttempt.id == allocation.recovery_attempt_id).first()
        if recovery is None:
            raise RefundInvalidTarget("Chargeback owner is unavailable")
        amount = _money(disputed_amount)
        canonical_status = {"disputed": "hold", "reversed": "reversed"}.get(status, status)
        canonical_status = canonical_status if canonical_status in CHARGEBACK_STATUSES else "unknown"
        fingerprint = _fingerprint({"provider": provider, "payment_ref": payment_ref, "dispute_ref": dispute_ref, "amount": format(amount, ".2f"), "currency": currency, "status": canonical_status, "deadline_at": deadline_at, "funds_state": funds_state, "evidence_reference": evidence_reference})
        case = db.query(ChargebackCase).filter(ChargebackCase.provider == provider, ChargebackCase.provider_dispute_ref == dispute_ref).with_for_update().first()
        if case is not None:
            duplicate = (
                db.query(AuditLog)
                .filter(
                    AuditLog.resource_type == "chargeback_case",
                    AuditLog.resource_id == str(case.id),
                    AuditLog.action.in_(["chargeback.fact.received", "chargeback.case.state_changed"]),
                )
                .order_by(AuditLog.created_at.desc())
                .first()
            )
            if duplicate and _audit_metadata(duplicate).get("source_fingerprint") == fingerprint:
                return case
        if case is None:
            case = ChargebackCase(tenant_id=allocation.tenant_id, app_user_id=recovery.app_user_id, invoice_id=invoice.id, payment_allocation_id=allocation.id, provider=provider, provider_account_ref=(order.order_metadata or {}).get("merchant", {}).get("merchant_account_ref", "unknown"), provider_dispute_ref=dispute_ref, disputed_amount=amount, currency=currency, status=canonical_status, reason_code=reason_code, received_at=_now(), audit_reference=f"pay-mp-002:chargeback:{uuid4()}")
            db.add(case)
            db.flush()
            before = None
        else:
            before = {"status": case.status, "amount": format(_money(case.disputed_amount), ".2f")}
            if case.tenant_id != allocation.tenant_id:
                raise RefundPermissionDenied("Chargeback scope mismatch")
            case.status = canonical_status
            case.disputed_amount = amount
            case.reason_code = reason_code
            case.version += 1
            case.resolved_at = _now() if canonical_status in FINAL_CHARGEBACK_STATUSES else None
        self._audit(db, tenant_id=case.tenant_id, actor_id=SYSTEM_ACTOR_ID, actor_type="system", action="chargeback.fact.received" if before is None else "chargeback.case.state_changed", resource_type="chargeback_case", resource_id=case.id, before=before, after={"status": case.status, "amount": format(amount, ".2f"), "reason_code": reason_code}, result="recorded", metadata={"source_reference": source_reference, "source_fingerprint": fingerprint, "canonical_fact": {"payment_reference": payment_ref, "invoice_reference": str(invoice.id), "deadline_at": deadline_at, "funds_state": funds_state, "evidence_reference": evidence_reference, "source_reference": source_reference}})
        enqueue_financial_eligibility_recheck(db, app_user_id=case.app_user_id, tenant_id=case.tenant_id, source_type="chargeback_case", source_id=case.id, source_version=case.version, reason_code="chargeback_fact_changed")
        db.commit()
        db.refresh(case)
        return case
