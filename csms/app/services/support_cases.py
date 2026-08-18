"""PAY-MP-002 BE-209 structured support authority.

Support is a contextual operations domain.  It may reference financial and
charging facts, but it never mutates those authorities.  Notification work is
handed to the existing tenant-scoped Outbox and contains only safe references.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.database.base import tenant_id_context
from app.database.models import (
    AdminUser,
    AppUser,
    AuditLog,
    ChargebackCase,
    ChargingSession,
    Invoice,
    OutboxEvent,
    Payment,
    PaymentAllocation,
    PaymentOrder,
    RecoveryAttempt,
    RefundCase,
    SupportCase,
    SupportCaseEvent,
)
from app.services.outbox_service import OutboxService


MAX_PAGE_SIZE = 100
MAX_NOTE_LENGTH = 4000
APP_CATEGORY_MAP = {
    "payment_recovery": "unpaid",
    "refund_request": "refund_delayed",
    "chargeback_question": "chargeback",
    "charging_issue": "cannot_stop",
    "other": "other",
}
CASE_CATEGORIES = frozenset({
    "unpaid", "payment_failed", "duplicate_charge", "refund_delayed",
    "chargeback", "cannot_stop", "amount_mismatch", "other",
})
CASE_STATUSES = frozenset({
    "open", "acknowledged", "in_progress", "waiting_user", "resolved",
    "closed", "unknown",
})
EVENT_TYPES = frozenset({
    "acknowledge", "assign", "request_user_input", "resolve", "close",
    "add_note",
})
CONTEXT_TYPES = frozenset({
    "invoice", "session", "payment", "payment_order", "recovery_attempt",
    "refund", "refund_case", "chargeback", "chargeback_case",
})
SENSITIVE_NOTE_PATTERNS = (
    re.compile(r"(?i)\b(?:pan|cvv|cvc|card\s*token|access\s*token|refresh\s*token|document\s*(?:no|number)?|id\s*number)\b\s*[:=]?\s*[^\s,;]+"),
    re.compile(r"\b\d{13,19}\b"),
)


class SupportError(RuntimeError):
    code = "REQUEST_INVALID"
    status_code = 422
    retryable = False


class SupportNotFound(SupportError):
    code = "RESOURCE_NOT_FOUND"
    status_code = 404


class SupportContextInvalid(SupportError):
    code = "SUPPORT_CONTEXT_INVALID"
    status_code = 404


class SupportPermissionDenied(SupportError):
    code = "PERMISSION_DENIED"
    status_code = 403


class SupportVersionConflict(SupportError):
    code = "RESOURCE_VERSION_CONFLICT"
    status_code = 409


class SupportIdempotencyConflict(SupportError):
    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _utc(value)
    return normalized.isoformat().replace("+00:00", "Z") if normalized else None


def _safe_note(value: str | None) -> str | None:
    if value is None:
        return None
    note = str(value).strip()
    if not note or len(note) > MAX_NOTE_LENGTH:
        raise SupportError("note is invalid")
    # User text is retained only as a redacted collaboration note.  It is
    # never copied to notification payloads or audit metadata.
    for pattern in SENSITIVE_NOTE_PATTERNS:
        note = pattern.sub("[redacted]", note)
    return note


def _safe_ref(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or len(text) > 255:
        return None
    return text


def _add_business_days(start: datetime, days: int) -> datetime:
    result = _utc(start) or _now()
    remaining = days
    while remaining:
        result += timedelta(days=1)
        if result.weekday() < 5:
            remaining -= 1
    return result


def _cursor_encode(target: datetime | None, case_id: UUID) -> str:
    raw = json.dumps({"target": _iso(target), "id": str(case_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _cursor_decode(cursor: str | None) -> tuple[datetime | None, UUID] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        target_value = value.get("target")
        target = datetime.fromisoformat(str(target_value).replace("Z", "+00:00")) if target_value else None
        return _utc(target), UUID(str(value["id"]))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError, binascii.Error) as exc:
        raise SupportError("Cursor is invalid") from exc


def _fingerprint(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _actor_ref(db: Session, actor_type: str, actor_ref: str) -> dict[str, str]:
    display_name = "EsLatin system"
    role_label = "system"
    if actor_type == "admin":
        try:
            admin = db.query(AdminUser).filter(AdminUser.id == UUID(actor_ref)).first()
        except (TypeError, ValueError):
            admin = None
        if admin:
            display_name = (admin.full_name or admin.username or "Support operator")[:100]
            role_label = "support"
    elif actor_type == "app_user":
        display_name = "Customer"
        role_label = "customer"
    return {"id": actor_ref, "display_name": display_name, "role_label": role_label}


def _audit(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    actor_type: str,
    action: str,
    resource_type: str,
    resource_id: UUID | str,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
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
        audit_metadata={"source": "pay-mp-002-be-209", **dict(metadata or {})},
    )
    db.add(audit)
    db.flush()
    return audit


def _scope_tenant(admin: AdminUser, requested: UUID | None = None) -> UUID | None:
    if admin.is_super_admin:
        return requested
    try:
        current = tenant_id_context.get()
    except LookupError:
        current = None
    if current is None:
        raise SupportPermissionDenied("Tenant context required")
    if requested is not None and requested != current:
        raise SupportPermissionDenied("Tenant scope denied")
    return current


def _context_for_app_user(
    db: Session,
    *,
    app_user_id: UUID,
    resource_type: str,
    resource_id: UUID,
) -> dict[str, Any]:
    kind = resource_type.lower().strip()
    if kind not in CONTEXT_TYPES:
        raise SupportContextInvalid("Support context is invalid")

    context: dict[str, Any] = {
        "tenant_id": None,
        "invoice_id": None,
        "session_id": None,
        "payment_order_id": None,
        "refund_case_id": None,
        "chargeback_case_id": None,
        "references": [],
    }

    if kind == "invoice":
        invoice = (
            db.query(Invoice)
            .join(ChargingSession, ChargingSession.id == Invoice.session_id)
            .filter(Invoice.id == resource_id, ChargingSession.app_user_id == app_user_id)
            .first()
        )
        if invoice is None:
            raise SupportContextInvalid("Support context is not visible")
        context.update(tenant_id=invoice.tenant_id, invoice_id=invoice.id, session_id=invoice.session_id)
        context["references"].append(("invoice", invoice.id, invoice.invoice_number))
        context["references"].append(("session", invoice.session_id, None))
        return context

    if kind in {"session"}:
        session = db.query(ChargingSession).filter(
            ChargingSession.id == resource_id,
            ChargingSession.app_user_id == app_user_id,
        ).first()
        if session is None:
            raise SupportContextInvalid("Support context is not visible")
        invoice = db.query(Invoice).filter(
            Invoice.session_id == session.id,
            Invoice.tenant_id == session.tenant_id,
        ).first()
        context.update(tenant_id=session.tenant_id, session_id=session.id)
        if invoice:
            context["invoice_id"] = invoice.id
        context["references"].append(("session", session.id, None))
        if invoice:
            context["references"].append(("invoice", invoice.id, invoice.invoice_number))
        return context

    if kind in {"refund", "refund_case"}:
        case = db.query(RefundCase).filter(
            RefundCase.id == resource_id,
            RefundCase.app_user_id == app_user_id,
        ).first()
        if case is None:
            raise SupportContextInvalid("Support context is not visible")
        context.update(tenant_id=case.tenant_id, invoice_id=case.invoice_id, refund_case_id=case.id)
        context["references"].append(("refund_case", case.id, case.case_reference))
        context["references"].append(("invoice", case.invoice_id, None))
        return context

    if kind in {"chargeback", "chargeback_case"}:
        case = db.query(ChargebackCase).filter(
            ChargebackCase.id == resource_id,
            ChargebackCase.app_user_id == app_user_id,
        ).first()
        if case is None:
            raise SupportContextInvalid("Support context is not visible")
        context.update(tenant_id=case.tenant_id, invoice_id=case.invoice_id, chargeback_case_id=case.id)
        context["references"].append(("chargeback_case", case.id, case.case_reference))
        context["references"].append(("invoice", case.invoice_id, None))
        return context

    if kind == "recovery_attempt":
        attempt = db.query(RecoveryAttempt).filter(
            RecoveryAttempt.id == resource_id,
            RecoveryAttempt.app_user_id == app_user_id,
        ).first()
        if attempt is None:
            raise SupportContextInvalid("Support context is not visible")
        context.update(tenant_id=attempt.tenant_id, invoice_id=attempt.invoice_id, session_id=attempt.session_id)
        context["references"].extend([
            ("invoice", attempt.invoice_id, None),
            ("session", attempt.session_id, None),
            ("recovery_attempt", attempt.id, None),
        ])
        return context

    if kind in {"payment", "payment_order"}:
        if kind == "payment":
            payment = db.query(Payment).filter(Payment.id == resource_id).first()
            if payment is None:
                raise SupportContextInvalid("Support context is not visible")
            invoice = db.query(Invoice).filter(
                Invoice.id == payment.invoice_id,
                Invoice.tenant_id == payment.tenant_id,
            ).first()
            session = db.query(ChargingSession).filter(
                ChargingSession.id == invoice.session_id if invoice else False,
                ChargingSession.app_user_id == app_user_id,
            ).first() if invoice else None
            if invoice is None or session is None:
                raise SupportContextInvalid("Support context is not visible")
            context.update(tenant_id=payment.tenant_id, invoice_id=invoice.id, session_id=session.id)
            context["references"].extend([
                ("payment", payment.id, payment.payment_number),
                ("invoice", invoice.id, invoice.invoice_number),
            ])
            return context

        order = db.query(PaymentOrder).filter(
            PaymentOrder.id == resource_id,
            PaymentOrder.app_user_id == app_user_id,
        ).first()
        if order is None:
            raise SupportContextInvalid("Support context is not visible")
        allocation = db.query(PaymentAllocation).filter(
            PaymentAllocation.payment_order_id == order.id,
        ).first()
        invoice = None
        if allocation:
            invoice = db.query(Invoice).filter(
                Invoice.id == allocation.invoice_id,
                Invoice.tenant_id == allocation.tenant_id,
            ).first()
            tenant_id = allocation.tenant_id
        else:
            metadata = order.order_metadata if isinstance(order.order_metadata, Mapping) else {}
            session_value = metadata.get("session_id") or metadata.get("charging_session_id")
            try:
                session_id = UUID(str(session_value)) if session_value else None
            except (TypeError, ValueError):
                session_id = None
            session = db.query(ChargingSession).filter(
                ChargingSession.id == session_id,
                ChargingSession.app_user_id == app_user_id,
            ).first() if session_id else None
            invoice = db.query(Invoice).filter(
                Invoice.session_id == session.id,
                Invoice.tenant_id == session.tenant_id,
            ).first() if session else None
            tenant_id = session.tenant_id if session else None
        if invoice is None or tenant_id is None:
            raise SupportContextInvalid("Support context has no trusted tenant association")
        context.update(tenant_id=tenant_id, invoice_id=invoice.id, session_id=invoice.session_id, payment_order_id=order.id)
        context["references"].extend([
            ("payment_order", order.id, order.reference or order.external_reference),
            ("invoice", invoice.id, invoice.invoice_number),
        ])
        return context

    raise SupportContextInvalid("Support context is invalid")


def _linked_resources(db: Session, case: SupportCase) -> list[dict[str, str | None]]:
    values: list[tuple[str, UUID | None, str | None]] = [
        ("invoice", case.invoice_id, None),
        ("session", case.session_id, None),
        ("payment_order", case.payment_order_id, None),
        ("refund_case", case.refund_case_id, None),
        ("chargeback_case", case.chargeback_case_id, None),
        ("rail_control", case.rail_control_id, None),
    ]
    references: dict[tuple[str, UUID], str | None] = {}
    if case.invoice_id:
        invoice = db.query(Invoice).filter(Invoice.id == case.invoice_id).first()
        references[("invoice", case.invoice_id)] = invoice.invoice_number if invoice else None
    if case.payment_order_id:
        order = db.query(PaymentOrder).filter(PaymentOrder.id == case.payment_order_id).first()
        references[("payment_order", case.payment_order_id)] = (order.reference or order.external_reference) if order else None
    if case.refund_case_id:
        refund = db.query(RefundCase).filter(RefundCase.id == case.refund_case_id).first()
        references[("refund_case", case.refund_case_id)] = refund.case_reference if refund else None
    if case.chargeback_case_id:
        chargeback = db.query(ChargebackCase).filter(ChargebackCase.id == case.chargeback_case_id).first()
        references[("chargeback_case", case.chargeback_case_id)] = chargeback.case_reference if chargeback else None
    return [
        {"type": kind, "id": str(resource_id), "reference": references.get((kind, resource_id))}
        for kind, resource_id, _ in values if resource_id is not None
    ]


def _event_projection(db: Session, event: SupportCaseEvent, case_version: int) -> dict[str, Any]:
    return {
        "event_id": str(event.id),
        "case_id": str(event.support_case_id),
        "event_type": event.event_type,
        "note_visibility": event.visibility,
        "status": event.status,
        "actor": _actor_ref(db, event.actor_type, event.actor_ref),
        "occurred_at": _iso(event.occurred_at),
        "case_version": case_version,
    }


def _timeline(db: Session, case: SupportCase, *, user_visible_only: bool) -> list[dict[str, Any]]:
    query = db.query(SupportCaseEvent).filter(
        SupportCaseEvent.support_case_id == case.id,
        SupportCaseEvent.tenant_id == case.tenant_id,
    )
    if user_visible_only:
        query = query.filter(SupportCaseEvent.visibility == "user")
    events = query.order_by(SupportCaseEvent.occurred_at.asc(), SupportCaseEvent.id.asc()).all()
    return [_event_projection(db, event, case.version) for event in events]


def _assignee(db: Session, case: SupportCase) -> dict[str, str] | None:
    if case.assigned_admin_id is None:
        return None
    return _actor_ref(db, "admin", str(case.assigned_admin_id))


def project_support_case(
    db: Session,
    case: SupportCase,
    *,
    user_visible_only: bool = False,
    app_projection: bool = False,
) -> dict[str, Any]:
    result = {
        "case_id": str(case.id),
        "reference": case.case_reference,
        "status": case.status,
        "category": case.category,
        "linked_resources": _linked_resources(db, case),
        "sla_target_at": _iso(case.first_response_target_at),
        "assignee": _assignee(db, case),
        "timeline": _timeline(db, case, user_visible_only=user_visible_only),
        "allowed_actions": ["view"] if app_projection else (["view"] if case.status == "closed" else ["view", "add_event"]),
        "version": case.version,
        "created_at": _iso(case.created_at),
        "updated_at": _iso(case.updated_at),
    }
    if app_projection:
        result["linked_refund_case"] = next(
            (item for item in result["linked_resources"] if item["type"] == "refund_case"),
            None,
        )
    return result


class SupportCaseService:
    """Create/read support facts and bounded collaboration events."""

    def create_case(
        self,
        db: Session,
        *,
        app_user: AppUser,
        category: str,
        resource_type: str,
        resource_id: UUID,
        description: str | None,
    ) -> SupportCase:
        if app_user.status != "active":
            raise SupportPermissionDenied("App user is inactive")
        normalized_category = APP_CATEGORY_MAP.get(category, category)
        if normalized_category not in CASE_CATEGORIES:
            raise SupportError("Support category is invalid")
        context = _context_for_app_user(
            db, app_user_id=app_user.id, resource_type=resource_type, resource_id=resource_id
        )
        tenant_id = context["tenant_id"]
        if tenant_id is None:
            raise SupportContextInvalid("Support context has no tenant")
        now = _now()
        case = SupportCase(
            tenant_id=tenant_id,
            app_user_id=app_user.id,
            invoice_id=context["invoice_id"],
            session_id=context["session_id"],
            payment_order_id=context["payment_order_id"],
            refund_case_id=context["refund_case_id"],
            chargeback_case_id=context["chargeback_case_id"],
            category=normalized_category,
            priority="urgent" if category == "charging_issue" else "normal",
            first_response_target_at=_add_business_days(now, 1),
            decision_target_at=_add_business_days(now, 3),
            audit_reference=f"support-audit:{uuid4()}",
        )
        db.add(case)
        db.flush()
        note = _safe_note(description)
        event = SupportCaseEvent(
            tenant_id=tenant_id,
            support_case_id=case.id,
            event_type="case_opened",
            status=case.status,
            actor_type="app_user",
            actor_ref=str(app_user.id),
            visibility="user",
            note=note,
            reason_code=normalized_category,
            audit_reference=f"support-event-audit:{uuid4()}",
        )
        db.add(event)
        db.flush()
        _audit(
            db,
            tenant_id=tenant_id,
            actor_id=app_user.id,
            actor_type="app_user",
            action="create",
            resource_type="support_case",
            resource_id=case.id,
            after={"status": case.status, "category": case.category, "reference": case.case_reference},
        )
        safe_payload = {
            "case_id": str(case.id),
            "case_reference": case.case_reference,
            "status": case.status,
            "event_type": "case_opened",
            "recipient_ref": f"app_user:{app_user.id}",
            "safe_url": f"/api/v1/app/support-cases/{case.id}",
        }
        OutboxService.enqueue(
            db,
            tenant_id=tenant_id,
            aggregate_type="support_case",
            aggregate_id=str(case.id),
            event_type="support.case.created",
            idempotency_key=f"support.case.created:{case.id}",
            payload={"case_id": str(case.id), "case_reference": case.case_reference, "status": case.status},
        )
        OutboxService.enqueue(
            db,
            tenant_id=tenant_id,
            aggregate_type="support_case",
            aggregate_id=str(case.id),
            event_type="support.notification.requested",
            idempotency_key=f"support.notification.created:{case.id}",
            payload=safe_payload,
        )
        db.commit()
        db.refresh(case)
        return case

    def list_app_cases(
        self, db: Session, *, app_user: AppUser, status: str | None, cursor: str | None, limit: int
    ) -> dict[str, Any]:
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise SupportError("limit must be between 1 and 100")
        query = db.query(SupportCase).filter(SupportCase.app_user_id == app_user.id)
        if status:
            if status not in CASE_STATUSES:
                raise SupportError("status is invalid")
            query = query.filter(SupportCase.status == status)
        decoded = _cursor_decode(cursor)
        if decoded:
            target, case_id = decoded
            query = query.filter(
                or_(
                    SupportCase.first_response_target_at > target,
                    and_(SupportCase.first_response_target_at == target, SupportCase.id > case_id),
                ) if target is not None else and_(
                    SupportCase.first_response_target_at.is_(None), SupportCase.id > case_id
                )
            )
        rows = query.order_by(
            SupportCase.first_response_target_at.asc().nulls_last(), SupportCase.id.asc()
        ).limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = _cursor_encode(rows[-1].first_response_target_at, rows[-1].id) if has_more and rows else None
        return {
            "items": [project_support_case(db, row, user_visible_only=True, app_projection=True) for row in rows],
            "page": {"next_cursor": next_cursor, "has_more": has_more},
        }

    def get_app_case(self, db: Session, *, app_user: AppUser, case_id: UUID) -> SupportCase:
        case = db.query(SupportCase).filter(
            SupportCase.id == case_id,
            SupportCase.app_user_id == app_user.id,
        ).first()
        if case is None:
            raise SupportNotFound("Support case not found")
        return case

    def _admin_case(self, db: Session, *, admin: AdminUser, case_id: UUID, tenant_id: UUID | None) -> SupportCase:
        # Filtering by the trusted scope before returning is the existence
        # hiding boundary for cross-tenant resources.
        query = db.query(SupportCase).filter(SupportCase.id == case_id)
        if tenant_id is not None:
            query = query.filter(SupportCase.tenant_id == tenant_id)
        case = query.first()
        if case is None:
            raise SupportNotFound("Support case not found")
        return case

    def list_admin_cases(
        self,
        db: Session,
        *,
        admin: AdminUser,
        status: str | None,
        category: str | None,
        cursor: str | None,
        limit: int,
        tenant_id: UUID | None,
    ) -> dict[str, Any]:
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise SupportError("limit must be between 1 and 100")
        resolved_tenant = _scope_tenant(admin, tenant_id)
        query = db.query(SupportCase)
        if resolved_tenant is not None:
            query = query.filter(SupportCase.tenant_id == resolved_tenant)
        if status:
            if status not in CASE_STATUSES:
                raise SupportError("status is invalid")
            query = query.filter(SupportCase.status == status)
        if category:
            if category not in CASE_CATEGORIES:
                raise SupportError("category is invalid")
            query = query.filter(SupportCase.category == category)
        decoded = _cursor_decode(cursor)
        if decoded:
            target, case_id = decoded
            query = query.filter(
                or_(
                    SupportCase.first_response_target_at > target,
                    and_(SupportCase.first_response_target_at == target, SupportCase.id > case_id),
                ) if target is not None else and_(
                    SupportCase.first_response_target_at.is_(None), SupportCase.id > case_id
                )
            )
        rows = query.order_by(
            SupportCase.first_response_target_at.asc().nulls_last(), SupportCase.id.asc()
        ).limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = _cursor_encode(rows[-1].first_response_target_at, rows[-1].id) if has_more and rows else None
        return {
            "items": [project_support_case(db, row) for row in rows],
            "page": {"next_cursor": next_cursor, "has_more": has_more},
        }

    def get_admin_case(self, db: Session, *, admin: AdminUser, case_id: UUID, tenant_id: UUID | None) -> SupportCase:
        resolved_tenant = _scope_tenant(admin, tenant_id)
        return self._admin_case(db, admin=admin, case_id=case_id, tenant_id=resolved_tenant)

    def add_admin_event(
        self,
        db: Session,
        *,
        admin: AdminUser,
        case_id: UUID,
        event_type: str,
        note: str | None,
        visibility: str,
        expected_version: int,
        idempotency_key: str,
        tenant_id: UUID | None,
    ) -> SupportCaseEvent:
        if event_type not in EVENT_TYPES:
            raise SupportError("event_type is invalid")
        if visibility not in {"internal", "user"}:
            raise SupportError("note_visibility is invalid")
        if not idempotency_key or len(idempotency_key) > 255:
            raise SupportError("Idempotency-Key is required")
        resolved_tenant = _scope_tenant(admin, tenant_id)
        case = self._admin_case(db, admin=admin, case_id=case_id, tenant_id=resolved_tenant)
        outbox_key = f"support.case.event:{case.id}:{idempotency_key}"
        request_fingerprint = _fingerprint({
            "case_id": str(case.id),
            "event_type": event_type,
            "note": _safe_note(note),
            "note_visibility": visibility,
            "expected_version": expected_version,
        })
        existing_outbox = db.query(OutboxEvent).filter(
            OutboxEvent.tenant_id == case.tenant_id,
            OutboxEvent.idempotency_key == outbox_key,
        ).first()
        if existing_outbox:
            existing_payload = existing_outbox.payload if isinstance(existing_outbox.payload, Mapping) else {}
            if existing_payload.get("request_fingerprint") not in {None, request_fingerprint}:
                raise SupportIdempotencyConflict("Idempotency key fingerprint conflict")
            event_id = (existing_outbox.payload or {}).get("event_id") if isinstance(existing_outbox.payload, Mapping) else None
            if event_id:
                event = db.query(SupportCaseEvent).filter(SupportCaseEvent.id == UUID(str(event_id))).first()
                if event:
                    return event
            raise SupportIdempotencyConflict("Idempotency key has no recoverable event")
        if expected_version != case.version:
            raise SupportVersionConflict("Support case version conflict")
        safe_note = _safe_note(note)
        transitions = {
            "acknowledge": {"open": "acknowledged"},
            "assign": {"open": "in_progress", "acknowledged": "in_progress", "waiting_user": "in_progress", "in_progress": "in_progress"},
            "request_user_input": {"open": "waiting_user", "acknowledged": "waiting_user", "in_progress": "waiting_user"},
            "resolve": {"open": "resolved", "acknowledged": "resolved", "in_progress": "resolved", "waiting_user": "resolved"},
            "close": {"resolved": "closed"},
            "add_note": {status: status for status in CASE_STATUSES if status != "closed"},
        }
        next_status = transitions[event_type].get(case.status)
        if next_status is None:
            raise SupportError("Support case lifecycle transition is invalid")
        previous = {"status": case.status, "version": case.version, "assigned_admin_id": str(case.assigned_admin_id) if case.assigned_admin_id else None}
        case.status = next_status
        case.version += 1
        if event_type == "assign":
            case.assigned_admin_id = admin.id
        if event_type in {"acknowledge", "assign"} and case.first_responded_at is None:
            case.first_responded_at = _now()
        if event_type == "resolve":
            case.resolved_at = _now()
        event = SupportCaseEvent(
            tenant_id=case.tenant_id,
            support_case_id=case.id,
            event_type=event_type,
            status=case.status,
            actor_type="admin",
            actor_ref=str(admin.id),
            visibility=visibility,
            note=safe_note,
            reason_code=event_type,
            audit_reference=f"support-event-audit:{uuid4()}",
        )
        db.add(event)
        db.flush()
        _audit(
            db,
            tenant_id=case.tenant_id,
            actor_id=admin.id,
            actor_type="admin",
            action="support_case_event",
            resource_type="support_case",
            resource_id=case.id,
            before=previous,
            after={"status": case.status, "version": case.version},
            metadata={"event_type": event_type},
        )
        payload = {
            "event_id": str(event.id),
            "case_id": str(case.id),
            "case_reference": case.case_reference,
            "status": case.status,
            "event_type": event_type,
            "recipient_ref": f"app_user:{case.app_user_id}",
            "safe_url": f"/api/v1/app/support-cases/{case.id}",
            "request_fingerprint": request_fingerprint,
        }
        OutboxService.enqueue(
            db,
            tenant_id=case.tenant_id,
            aggregate_type="support_case",
            aggregate_id=str(case.id),
            event_type="support.case.state_changed",
            idempotency_key=outbox_key,
            payload=payload,
        )
        OutboxService.enqueue(
            db,
            tenant_id=case.tenant_id,
            aggregate_type="support_case",
            aggregate_id=str(case.id),
            event_type="support.notification.requested",
            idempotency_key=f"{outbox_key}:notification",
            payload={key: payload[key] for key in payload if key not in {"event_id", "request_fingerprint"}},
        )
        db.commit()
        db.refresh(event)
        return event


def emergency_support_status(case: SupportCase, now: datetime | None = None) -> dict[str, Any]:
    """Return an explicit, non-24/7 emergency capability projection.

    Business-hours staffing is an operations/configuration fact owned outside
    BE-209.  The backend therefore exposes the safe capability state rather
    than inventing hours or pretending that every site is staffed 24/7.
    """
    del now
    return {
        "status": "urgent_support_requested" if case.priority == "urgent" else "standard_support",
        "availability": "published_business_hours_only",
        "is_24_7": False,
    }
