"""Test-phase asset lifecycle compatibility helpers.

The production lifecycle design has dedicated persisted states. During the
test phase we deliberately reuse existing columns and AuditLog so no schema
migration is required. Transaction ownership remains with the caller.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional, Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.models import AuditLog, ChargePoint, Site


SiteLifecycleStatus = Literal["active", "archived"]
ChargePointLifecycleStatus = Literal["active", "retired"]
LifecycleResourceType = Literal["site", "charge_point"]

SITE_ARCHIVE_ACTION = "site.archive"
SITE_RESTORE_ACTION = "site.restore"
SITE_DELETE_ACTION = "site.delete"
CHARGER_RETIRE_ACTION = "charge_point.retire"
CHARGER_RESTORE_ACTION = "charge_point.restore"
CHARGER_DELETE_ACTION = "charge_point.delete"
CHARGER_MOVE_ACTION = "charge_point.move"


class LifecycleReasonError(ValueError):
    """Raised when an operator reason is missing or outside the contract."""


class AssetNotOperationalError(ValueError):
    """Raised when a charger or its site cannot accept new business."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_lifecycle_reason(reason: str) -> str:
    normalized = (reason or "").strip()
    if not 3 <= len(normalized) <= 500:
        raise LifecycleReasonError("reason must contain 3-500 characters")
    return normalized


def site_lifecycle_status(site: Site) -> SiteLifecycleStatus:
    return "active" if site.is_active is not False else "archived"


def charge_point_lifecycle_status(
    charge_point: ChargePoint,
) -> ChargePointLifecycleStatus:
    # ``is_active`` is the safety boundary for legacy rows. Lifecycle writes
    # additionally set commissioning_status=suspended, but an older inactive
    # row must never leak back into normal operations merely because that
    # secondary field predates this compatibility layer.
    return "active" if charge_point.is_active is not False else "retired"


def require_charge_point_operational(charge_point: ChargePoint) -> None:
    """Fail closed unless both the charger and its owning site are active."""

    if charge_point.is_active is not True:
        raise AssetNotOperationalError(
            "charger_not_operational",
            "The charge point is retired and cannot accept new business",
        )
    site = charge_point.site
    if site is None or site.is_active is not True:
        raise AssetNotOperationalError(
            "site_not_operational",
            "The charge point site is archived and cannot accept new business",
        )


def apply_site_archived_state(site: Site) -> None:
    site.is_active = False


def apply_site_restored_state(site: Site) -> None:
    site.is_active = True


def apply_charge_point_retired_state(charge_point: ChargePoint) -> None:
    charge_point.is_active = False
    charge_point.commissioning_status = "suspended"
    charge_point.ocpp_auth_secret_hash = None


def apply_charge_point_restored_state(charge_point: ChargePoint) -> None:
    charge_point.is_active = True
    charge_point.commissioning_status = "testing"


def add_lifecycle_audit(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    action: str,
    resource_type: LifecycleResourceType,
    resource_id: str,
    reason: str,
    before_data: Optional[Mapping[str, Any]] = None,
    after_data: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> AuditLog:
    """Stage a lifecycle audit row without committing the caller's transaction."""

    normalized_reason = normalize_lifecycle_reason(reason)
    audit_metadata = dict(metadata or {})
    audit_metadata["reason"] = normalized_reason
    audit = AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="admin",
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        before_data=dict(before_data) if before_data is not None else None,
        after_data=dict(after_data) if after_data is not None else None,
        audit_metadata=audit_metadata,
    )
    db.add(audit)
    db.flush()
    return audit


def latest_lifecycle_audit(
    db: Session,
    *,
    tenant_id: UUID,
    resource_type: LifecycleResourceType,
    resource_id: str,
    actions: Sequence[str],
) -> Optional[AuditLog]:
    """Return the latest matching audit inside the authenticated tenant scope."""

    if not actions:
        return None
    return (
        db.query(AuditLog)
        .filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.resource_type == resource_type,
            AuditLog.resource_id == str(resource_id),
            AuditLog.action.in_(tuple(actions)),
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .first()
    )
