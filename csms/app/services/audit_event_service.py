"""Safe, read-only PAY-MP-002 Admin AuditEvent projection.

AuditLog remains the existing operations/audit authority.  This module only
projects bounded, tenant/platform-scoped safe fields for the frozen Admin API;
it does not create audit facts or expose before/after payloads.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import func, literal, or_
from sqlalchemy.orm import Session

from app.core.tenant_middleware import tenant_id_context
from app.database.models import AdminUser, AuditLog


MAX_PAGE_SIZE = 100
PLATFORM_REF = "platform:eslatin"
_SAFE_TEXT = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")
_SENSITIVE_KEY_TOKENS = {
    "pan",
    "cvv",
    "cvc",
    "token",
    "secret",
    "credential",
    "password",
    "authorization",
}
_SENSITIVE_KEY_COMPOUNDS = {
    "privatekey",
    "rawproviderpayload",
    "providerpayload",
    "webhookpayload",
}
_SENSITIVE_VALUE = re.compile(r"(?:\b\d{13,19}\b|-----BEGIN [A-Z ]+-----)")


class AuditEventError(RuntimeError):
    code = "REQUEST_INVALID"
    status_code = 422
    retryable = False


class AuditEventRequestInvalid(AuditEventError):
    code = "REQUEST_INVALID"


class AuditEventPaginationModeInvalid(AuditEventError):
    code = "PAGINATION_MODE_INVALID"
    status_code = 400


class AuditEventCursorInvalid(AuditEventError):
    code = "CURSOR_INVALID"
    status_code = 409


class AuditEventPermissionDenied(AuditEventError):
    code = "PERMISSION_DENIED"
    status_code = 403


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _utc(value).isoformat().replace("+00:00", "Z") if value else None


def _parse_datetime(value: str | None, field: str) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise AuditEventRequestInvalid(f"{field} must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None:
        raise AuditEventRequestInvalid(f"{field} must include a UTC offset")
    return _utc(parsed)


def _is_sensitive_key(key: str) -> bool:
    """Match sensitive names across snake_case, camelCase, acronyms, and nesting."""
    # Split acronym-to-word (PANNumber) and lower-to-upper (rawProviderPayload)
    # boundaries before normalizing separators.
    separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key)
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", separated)
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", separated).casefold()
    tokens = tuple(token for token in normalized.split("_") if token)
    if any(token in _SENSITIVE_KEY_TOKENS for token in tokens):
        return True
    compact = "".join(tokens)
    return any(marker in compact for marker in _SENSITIVE_KEY_COMPOUNDS)


def _safe_filter(value: Any, *, depth: int = 0) -> Any:
    """Keep only bounded JSON primitives and recursively safe containers."""
    if depth > 3:
        return None
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:50]:
            key = str(raw_key)
            if _is_sensitive_key(key):
                continue
            safe_value = _safe_filter(raw_value, depth=depth + 1)
            if safe_value is not None:
                result[key[:100]] = safe_value
        return result
    if isinstance(value, (list, tuple)):
        return [item for item in (_safe_filter(entry, depth=depth + 1) for entry in list(value)[:50]) if item is not None]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if _SENSITIVE_VALUE.search(value):
            return None
        return value[:256]
    return None


def _safe_string(value: Any, fallback: str | None = None) -> str | None:
    if not isinstance(value, str):
        return fallback
    candidate = value.strip()
    return candidate[:256] if candidate and _SAFE_TEXT.fullmatch(candidate) else fallback


def _cursor_fingerprint(filters: Mapping[str, Any]) -> str:
    raw = json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _encode_cursor(*, occurred_at: datetime, event_id: UUID, fingerprint: str) -> str:
    raw = json.dumps(
        {"occurred_at": _iso(occurred_at), "event_id": str(event_id), "filters": fingerprint},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str | None, *, fingerprint: str) -> tuple[datetime, UUID] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if payload.get("filters") != fingerprint:
            raise ValueError("cursor filter binding mismatch")
        occurred_at = _parse_datetime(str(payload["occurred_at"]), "cursor.occurred_at")
        return occurred_at, UUID(str(payload["event_id"]))
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditEventCursorInvalid("Invalid audit event cursor") from exc


def _uuid_filter(value: str | None, field: str) -> UUID | None:
    if value is None or value == "":
        return None
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise AuditEventRequestInvalid(f"{field} is invalid") from exc


def _result_expression():
    """Derive result without requiring a schema change to legacy AuditLog."""
    metadata_result = AuditLog.audit_metadata["result"].as_string()
    after_result = AuditLog.after_data["result"].as_string()
    before_result = AuditLog.before_data["result"].as_string()
    return func.coalesce(metadata_result, after_result, before_result, literal("unknown"))


class AuditEventService:
    """Read-only server-authorized AuditEvent projection."""

    @staticmethod
    def _scope(admin: AdminUser) -> tuple[str, UUID | None]:
        tenant_id = tenant_id_context.get()
        if admin.is_super_admin:
            return ("tenant", tenant_id) if tenant_id else ("platform", None)
        if tenant_id is None:
            raise AuditEventPermissionDenied("Tenant context required")
        return "tenant", tenant_id

    @staticmethod
    def _actor(db: Session, event: AuditLog) -> dict[str, str] | None:
        if event.actor_type == "system":
            return None
        if event.actor_type == "admin":
            actor = db.query(AdminUser).filter(AdminUser.id == event.actor_id).first()
            return {
                "id": str(event.actor_id),
                "display_name": _safe_string((actor.full_name or actor.username) if actor else None, "Admin operator"),
                "role_label": "platform" if actor and actor.is_super_admin else "operations",
            }
        if event.actor_type == "app_user":
            return {"id": str(event.actor_id), "display_name": "App user", "role_label": "app_user"}
        return None

    @staticmethod
    def _event_scope(event: AuditLog) -> dict[str, str]:
        if event.tenant_id is None:
            return {"type": "platform", "ref": PLATFORM_REF}
        return {"type": "tenant", "ref": f"tenant:{event.tenant_id}"}

    @classmethod
    def _project(cls, db: Session, event: AuditLog) -> dict[str, Any]:
        metadata = event.audit_metadata if isinstance(event.audit_metadata, Mapping) else {}
        after = event.after_data if isinstance(event.after_data, Mapping) else {}
        before = event.before_data if isinstance(event.before_data, Mapping) else {}
        result = _safe_string(metadata.get("result") or after.get("result") or before.get("result"), "unknown")
        reason_code = _safe_string(metadata.get("reason_code") or after.get("reason_code") or before.get("reason_code"))
        safe_metadata = _safe_filter(metadata)
        if not isinstance(safe_metadata, dict):
            safe_metadata = {}
        return {
            "event_id": str(event.id),
            "actor": cls._actor(db, event),
            "resource": {
                "type": _safe_string(event.resource_type, "unknown"),
                "id": _safe_string(event.resource_id, ""),
            },
            "action": _safe_string(event.action, "unknown"),
            "result": result,
            "scope": cls._event_scope(event),
            "reason_code": reason_code,
            "safe_metadata": safe_metadata,
            "occurred_at": _iso(event.created_at),
        }

    @classmethod
    def list_events(
        cls,
        db: Session,
        *,
        admin: AdminUser,
        actor: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        action: str | None = None,
        result: str | None = None,
        from_value: str | None = None,
        to_value: str | None = None,
        cursor: str | None = None,
        limit: int | str = 50,
    ) -> dict[str, Any]:
        try:
            limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise AuditEventRequestInvalid("limit must be between 1 and 100") from exc
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise AuditEventRequestInvalid("limit must be between 1 and 100")

        actor_id = _uuid_filter(actor, "actor")
        from_at = _parse_datetime(from_value, "from")
        to_at = _parse_datetime(to_value, "to")
        if from_at and to_at and from_at > to_at:
            raise AuditEventRequestInvalid("from must be before or equal to to")

        scope_type, tenant_id = cls._scope(admin)
        filters = {
            "scope_type": scope_type,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "actor": str(actor_id) if actor_id else None,
            "resource_type": resource_type or None,
            "resource_id": resource_id or None,
            "action": action or None,
            "result": result or None,
            "from": _iso(from_at),
            "to": _iso(to_at),
        }
        fingerprint = _cursor_fingerprint(filters)
        decoded = _decode_cursor(cursor, fingerprint=fingerprint)

        query = db.query(AuditLog)
        if scope_type == "tenant":
            query = query.filter(AuditLog.tenant_id == tenant_id)
        if actor_id:
            query = query.filter(AuditLog.actor_id == actor_id)
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        if resource_id:
            query = query.filter(AuditLog.resource_id == resource_id)
        if action:
            query = query.filter(AuditLog.action == action)
        if from_at:
            query = query.filter(AuditLog.created_at >= from_at)
        if to_at:
            query = query.filter(AuditLog.created_at <= to_at)
        if result:
            query = query.filter(_result_expression() == result)
        if decoded:
            occurred_at, event_id = decoded
            query = query.filter(
                (AuditLog.created_at < occurred_at)
                | ((AuditLog.created_at == occurred_at) & (AuditLog.id < event_id))
            )

        rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1).all()
        has_more = len(rows) > limit
        visible = rows[:limit]
        return {
            "items": [cls._project(db, event) for event in visible],
            "page": {
                "next_cursor": _encode_cursor(occurred_at=visible[-1].created_at, event_id=visible[-1].id, fingerprint=fingerprint) if has_more and visible else None,
                "has_more": has_more,
            },
        }
