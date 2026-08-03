"""Tenant-scoped read APIs for archived sites and retired chargers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.database.base import get_db, tenant_id_context
from app.database.models import AdminUser, AuditLog, ChargePoint, Site
from app.services.asset_lifecycle_service import CHARGER_RETIRE_ACTION, SITE_ARCHIVE_ACTION


router = APIRouter()


def _current_tenant_id() -> UUID:
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _latest_audits(
    db: Session,
    *,
    tenant_id: UUID,
    resource_type: str,
    action: str,
) -> dict[str, AuditLog]:
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.resource_type == resource_type,
            AuditLog.action == action,
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .all()
    )
    latest: dict[str, AuditLog] = {}
    for row in rows:
        if row.resource_id:
            latest.setdefault(row.resource_id, row)
    return latest


def _actors(db: Session, audits: dict[str, AuditLog]) -> dict[UUID, AdminUser]:
    actor_ids = {audit.actor_id for audit in audits.values() if audit.actor_type == "admin"}
    if not actor_ids:
        return {}
    return {
        actor.id: actor
        for actor in db.query(AdminUser).filter(AdminUser.id.in_(actor_ids)).all()
    }


def _actor_payload(audit: Optional[AuditLog], actors: dict[UUID, AdminUser]) -> Optional[dict[str, str | None]]:
    if not audit:
        return None
    actor = actors.get(audit.actor_id)
    if not actor:
        return {"id": str(audit.actor_id), "username": None, "full_name": None}
    return {
        "id": str(actor.id),
        "username": actor.username,
        "full_name": actor.full_name,
    }


def _audit_matches(
    audit: Optional[AuditLog],
    *,
    from_time: Optional[datetime],
    to_time: Optional[datetime],
) -> bool:
    if from_time or to_time:
        if not audit or not audit.created_at:
            return False
        created_at = _utc(audit.created_at)
        if from_time and created_at < _utc(from_time):
            return False
        if to_time and created_at > _utc(to_time):
            return False
    return True


@router.get("/sites", summary="查询已归档站点")
def list_archived_sites(
    search: Optional[str] = Query(None, max_length=200),
    archived_from: Optional[datetime] = Query(None),
    archived_to: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _current_user=Depends(require_permission("sites.read")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant_id = _current_tenant_id()
    normalized_search = search.strip().casefold() if search and search.strip() else None
    audits = _latest_audits(
        db,
        tenant_id=tenant_id,
        resource_type="site",
        action=SITE_ARCHIVE_ACTION,
    )
    actors = _actors(db, audits)

    sites = (
        db.query(Site)
        .filter(Site.tenant_id == tenant_id, Site.is_active.is_(False))
        .all()
    )
    matched: list[tuple[Site, Optional[AuditLog]]] = []
    for site in sites:
        audit = audits.get(str(site.id))
        asset_matches = not normalized_search or any(
            normalized_search in str(value or "").casefold()
            for value in (site.site_code, site.name, site.address)
        )
        audit_matches_search = bool(
            normalized_search
            and audit
            and normalized_search
            in str((audit.audit_metadata or {}).get("reason") or "").casefold()
        )
        if not asset_matches and not audit_matches_search:
            continue
        if not _audit_matches(
            audit,
            from_time=archived_from,
            to_time=archived_to,
        ):
            continue
        matched.append((site, audit))

    matched.sort(
        key=lambda item: _utc(item[1].created_at) if item[1] and item[1].created_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    page = matched[offset:offset + limit]
    site_ids = [site.id for site, _audit in page]
    retired_counts = dict(
        db.query(ChargePoint.site_id, func.count(ChargePoint.id))
        .filter(
            ChargePoint.tenant_id == tenant_id,
            ChargePoint.site_id.in_(site_ids),
            ChargePoint.is_active.is_(False),
        )
        .group_by(ChargePoint.site_id)
        .all()
    ) if site_ids else {}

    return [
        {
            "id": str(site.id),
            "site_code": site.site_code,
            "name": site.name,
            "address": site.address,
            "lifecycle_status": "archived",
            "archived_at": audit.created_at.isoformat() if audit and audit.created_at else None,
            "archive_reason": (audit.audit_metadata or {}).get("reason") if audit else None,
            "archived_by": _actor_payload(audit, actors),
            "active_charge_points_count": 0,
            "retiring_charge_points_count": 0,
            "retired_charge_points_count": int(retired_counts.get(site.id, 0)),
        }
        for site, audit in page
    ]


@router.get("/chargers", summary="查询已退役充电桩")
def list_retired_chargers(
    search: Optional[str] = Query(None, max_length=200),
    original_site_id: Optional[UUID] = Query(None),
    retired_from: Optional[datetime] = Query(None),
    retired_to: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _current_user=Depends(require_permission("chargers.read")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant_id = _current_tenant_id()
    normalized_search = search.strip().casefold() if search and search.strip() else None
    audits = _latest_audits(
        db,
        tenant_id=tenant_id,
        resource_type="charge_point",
        action=CHARGER_RETIRE_ACTION,
    )
    actors = _actors(db, audits)

    query = (
        db.query(ChargePoint, Site)
        .join(Site, ChargePoint.site_id == Site.id)
        .filter(
            ChargePoint.tenant_id == tenant_id,
            ChargePoint.is_active.is_(False),
        )
    )
    if original_site_id:
        query = query.filter(ChargePoint.site_id == original_site_id)

    matched: list[tuple[ChargePoint, Site, Optional[AuditLog]]] = []
    for charge_point, site in query.all():
        audit = audits.get(str(charge_point.id))
        asset_matches = not normalized_search or any(
            normalized_search in str(value or "").casefold()
            for value in (
                charge_point.display_code,
                charge_point.display_name,
                charge_point.ocpp_identity,
                site.site_code,
                site.name,
            )
        )
        audit_matches_search = bool(
            normalized_search
            and audit
            and normalized_search
            in str((audit.audit_metadata or {}).get("reason") or "").casefold()
        )
        if not asset_matches and not audit_matches_search:
            continue
        if not _audit_matches(
            audit,
            from_time=retired_from,
            to_time=retired_to,
        ):
            continue
        matched.append((charge_point, site, audit))

    matched.sort(
        key=lambda item: _utc(item[2].created_at) if item[2] and item[2].created_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    page = matched[offset:offset + limit]
    return [
        {
            "id": str(charge_point.id),
            "ocpp_identity": charge_point.ocpp_identity,
            "display_code": charge_point.display_code,
            "display_name": charge_point.display_name,
            "vendor": charge_point.vendor,
            "model": charge_point.model,
            "lifecycle_status": "retired",
            "retirement_reason": (audit.audit_metadata or {}).get("reason") if audit else None,
            "retired_at": audit.created_at.isoformat() if audit and audit.created_at else None,
            "retired_by": _actor_payload(audit, actors),
            "original_site": {
                "id": str(site.id),
                "site_code": site.site_code,
                "name": site.name,
            },
        }
        for charge_point, site, audit in page
    ]
