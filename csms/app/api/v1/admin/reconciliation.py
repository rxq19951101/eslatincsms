"""Frozen PAY-MP-002-v1 Admin reconciliation endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.database.base import get_db
from app.database.models import AdminUser
from app.services.reconciliation import (
    ReconciliationError,
    ReconciliationService,
    _project_export,
    _project_exception,
    _project_item,
    _project_run,
)


router = APIRouter()


class ResolutionIntentRequest(BaseModel):
    resolution_code: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)


class TemporaryAcceptanceRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)


class TemporaryAcceptanceDecisionRequest(BaseModel):
    decision: str
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)


class ReconciliationExportRequest(BaseModel):
    run_id: UUID
    filters: dict[str, Any] = Field(default_factory=dict)
    format: str = "csv"


def _error(exc: ReconciliationError) -> HTTPException:
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
    http_error.error_code = exc.code
    return http_error


def _limit(value: int) -> int:
    if value < 1 or value > 100:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "limit must be between 1 and 100"}})
    return value


def _tenant(value: Optional[str]) -> Optional[UUID]:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "tenant_scope is invalid"}}) from exc


@router.get("/runs", summary="List reconciliation runs")
def list_reconciliation_runs(
    business_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50),
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return ReconciliationService().list_runs(db, actor=admin, status=status, business_date=business_date,
                                                 cursor=cursor, limit=_limit(limit), tenant_id=_tenant(tenant_scope))
    except ReconciliationError as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}", summary="Get reconciliation run")
def get_reconciliation_run(
    run_id: UUID,
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        run = ReconciliationService().get_run(db, actor=admin, run_id=run_id, tenant_id=_tenant(tenant_scope))
        return _project_run(run)
    except ReconciliationError as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/items", summary="List reconciliation items")
def list_reconciliation_items(
    run_id: UUID,
    status: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50),
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    # The frozen endpoint accepts cursor; the service deliberately keeps this
    # first implementation bounded and stable. An invalid cursor is rejected
    # rather than silently returning page one.
    if cursor:
        from app.services.reconciliation import _cursor_decode
        _cursor_decode(cursor)
    try:
        return ReconciliationService().list_items(db, actor=admin, run_id=run_id, status=status, cursor=cursor,
                                                  limit=_limit(limit), tenant_id=_tenant(tenant_scope))
    except ReconciliationError as exc:
        raise _error(exc) from exc


@router.get("/exceptions", summary="List reconciliation exceptions")
def list_reconciliation_exceptions(
    status: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50),
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if cursor:
        from app.services.reconciliation import _cursor_decode
        _cursor_decode(cursor)
    try:
        return ReconciliationService().list_exceptions(db, actor=admin, status=status, cursor=cursor,
                                                       limit=_limit(limit), tenant_id=_tenant(tenant_scope))
    except ReconciliationError as exc:
        raise _error(exc) from exc


@router.get("/exceptions/{exception_id}", summary="Get reconciliation exception")
def get_reconciliation_exception(
    exception_id: UUID,
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        exception = ReconciliationService().get_exception(db, actor=admin, exception_id=exception_id, tenant_id=_tenant(tenant_scope))
        return _project_exception(exception)
    except ReconciliationError as exc:
        raise _error(exc) from exc


@router.post("/exceptions/{exception_id}/resolution-intents", status_code=201, summary="Resolve reconciliation exception")
def create_resolution_intent(
    exception_id: UUID,
    request: ResolutionIntentRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.resolve")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Idempotency-Key is required"}})
    try:
        exception = ReconciliationService().create_resolution_intent(
            db, actor=admin, exception_id=exception_id, resolution_code=request.resolution_code,
            reason=request.reason, expected_version=request.expected_version, idempotency_key=idempotency_key,
            tenant_id=_tenant(tenant_scope),
        )
        return _project_exception(exception)
    except ReconciliationError as exc:
        raise _error(exc) from exc


@router.post("/exceptions/{exception_id}/temporary-acceptance-requests", status_code=201, summary="Request temporary reconciliation acceptance")
def request_temporary_acceptance(
    exception_id: UUID,
    request: TemporaryAcceptanceRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.exception.request")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Idempotency-Key is required"}})
    try:
        exception = ReconciliationService().request_temporary_acceptance(
            db, actor=admin, exception_id=exception_id, reason=request.reason,
            expected_version=request.expected_version, idempotency_key=idempotency_key,
            tenant_id=_tenant(tenant_scope),
        )
        return _project_exception(exception)
    except ReconciliationError as exc:
        raise _error(exc) from exc


@router.post("/temporary-acceptance-requests/{request_id}/decisions", summary="Decide temporary reconciliation acceptance")
def decide_temporary_acceptance(
    request_id: UUID,
    request: TemporaryAcceptanceDecisionRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.exception.approve")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Idempotency-Key is required"}})
    try:
        exception = ReconciliationService().decide_temporary_acceptance(
            db, actor=admin, exception_id=request_id, decision=request.decision,
            reason=request.reason, expected_version=request.expected_version,
            idempotency_key=idempotency_key, tenant_id=_tenant(tenant_scope),
        )
        return _project_exception(exception)
    except ReconciliationError as exc:
        raise _error(exc) from exc


@router.post("/exports", status_code=202, summary="Queue reconciliation CSV export")
def create_reconciliation_export(
    request: ReconciliationExportRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Idempotency-Key is required"}})
    if request.format != "csv":
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Only csv exports are supported"}})
    try:
        export = ReconciliationService().create_export(
            db, actor=admin, run_id=request.run_id, filters=request.filters,
            idempotency_key=idempotency_key, tenant_id=_tenant(tenant_scope),
        )
        return _project_export(export)
    except ReconciliationError as exc:
        raise _error(exc) from exc


@router.get("/exports/{export_id}", summary="Get reconciliation export")
def get_reconciliation_export(
    export_id: UUID,
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        export = ReconciliationService().get_export(db, actor=admin, export_id=export_id, tenant_id=_tenant(tenant_scope))
        return _project_export(export)
    except ReconciliationError as exc:
        raise _error(exc) from exc


@router.get("/exports/{export_id}/download", summary="Download reconciliation CSV")
def download_reconciliation_export(
    export_id: UUID,
    tenant_scope: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("reconciliation.read")),
    db: Session = Depends(get_db),
) -> Response:
    try:
        service = ReconciliationService()
        resolved_tenant = _tenant(tenant_scope)
        content = service.download_export(db, actor=admin, export_id=export_id, tenant_id=resolved_tenant)
        export = service.get_export(db, actor=admin, export_id=export_id, tenant_id=resolved_tenant)
        filename = f"reconciliation-{export.id}.csv"
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Audit-Reference": export.audit_reference,
            },
        )
    except ReconciliationError as exc:
        raise _error(exc) from exc
