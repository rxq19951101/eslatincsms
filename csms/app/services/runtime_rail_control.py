"""PAY-MP-002 dual-axis runtime rail control.

This service owns operational rail facts and their two-person reopen workflow.
It is intentionally independent from ``PAYMENT_RAILS_ENABLED``: that setting
is a deployment gate, while these rows are scoped, audited runtime controls.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.permissions import check_permission
from app.database.models import (
    AdminUser,
    AuditLog,
    ChargePoint,
    OutboxEvent,
    RailHealthCheck,
    RailReopenRequest,
    RuntimeRailControl,
    Site,
    Tenant,
)


AXES = frozenset({"paid_admission", "payment_creation"})
SCOPE_TYPES = frozenset({"platform", "provider", "tenant", "site"})
HEALTH_STATUSES = frozenset({"passed", "failed", "unknown"})
PLATFORM_REF = "platform:eslatin"
_SAFE_PROVIDER = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


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


def _fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _cursor_encode(updated_at: datetime, resource_id: UUID) -> str:
    raw = json.dumps({"updated_at": _iso(updated_at), "id": str(resource_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _cursor_decode(value: str | None) -> tuple[datetime, UUID] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return datetime.fromisoformat(str(raw["updated_at"]).replace("Z", "+00:00")), UUID(str(raw["id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RailRequestInvalid("Invalid cursor") from exc


class RailError(RuntimeError):
    code = "RAIL_ERROR"
    status_code = 500
    retryable = False


class RailRequestInvalid(RailError):
    code = "REQUEST_INVALID"
    status_code = 422


class RailNotFound(RailError):
    code = "RESOURCE_NOT_FOUND"
    status_code = 404


class RailPermissionDenied(RailError):
    code = "PERMISSION_DENIED"
    status_code = 403


class RailVersionConflict(RailError):
    code = "RESOURCE_VERSION_CONFLICT"
    status_code = 409


class RailIdempotencyConflict(RailError):
    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409


class RailApprovalConflict(RailError):
    code = "APPROVAL_CONFLICT"
    status_code = 409


class RailApprovalExpired(RailError):
    code = "APPROVAL_EXPIRED"
    status_code = 409


class RailClosed(RailError):
    code = "RAIL_CLOSED"
    status_code = 503


class RailStateUnknown(RailError):
    code = "RAIL_STATE_UNKNOWN"
    status_code = 503
    retryable = True


@dataclass(frozen=True)
class RailScope:
    scope_type: str
    scope_ref: str
    tenant_id: UUID | None = None
    site_id: UUID | None = None
    provider: str | None = None


@dataclass(frozen=True)
class RailDecision:
    axis: str
    status: str
    matched_scope_refs: tuple[str, ...]
    version: int


def _actor_projection(db: Session, actor_id: UUID | None) -> dict[str, str] | None:
    if actor_id is None:
        return None
    actor = db.query(AdminUser).filter(AdminUser.id == actor_id).first()
    return {
        "id": str(actor_id),
        "display_name": ((actor.full_name or actor.username) if actor else "Platform operator")[:100],
        "role_label": "platform" if actor and actor.is_super_admin else "tenant",
    }


class RuntimeRailControlService:
    """Scoped rail facts, health evidence, and audited two-person reopen."""

    @staticmethod
    def resolve_scope(db: Session, *, scope_type: str, scope_ref: str) -> RailScope:
        scope_type = str(scope_type or "").strip().lower()
        scope_ref = str(scope_ref or "").strip()
        if scope_type not in SCOPE_TYPES or not scope_ref:
            raise RailRequestInvalid("Invalid rail scope")
        if scope_type == "platform":
            if scope_ref != PLATFORM_REF:
                raise RailRequestInvalid("Platform rail scope is invalid")
            return RailScope(scope_type, PLATFORM_REF)
        if scope_type == "provider":
            provider = scope_ref.removeprefix("provider:")
            if not _SAFE_PROVIDER.fullmatch(provider):
                raise RailRequestInvalid("Provider rail scope is invalid")
            return RailScope(scope_type, f"provider:{provider}", provider=provider)
        if scope_type == "tenant":
            raw_id = scope_ref.removeprefix("tenant:")
            try:
                tenant_id = UUID(raw_id)
            except (TypeError, ValueError) as exc:
                raise RailRequestInvalid("Tenant rail scope is invalid") from exc
            if db.query(Tenant).filter(Tenant.id == tenant_id).first() is None:
                raise RailNotFound("Rail scope is not available")
            return RailScope(scope_type, f"tenant:{tenant_id}", tenant_id=tenant_id)
        raw_id = scope_ref.removeprefix("site:")
        try:
            site_id = UUID(raw_id)
        except (TypeError, ValueError) as exc:
            raise RailRequestInvalid("Site rail scope is invalid") from exc
        site = db.query(Site).filter(Site.id == site_id).first()
        if site is None:
            raise RailNotFound("Rail scope is not available")
        return RailScope(scope_type, f"site:{site.id}", tenant_id=site.tenant_id, site_id=site.id)

    @staticmethod
    def applicable_scope_refs(
        *, tenant_id: UUID | None = None, site_id: UUID | None = None, provider: str | None = None
    ) -> tuple[str, ...]:
        refs = [PLATFORM_REF]
        if provider:
            refs.append(f"provider:{provider}")
        if tenant_id:
            refs.append(f"tenant:{tenant_id}")
        if site_id:
            refs.append(f"site:{site_id}")
        return tuple(refs)

    @classmethod
    def evaluate(
        cls,
        db: Session,
        *,
        axis: str,
        tenant_id: UUID | None = None,
        site_id: UUID | None = None,
        provider: str | None = None,
    ) -> RailDecision:
        if axis not in AXES:
            raise RailRequestInvalid("Invalid rail axis")
        refs = cls.applicable_scope_refs(tenant_id=tenant_id, site_id=site_id, provider=provider)
        rows = (
            db.query(RuntimeRailControl)
            .filter(RuntimeRailControl.axis == axis, RuntimeRailControl.scope_ref.in_(refs))
            .all()
        )
        by_ref = {row.scope_ref: row for row in rows}
        matched = tuple(ref for ref in refs if ref in by_ref)
        if any(by_ref[ref].status == "unknown" for ref in matched):
            status = "unknown"
        elif any(by_ref[ref].status == "closed" for ref in matched):
            status = "closed"
        else:
            status = "open"
        return RailDecision(axis, status, matched, max((by_ref[ref].version for ref in matched), default=0))

    @classmethod
    def require_open(cls, db: Session, **kwargs: Any) -> RailDecision:
        decision = cls.evaluate(db, **kwargs)
        if decision.status == "unknown":
            raise RailStateUnknown("Rail state is unknown")
        if decision.status == "closed":
            raise RailClosed("Rail is closed")
        return decision

    @classmethod
    def payment_creation_decision(
        cls, db: Session, *, provider: str, tenant_id: UUID | None = None, site_id: UUID | None = None
    ) -> RailDecision:
        return cls.evaluate(
            db,
            axis="payment_creation",
            tenant_id=tenant_id,
            site_id=site_id,
            provider=provider,
        )

    @classmethod
    def require_payment_creation_open(
        cls, db: Session, *, provider: str, tenant_id: UUID | None = None, site_id: UUID | None = None
    ) -> RailDecision:
        return cls.require_open(
            db,
            axis="payment_creation",
            tenant_id=tenant_id,
            site_id=site_id,
            provider=provider,
        )

    @staticmethod
    def _authorize(db: Session, *, admin: AdminUser, scope: RailScope, permission: str) -> None:
        if admin.is_super_admin:
            return
        if scope.scope_type in {"platform", "provider"} or scope.tenant_id is None:
            raise RailPermissionDenied("Platform rail control requires platform authority")
        if not check_permission(admin.id, permission, db, scope.tenant_id):
            raise RailPermissionDenied("Rail permission is not available for this scope")

    @staticmethod
    def _audit(
        db: Session,
        *,
        admin: AdminUser,
        scope: RailScope,
        action: str,
        resource_id: UUID,
        result: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        reason: str,
        incident_reference: str | None = None,
        health_check_reference: str | None = None,
    ) -> str:
        reference = f"pay-mp-002:rail:{action}:{resource_id}:{uuid4()}"
        db.add(AuditLog(
            tenant_id=scope.tenant_id,
            actor_id=admin.id,
            actor_type="admin",
            action=action,
            resource_type="runtime_rail_control",
            resource_id=str(resource_id),
            before_data=dict(before) if before else None,
            after_data=dict(after) if after else None,
            audit_metadata={
                "audit_reference": reference,
                "result": result,
                "scope": {"type": scope.scope_type, "ref": scope.scope_ref},
                "reason": reason[:1000],
                "incident_reference": incident_reference,
                "health_check_reference": health_check_reference,
            },
        ))
        return reference

    @staticmethod
    def _outbox(
        db: Session,
        *,
        control: RuntimeRailControl,
        scope: RailScope,
        event_type: str,
        idempotency_key: str,
        status: str,
        reason: str,
        audit_reference: str,
        entity_id: UUID | None = None,
    ) -> None:
        delivery_scope = "tenant" if scope.tenant_id is not None else "platform"
        delivery_ref = f"tenant:{scope.tenant_id}" if scope.tenant_id is not None else PLATFORM_REF
        db.add(OutboxEvent(
            tenant_id=scope.tenant_id,
            scope_type=delivery_scope,
            scope_ref=delivery_ref,
            aggregate_type="runtime_rail_control",
            aggregate_id=str(entity_id or control.id),
            event_type=event_type,
            idempotency_key=idempotency_key,
            status="pending",
            payload={
                "event_id": str(uuid4()),
                "schema_version": 1,
                "aggregate_type": "runtime_rail_control",
                "id": str(entity_id or control.id),
                "scope_type": delivery_scope,
                "scope_ref": delivery_ref,
                "entity_reference": str(control.id),
                "axis": control.axis,
                "rail_scope_type": control.scope_type,
                "rail_scope_ref": control.scope_ref,
                "status": status,
                "version": control.version,
                "occurred_at_utc": _iso(_now()),
                "reason_code": reason[:100],
                "audit_reference": audit_reference,
                "idempotency_key": idempotency_key,
            },
        ))

    @staticmethod
    def _projection(db: Session, control: RuntimeRailControl, *, admin: AdminUser | None = None) -> dict[str, Any]:
        allowed = ["read"]
        if control.status in {"closed", "unknown"}:
            allowed.append("request_reopen")
        else:
            allowed.append("close")
        return {
            "control_id": str(control.id),
            "axis": control.axis,
            "scope": {"type": control.scope_type, "ref": control.scope_ref},
            "status": control.status,
            "reason": control.reason or control.reason_code,
            "incident_reference": control.incident_reference,
            "effective_at": _iso(control.effective_at or control.closed_at),
            "closed_by": _actor_projection(db, control.closed_by_admin_id),
            "reopened_by": _actor_projection(db, control.reopened_by_admin_id),
            "health_check_reference": control.health_check_reference,
            "allowed_actions": allowed,
            "version": control.version,
            "created_at": _iso(control.created_at),
            "updated_at": _iso(control.updated_at),
        }

    @staticmethod
    def _reopen_projection(db: Session, request: RailReopenRequest) -> dict[str, Any]:
        return {
            "request_id": str(request.id),
            "control_id": str(request.control_id),
            "status": request.status,
            "reason": request.reason,
            "initiator": _actor_projection(db, request.initiator_admin_id),
            "approver": _actor_projection(db, request.approver_admin_id),
            "health_check_reference": request.health_check_reference,
            "control_status": request.control_status,
            "expires_at": _iso(request.expires_at),
            "decided_at": _iso(request.decided_at),
            "allowed_actions": ["approve", "reject"] if request.status == "requested" else ["read"],
            "version": request.version,
            "created_at": _iso(request.created_at),
            "updated_at": _iso(request.updated_at),
        }

    @classmethod
    def record_health_check(
        cls,
        db: Session,
        *,
        reference: str,
        axis: str,
        scope_type: str,
        scope_ref: str,
        status: str,
        safe_metadata: Mapping[str, Any] | None = None,
    ) -> RailHealthCheck:
        if not reference or status not in HEALTH_STATUSES or axis not in AXES:
            raise RailRequestInvalid("Health check is invalid")
        scope = cls.resolve_scope(db, scope_type=scope_type, scope_ref=scope_ref)
        existing = db.query(RailHealthCheck).filter(RailHealthCheck.reference == reference).first()
        if existing is None:
            existing = RailHealthCheck(
                reference=reference,
                axis=axis,
                scope_type=scope.scope_type,
                scope_ref=scope.scope_ref,
                status=status,
                safe_metadata=dict(safe_metadata or {}),
            )
            db.add(existing)
        else:
            existing.axis = axis
            existing.scope_type = scope.scope_type
            existing.scope_ref = scope.scope_ref
            existing.status = status
            existing.checked_at = _now()
            existing.safe_metadata = dict(safe_metadata or {})
        db.commit()
        db.refresh(existing)
        return existing

    @classmethod
    def _health_status(cls, db: Session, *, reference: str, control: RuntimeRailControl) -> str:
        row = db.query(RailHealthCheck).filter(RailHealthCheck.reference == reference).first()
        if row is None:
            return "unknown"
        if row.axis != control.axis or row.scope_ref != control.scope_ref:
            return "unknown"
        return row.status if row.status in HEALTH_STATUSES else "unknown"

    @classmethod
    def close(
        cls,
        db: Session,
        *,
        admin: AdminUser,
        axis: str,
        scope_type: str,
        scope_ref: str,
        reason: str,
        incident_reference: str,
        expected_version: int,
        idempotency_key: str,
    ) -> RuntimeRailControl:
        if axis not in AXES or not reason.strip() or not incident_reference.strip() or not idempotency_key.strip():
            raise RailRequestInvalid("Rail close request is invalid")
        scope = cls.resolve_scope(db, scope_type=scope_type, scope_ref=scope_ref)
        cls._authorize(db, admin=admin, scope=scope, permission="rail.close")
        request_fingerprint = _fingerprint({
            "axis": axis, "scope_ref": scope.scope_ref, "reason": reason, "incident_reference": incident_reference,
            "expected_version": expected_version,
        })
        replay = db.query(RuntimeRailControl).filter(
            RuntimeRailControl.axis == axis,
            RuntimeRailControl.scope_ref == scope.scope_ref,
            RuntimeRailControl.close_idempotency_key == idempotency_key,
        ).first()
        if replay is not None:
            if replay.close_request_fingerprint != request_fingerprint:
                raise RailIdempotencyConflict("Rail close idempotency key conflict")
            return replay
        control = db.query(RuntimeRailControl).filter(
            RuntimeRailControl.axis == axis,
            RuntimeRailControl.scope_type == scope.scope_type,
            RuntimeRailControl.scope_ref == scope.scope_ref,
        ).with_for_update().first()
        if control is None:
            if expected_version != 0:
                raise RailVersionConflict("Rail version does not match")
            control = RuntimeRailControl(
                axis=axis,
                scope_type=scope.scope_type,
                scope_ref=scope.scope_ref,
                tenant_id=scope.tenant_id,
                site_id=scope.site_id,
                provider=scope.provider,
                status="closed",
                reason=reason.strip(),
                reason_code="incident_close",
                incident_reference=incident_reference.strip(),
                closed_by_admin_id=admin.id,
                version=1,
                schema_version=1,
                audit_reference=f"pay-mp-002:rail:close:{uuid4()}",
                closed_at=_now(),
                effective_at=_now(),
                close_idempotency_key=idempotency_key,
                close_request_fingerprint=request_fingerprint,
            )
            db.add(control)
            db.flush()
            before = None
        else:
            if control.version != expected_version:
                raise RailVersionConflict("Rail version does not match")
            if control.status == "closed":
                return control
            before = {"status": control.status, "version": control.version}
            control.status = "closed"
            control.reason = reason.strip()
            control.reason_code = "incident_close"
            control.incident_reference = incident_reference.strip()
            control.closed_by_admin_id = admin.id
            control.closed_at = _now()
            control.effective_at = control.closed_at
            control.version += 1
            control.close_idempotency_key = idempotency_key
            control.close_request_fingerprint = request_fingerprint
        audit_reference = cls._audit(
            db, admin=admin, scope=scope, action="rail.control.closed", resource_id=control.id,
            result="closed", before=before, after={"status": "closed", "version": control.version},
            reason=reason, incident_reference=incident_reference,
        )
        control.audit_reference = audit_reference
        key = f"rail-close:{idempotency_key}"
        cls._outbox(
            db, control=control, scope=scope, event_type="rail.control.closed", idempotency_key=key,
            status=control.status, reason="incident_close", audit_reference=audit_reference,
        )
        event = db.query(OutboxEvent).filter(OutboxEvent.idempotency_key == key).order_by(OutboxEvent.created_at.desc()).first()
        if event is not None and isinstance(event.payload, dict):
            event.payload = {**event.payload, "request_fingerprint": _fingerprint({
                "axis": axis, "scope_ref": scope.scope_ref, "reason": reason, "incident_reference": incident_reference,
                "expected_version": expected_version,
            }), "entity_reference": str(control.id)}
        db.commit()
        db.refresh(control)
        return control

    @classmethod
    def request_reopen(
        cls,
        db: Session,
        *,
        admin: AdminUser,
        control_id: UUID,
        reason: str,
        health_check_reference: str,
        expected_version: int,
        idempotency_key: str,
    ) -> RailReopenRequest:
        if not reason.strip() or not health_check_reference.strip() or not idempotency_key.strip():
            raise RailRequestInvalid("Rail reopen request is invalid")
        control = db.query(RuntimeRailControl).filter(RuntimeRailControl.id == control_id).with_for_update().first()
        if control is None:
            raise RailNotFound("Rail control is not available")
        scope = cls.resolve_scope(db, scope_type=control.scope_type, scope_ref=control.scope_ref)
        cls._authorize(db, admin=admin, scope=scope, permission="rail.reopen.request")
        if control.status == "open":
            raise RailApprovalConflict("Rail is already open")
        if control.version != expected_version:
            raise RailVersionConflict("Rail version does not match")
        fingerprint = _fingerprint({"control_id": str(control_id), "reason": reason, "health_check_reference": health_check_reference, "expected_version": expected_version})
        existing = db.query(RailReopenRequest).filter(
            RailReopenRequest.control_id == control_id,
            RailReopenRequest.idempotency_key == idempotency_key,
        ).first()
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise RailIdempotencyConflict("Rail reopen idempotency key conflict")
            return existing
        health_status = cls._health_status(db, reference=health_check_reference, control=control)
        request = RailReopenRequest(
            control_id=control.id,
            axis=control.axis,
            scope_type=control.scope_type,
            scope_ref=control.scope_ref,
            status="requested",
            reason=reason.strip(),
            initiator_admin_id=admin.id,
            health_check_reference=health_check_reference.strip(),
            health_check_status=health_status,
            control_status=control.status,
            expected_control_version=control.version,
            version=1,
            schema_version=1,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            audit_reference=f"pay-mp-002:rail:reopen-request:{uuid4()}",
        )
        db.add(request)
        db.flush()
        audit_reference = cls._audit(
            db, admin=admin, scope=scope, action="rail.control.reopen_requested", resource_id=control.id,
            result="requested", before={"status": control.status, "version": control.version},
            after={"request_id": str(request.id), "status": request.status, "health_check_status": health_status},
            reason=reason, health_check_reference=health_check_reference,
        )
        request.audit_reference = audit_reference
        cls._outbox(
            db, control=control, scope=scope, event_type="rail.control.reopen_requested",
            idempotency_key=f"rail-reopen-request:{request.id}", status=request.status,
            reason="reopen_requested", audit_reference=audit_reference, entity_id=request.id,
        )
        db.commit()
        db.refresh(request)
        return request

    @classmethod
    def decide_reopen(
        cls,
        db: Session,
        *,
        admin: AdminUser,
        request_id: UUID,
        decision: str,
        reason: str,
        expected_version: int,
        idempotency_key: str,
    ) -> RailReopenRequest:
        if decision not in {"approve", "reject"} or not reason.strip() or not idempotency_key.strip():
            raise RailRequestInvalid("Rail reopen decision is invalid")
        request = db.query(RailReopenRequest).filter(RailReopenRequest.id == request_id).with_for_update().first()
        if request is None:
            raise RailNotFound("Rail reopen request is not available")
        control = db.query(RuntimeRailControl).filter(RuntimeRailControl.id == request.control_id).with_for_update().first()
        if control is None:
            raise RailNotFound("Rail control is not available")
        scope = cls.resolve_scope(db, scope_type=request.scope_type, scope_ref=request.scope_ref)
        cls._authorize(db, admin=admin, scope=scope, permission="rail.reopen.approve")
        fingerprint = _fingerprint({"decision": decision, "reason": reason, "expected_version": expected_version})
        if request.decision_idempotency_key == idempotency_key:
            if request.decision_fingerprint != fingerprint:
                raise RailIdempotencyConflict("Rail decision idempotency key conflict")
            return request
        if request.status != "requested":
            raise RailApprovalConflict("Rail reopen request is no longer pending")
        if request.version != expected_version:
            raise RailVersionConflict("Rail reopen request version does not match")
        if request.initiator_admin_id == admin.id:
            raise RailApprovalConflict("Rail reopen requires a different actor")
        if request.expires_at is not None and _utc(request.expires_at) <= _now():
            request.status = "expired"
            request.version += 1
            db.commit()
            raise RailApprovalExpired("Rail reopen request has expired")
        if control.version != request.expected_control_version or control.status != "closed":
            raise RailVersionConflict("Rail control changed while approval was pending")
        health_status = cls._health_status(db, reference=request.health_check_reference, control=control)
        request.health_check_status = health_status
        if decision == "approve" and health_status != "passed":
            db.commit()
            if health_status == "unknown":
                raise RailStateUnknown("Rail health is unknown")
            raise RailApprovalConflict("Rail health check failed")
        request.decision_idempotency_key = idempotency_key
        request.decision_fingerprint = fingerprint
        request.approver_admin_id = admin.id
        request.decided_at = _now()
        request.version += 1
        if decision == "reject":
            request.status = "rejected"
            request.control_status = control.status
            audit_action = "rail.control.decision_recorded"
            event_type = "rail.control.decision_recorded"
            event_status = request.status
        else:
            before = {"status": control.status, "version": control.version}
            control.status = "open"
            control.reopened_by_admin_id = admin.id
            control.reopened_at = _now()
            control.health_check_reference = request.health_check_reference
            control.health_check_status = health_status
            control.version += 1
            request.status = "approved"
            request.control_status = control.status
            audit_action = "rail.control.reopened"
            event_type = "rail.control.reopened"
            event_status = control.status
        audit_reference = cls._audit(
            db, admin=admin, scope=scope, action=audit_action, resource_id=control.id,
            result=request.status, before={"status": control.status if decision == "reject" else "closed", "version": control.version if decision == "reject" else control.version - 1},
            after={"request_id": str(request.id), "status": event_status, "version": control.version},
            reason=reason, health_check_reference=request.health_check_reference,
        )
        request.audit_reference = audit_reference
        control.audit_reference = audit_reference if decision == "approve" else control.audit_reference
        cls._outbox(
            db, control=control, scope=scope, event_type=event_type,
            idempotency_key=f"rail-reopen-decision:{request.id}:{request.version}", status=event_status,
            reason="reopen_approved" if decision == "approve" else "reopen_rejected",
            audit_reference=audit_reference, entity_id=request.id,
        )
        db.commit()
        db.refresh(request)
        return request

    @classmethod
    def list_controls(
        cls,
        db: Session,
        *,
        admin: AdminUser,
        axis: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        if axis is not None and axis not in AXES:
            raise RailRequestInvalid("Invalid rail axis")
        if scope_type is not None and scope_type not in SCOPE_TYPES:
            raise RailRequestInvalid("Invalid rail scope type")
        if not 1 <= limit <= 100:
            raise RailRequestInvalid("Invalid limit")
        query = db.query(RuntimeRailControl).order_by(RuntimeRailControl.updated_at.desc(), RuntimeRailControl.id.desc())
        if axis:
            query = query.filter(RuntimeRailControl.axis == axis)
        if scope_type:
            query = query.filter(RuntimeRailControl.scope_type == scope_type)
        if scope_id:
            desired = scope_id
            if scope_type and not desired.startswith(f"{scope_type}:"):
                desired = f"{scope_type}:{desired}"
            query = query.filter(RuntimeRailControl.scope_ref == desired)
        decoded = _cursor_decode(cursor)
        if decoded:
            updated_at, resource_id = decoded
            query = query.filter(
                (RuntimeRailControl.updated_at < updated_at)
                | ((RuntimeRailControl.updated_at == updated_at) & (RuntimeRailControl.id < resource_id))
            )
        rows = query.limit(limit + 1).all()
        visible = []
        for row in rows:
            try:
                scope = cls.resolve_scope(db, scope_type=row.scope_type, scope_ref=row.scope_ref)
                cls._authorize(db, admin=admin, scope=scope, permission="rail.read")
            except RailError:
                continue
            visible.append(row)
        has_more = len(visible) > limit
        visible = visible[:limit]
        return {
            "items": [cls._projection(db, row, admin=admin) for row in visible],
            "page": {
                "next_cursor": _cursor_encode(visible[-1].updated_at, visible[-1].id) if has_more and visible else None,
                "has_more": has_more,
            },
        }
