"""Frozen PAY-MP-002-v1 App support-case endpoints."""

from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.validation import StrictRequestModel
from app.api.v1.app.payment_checkout import get_current_checkout_app_user
from app.database.base import get_db
from app.database.models import AppUser
from app.services.support_cases import SupportCaseService, SupportError, project_support_case


router = APIRouter()


class SupportContext(StrictRequestModel):
    resource_type: Literal[
        "invoice", "session", "payment", "payment_order", "recovery_attempt",
        "refund", "refund_case", "chargeback", "chargeback_case",
    ]
    resource_id: UUID


class CreateSupportCaseRequest(StrictRequestModel):
    category: Literal[
        "payment_recovery", "refund_request", "chargeback_question",
        "charging_issue", "other",
    ]
    context: SupportContext
    description: Optional[str] = Field(None, max_length=4000)


def _error(exc: SupportError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)})


@router.get("/support-cases", summary="List current App user's support cases")
def list_support_cases(
    status: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50),
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return SupportCaseService().list_app_cases(
            db, app_user=current_user, status=status, cursor=cursor, limit=limit
        )
    except SupportError as exc:
        raise _error(exc) from exc


@router.post("/support-cases", status_code=201, summary="Create an App support case")
def create_support_case(
    request: CreateSupportCaseRequest,
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        case = SupportCaseService().create_case(
            db,
            app_user=current_user,
            category=request.category,
            resource_type=request.context.resource_type,
            resource_id=request.context.resource_id,
            description=request.description,
        )
        return project_support_case(db, case, user_visible_only=True, app_projection=True)
    except SupportError as exc:
        raise _error(exc) from exc


@router.get("/support-cases/{case_id}", summary="Get current App user's support case")
def get_support_case(
    case_id: UUID,
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        case = SupportCaseService().get_app_case(db, app_user=current_user, case_id=case_id)
        return project_support_case(db, case, user_visible_only=True, app_projection=True)
    except SupportError as exc:
        raise _error(exc) from exc
