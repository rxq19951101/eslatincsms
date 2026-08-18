"""Frozen PAY-MP-002 Admin AuditEvent read projection."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.permissions import check_permission, get_current_admin_user
from app.database.base import get_db, tenant_id_context
from app.database.models import AdminUser
from app.services.audit_event_service import (
    AuditEventError,
    AuditEventPaginationModeInvalid,
    AuditEventPermissionDenied,
    AuditEventService,
)


router = APIRouter()
PAY_MP_002_MEDIA_TYPE = "application/vnd.eslatin.pay-mp-002.v1+json"


def _error(exc: AuditEventError) -> HTTPException:
    http_error = HTTPException(
        status_code=exc.status_code,
        detail={"error": {
            "code": exc.code,
            "message": str(exc),
            "reference": None,
            "retryable": exc.retryable,
            "retry_after_seconds": 2 if exc.retryable else None,
            "current_version": None,
        }},
    )
    # The project-wide handler uses this attribute for the canonical envelope.
    http_error.error_code = exc.code
    return http_error


async def require_audit_read(
    admin_user: AdminUser = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Use the shared permission evaluator with this route's canonical error shape."""
    if admin_user.is_super_admin:
        return admin_user
    tenant_id = tenant_id_context.get()
    if tenant_id is None or not check_permission(admin_user.id, "audit.read", db, tenant_id):
        raise _error(AuditEventPermissionDenied("Permission denied: audit.read"))
    return admin_user


@router.get("/audit-events", summary="List safe AuditEvents")
def list_audit_events(
    actor: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    from_value: Optional[str] = Query(None, alias="from"),
    to_value: Optional[str] = Query(None, alias="to"),
    cursor: Optional[str] = Query(None),
    limit: str = Query("50"),
    offset: Optional[int] = Query(None),
    admin: AdminUser = Depends(require_audit_read),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if offset is not None:
        raise _error(AuditEventPaginationModeInvalid("Audit events use cursor pagination"))
    try:
        payload: dict[str, Any] = AuditEventService.list_events(
            db,
            admin=admin,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            result=result,
            from_value=from_value,
            to_value=to_value,
            cursor=cursor,
            limit=limit,
        )
    except AuditEventError as exc:
        raise _error(exc) from exc
    response = JSONResponse(payload, media_type=PAY_MP_002_MEDIA_TYPE)
    response.headers["Vary"] = "Accept"
    return response
