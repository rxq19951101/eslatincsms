"""PAY-MP-002-v2 read-only risk projections for the authenticated App user."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.base import get_db
from app.services.risk_budget import RiskBudgetService, RiskBudgetError, V2_MEDIA_TYPE


router = APIRouter()


def _v2_response(payload: dict[str, Any]) -> JSONResponse:
    response = JSONResponse(payload, media_type=V2_MEDIA_TYPE)
    response.headers["Vary"] = "Accept"
    return response


def _require_v2(accept: str | None) -> None:
    if accept != V2_MEDIA_TYPE:
        raise HTTPException(status_code=406, detail={
            "code": "CONTRACT_VERSION_UNSUPPORTED",
            "message": "PAY-MP-002-v2 is required for this risk resource.",
            "retryable": False,
        })


def _app_user_id(payload: dict[str, Any]) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload.get("user_id")))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def _risk_http_error(exc: RiskBudgetError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message, "retryable": exc.retryable, **exc.details},
    ) from exc


@router.get("/risk-sessions/{session_id}", summary="PAY-MP-002-v2 risk session")
def get_risk_session(
    session_id: uuid.UUID,
    accept: str | None = Header(None, alias="Accept"),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_v2(accept)
    try:
        return _v2_response(RiskBudgetService.risk_session_projection(db, session_id=session_id, app_user_id=_app_user_id(current_user)))
    except RiskBudgetError as exc:
        return _risk_http_error(exc)


@router.get("/risk-stops/{stop_id}", summary="PAY-MP-002-v2 risk stop")
def get_risk_stop(
    stop_id: uuid.UUID,
    accept: str | None = Header(None, alias="Accept"),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_v2(accept)
    try:
        return _v2_response(RiskBudgetService.risk_stop_projection(db, stop_id=stop_id, app_user_id=_app_user_id(current_user)))
    except RiskBudgetError as exc:
        return _risk_http_error(exc)


@router.get("/provider-resolutions/{resolution_id}", summary="PAY-MP-002-v2 Provider resolution")
def get_provider_resolution(
    resolution_id: uuid.UUID,
    accept: str | None = Header(None, alias="Accept"),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_v2(accept)
    try:
        return _v2_response(RiskBudgetService.provider_resolution_projection(db, resolution_id=resolution_id, app_user_id=_app_user_id(current_user)))
    except RiskBudgetError as exc:
        return _risk_http_error(exc)
