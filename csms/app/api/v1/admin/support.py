"""Frozen PAY-MP-002-v1 Admin support-case endpoints."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.validation import StrictRequestModel
from app.core.permissions import require_permission
from app.database.base import get_db
from app.database.models import AdminUser
from app.services.support_cases import SupportCaseService, SupportError, project_support_case


router = APIRouter()


class SupportCaseEventRequest(StrictRequestModel):
    event_type: str
    note: Optional[str] = Field(None, max_length=4000)
    note_visibility: str
    expected_version: int = Field(ge=1)


def _error(exc: SupportError) -> HTTPException:
    return HTTPException(
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


def _tenant(value: Optional[str]) -> Optional[UUID]:
    if value is None:
        return None
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "REQUEST_INVALID", "message": "tenant_scope is invalid"}},
        ) from exc


@router.get("/support-cases", summary="List support cases")
def list_support_cases(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    tenant_scope: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50),
    admin: AdminUser = Depends(require_permission("support.manage")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return SupportCaseService().list_admin_cases(
            db,
            admin=admin,
            status=status,
            category=category,
            tenant_id=_tenant(tenant_scope),
            cursor=cursor,
            limit=limit,
        )
    except SupportError as exc:
        raise _error(exc) from exc


@router.get("/support-cases/{case_id}", summary="Get support case")
def get_support_case(
    case_id: UUID,
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("support.manage")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        case = SupportCaseService().get_admin_case(
            db, admin=admin, case_id=case_id, tenant_id=_tenant(tenant_scope)
        )
        return project_support_case(db, case)
    except SupportError as exc:
        raise _error(exc) from exc


@router.post("/support-cases/{case_id}/events", status_code=201, summary="Add support case event")
def add_support_case_event(
    case_id: UUID,
    request: SupportCaseEventRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("support.manage")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "REQUEST_INVALID", "message": "Idempotency-Key is required"}},
        )
    try:
        tenant_id = _tenant(tenant_scope)
        event = SupportCaseService().add_admin_event(
            db,
            admin=admin,
            case_id=case_id,
            event_type=request.event_type,
            note=request.note,
            visibility=request.note_visibility,
            expected_version=request.expected_version,
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
        )
        case = SupportCaseService().get_admin_case(
            db, admin=admin, case_id=case_id, tenant_id=tenant_id
        )
        occurred_at = event.occurred_at.astimezone().isoformat().replace("+00:00", "Z") if event.occurred_at else None
        return {
            "event_id": str(event.id),
            "case_id": str(event.support_case_id),
            "event_type": event.event_type,
            "note_visibility": event.visibility,
            "status": event.status,
            "actor": {
                "id": str(admin.id),
                "display_name": (admin.full_name or admin.username or "Support operator")[:100],
                "role_label": "support",
            },
            "occurred_at": occurred_at,
            "case_version": case.version,
        }
    except SupportError as exc:
        raise _error(exc) from exc
