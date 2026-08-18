"""Authorized PAY-MP-002-v2 risk projections for Admin operations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.database.base import get_db, tenant_id_context
from app.services.risk_budget import RiskBudgetError, RiskBudgetService, V2_MEDIA_TYPE


router = APIRouter()


def _check_v2(accept: str | None) -> None:
    if accept != V2_MEDIA_TYPE:
        raise HTTPException(status_code=406, detail={"code": "CONTRACT_VERSION_UNSUPPORTED", "message": "PAY-MP-002-v2 is required for this risk resource.", "retryable": False})


def _response(payload: dict) -> JSONResponse:
    response = JSONResponse(payload, media_type=V2_MEDIA_TYPE)
    response.headers["Vary"] = "Accept"
    return response


def _raise(exc: RiskBudgetError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message, "retryable": exc.retryable, **exc.details}) from exc


@router.get("/risk-sessions/{session_id}", summary="PAY-MP-002-v2 Admin risk session")
def get_admin_risk_session(
    session_id: uuid.UUID,
    accept: str | None = Header(None, alias="Accept"),
    _admin=Depends(require_permission("audit.read")),
    db: Session = Depends(get_db),
):
    _check_v2(accept)
    try:
        return _response(RiskBudgetService.risk_session_projection(db, session_id=session_id, tenant_id=tenant_id_context.get(None)))
    except RiskBudgetError as exc:
        return _raise(exc)


@router.get("/risk-stops/{stop_id}", summary="PAY-MP-002-v2 Admin risk stop")
def get_admin_risk_stop(
    stop_id: uuid.UUID,
    accept: str | None = Header(None, alias="Accept"),
    _admin=Depends(require_permission("audit.read")),
    db: Session = Depends(get_db),
):
    _check_v2(accept)
    try:
        return _response(RiskBudgetService.risk_stop_projection(db, stop_id=stop_id, tenant_id=tenant_id_context.get(None)))
    except RiskBudgetError as exc:
        return _raise(exc)


@router.get("/provider-resolutions/{resolution_id}", summary="PAY-MP-002-v2 Admin Provider resolution")
def get_admin_provider_resolution(
    resolution_id: uuid.UUID,
    accept: str | None = Header(None, alias="Accept"),
    _admin=Depends(require_permission("audit.read")),
    db: Session = Depends(get_db),
):
    _check_v2(accept)
    try:
        return _response(RiskBudgetService.provider_resolution_projection(db, resolution_id=resolution_id, tenant_id=tenant_id_context.get(None)))
    except RiskBudgetError as exc:
        return _raise(exc)
