"""Frozen PAY-MP-002-v1 runtime rail control endpoints."""

from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.validation import StrictRequestModel
from app.core.permissions import require_permission
from app.database.base import get_db
from app.database.models import AdminUser
from app.services.runtime_rail_control import (
    RailError,
    RuntimeRailControlService,
)


router = APIRouter()


class RailScopeRequest(StrictRequestModel):
    type: Literal["platform", "provider", "tenant", "site"]
    ref: str = Field(..., min_length=1, max_length=100)


class RailCloseRequest(StrictRequestModel):
    axis: Literal["paid_admission", "payment_creation"]
    scope: RailScopeRequest
    reason: str = Field(..., min_length=1, max_length=4000)
    incident_reference: str = Field(..., min_length=1, max_length=255)
    expected_version: int = Field(ge=0)


class RailReopenRequestBody(StrictRequestModel):
    reason: str = Field(..., min_length=1, max_length=4000)
    health_check_reference: str = Field(..., min_length=1, max_length=255)
    expected_version: int = Field(ge=1)


class RailReopenDecisionRequest(StrictRequestModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(..., min_length=1, max_length=4000)
    expected_version: int = Field(ge=1)


def _error(exc: RailError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error": {
                "code": exc.code,
                "message": str(exc),
                "reference": None,
                "retryable": exc.retryable,
                "retry_after_seconds": 2 if exc.retryable else None,
                "current_version": None,
            }
        },
    )


@router.get("/runtime-rails", summary="List runtime rail controls")
def list_runtime_rails(
    axis: Optional[str] = Query(None),
    scope_type: Optional[str] = Query(None),
    scope_id: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50),
    admin: AdminUser = Depends(require_permission("rail.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return RuntimeRailControlService.list_controls(
            db,
            admin=admin,
            axis=axis,
            scope_type=scope_type,
            scope_id=scope_id,
            cursor=cursor,
            limit=limit,
        )
    except RailError as exc:
        raise _error(exc) from exc


@router.post("/runtime-rails/close-requests", status_code=201, summary="Close a runtime rail")
def close_runtime_rail(
    payload: RailCloseRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    admin: AdminUser = Depends(require_permission("rail.close")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Idempotency-Key is required"}})
    try:
        control = RuntimeRailControlService.close(
            db,
            admin=admin,
            axis=payload.axis,
            scope_type=payload.scope.type,
            scope_ref=payload.scope.ref,
            reason=payload.reason,
            incident_reference=payload.incident_reference,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        )
        return RuntimeRailControlService._projection(db, control, admin=admin)
    except RailError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/runtime-rails/{control_id}/reopen-requests", status_code=201, summary="Request rail reopen")
def request_runtime_rail_reopen(
    control_id: UUID,
    payload: RailReopenRequestBody,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    admin: AdminUser = Depends(require_permission("rail.reopen.request")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Idempotency-Key is required"}})
    try:
        request = RuntimeRailControlService.request_reopen(
            db,
            admin=admin,
            control_id=control_id,
            reason=payload.reason,
            health_check_reference=payload.health_check_reference,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        )
        return RuntimeRailControlService._reopen_projection(db, request)
    except RailError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/runtime-rail-reopen-requests/{request_id}/decisions", summary="Decide a rail reopen request")
def decide_runtime_rail_reopen(
    request_id: UUID,
    payload: RailReopenDecisionRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    admin: AdminUser = Depends(require_permission("rail.reopen.approve")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Idempotency-Key is required"}})
    try:
        request = RuntimeRailControlService.decide_reopen(
            db,
            admin=admin,
            request_id=request_id,
            decision=payload.decision,
            reason=payload.reason,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        )
        return RuntimeRailControlService._reopen_projection(db, request)
    except RailError as exc:
        db.rollback()
        raise _error(exc) from exc

