"""PAY-MP-002 Admin RefundCase and ChargebackCase contract."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.database.base import get_db
from app.database.models import AdminUser
from app.services.refund_cases import RefundCaseError, RefundCaseService


router = APIRouter()


class RefundTarget(BaseModel):
    resource_type: str
    resource_id: UUID


class RefundCaseCreateRequest(BaseModel):
    target: RefundTarget
    requested_amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    reason_code: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


class RefundDecisionRequest(BaseModel):
    decision: str
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


def _error(exc: RefundCaseError) -> HTTPException:
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


def _validate_limit(limit: int) -> int:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "limit must be between 1 and 100"}})
    return limit


def _tenant_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "tenant_scope is invalid"}}) from exc


@router.get("/refund-cases", summary="List RefundCases")
def list_refund_cases(
    status: str | None = Query(None),
    tenant_scope: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(50),
    admin: AdminUser = Depends(require_permission("payment.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return RefundCaseService().list_refund_cases(
            db, admin=admin, status=status, tenant_id=_tenant_uuid(tenant_scope),
            cursor=cursor, limit=_validate_limit(limit), current_actor_id=admin.id,
        )
    except RefundCaseError as exc:
        raise _error(exc) from exc


@router.post("/refund-cases", status_code=201, summary="Create RefundCase")
def create_refund_case(
    request: RefundCaseCreateRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    admin: AdminUser = Depends(require_permission("refund.request")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Idempotency-Key is required"}})
    if request.target.resource_type != "payment_allocation":
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Only payment_allocation targets are supported"}})
    try:
        service = RefundCaseService()
        case = service.create_refund_case(
            db, actor=admin, allocation_id=request.target.resource_id,
            requested_amount=request.requested_amount, currency=request.currency.upper(),
            reason_code=request.reason_code, reason=request.reason,
            idempotency_key=idempotency_key,
        )
        return service.project_refund(db, case, current_actor_id=admin.id)
    except RefundCaseError as exc:
        raise _error(exc) from exc


@router.get("/refund-cases/{case_id}", summary="Get RefundCase")
def get_refund_case(
    case_id: UUID,
    admin: AdminUser = Depends(require_permission("payment.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        service = RefundCaseService()
        case = service.get_refund_case(db, admin=admin, case_id=case_id, current_actor_id=admin.id)
        return service.project_refund(db, case, current_actor_id=admin.id)
    except RefundCaseError as exc:
        raise _error(exc) from exc


@router.post("/refund-cases/{case_id}/decisions", summary="Approve or reject RefundCase")
def decide_refund_case(
    case_id: UUID,
    request: RefundDecisionRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    admin: AdminUser = Depends(require_permission("refund.approve")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail={"error": {"code": "REQUEST_INVALID", "message": "Idempotency-Key is required"}})
    try:
        service = RefundCaseService()
        case = service.approve_refund_case(
            db, actor=admin, case_id=case_id, decision=request.decision,
            expected_version=request.expected_version, reason=request.reason,
            idempotency_key=idempotency_key,
        )
        return service.project_refund(db, case, current_actor_id=admin.id)
    except RefundCaseError as exc:
        raise _error(exc) from exc


@router.get("/chargeback-cases", summary="List ChargebackCases")
def list_chargeback_cases(
    status: str | None = Query(None),
    deadline_from: str | None = Query(None),
    deadline_to: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(50),
    admin: AdminUser = Depends(require_permission("chargeback.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return RefundCaseService().list_chargeback_cases(
            db, admin=admin, status=status, deadline_from=deadline_from,
            deadline_to=deadline_to, cursor=cursor, limit=_validate_limit(limit),
        )
    except RefundCaseError as exc:
        raise _error(exc) from exc


@router.get("/chargeback-cases/{case_id}", summary="Get ChargebackCase")
def get_chargeback_case(
    case_id: UUID,
    admin: AdminUser = Depends(require_permission("chargeback.read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        service = RefundCaseService()
        case = service.get_chargeback_case(db, admin=admin, case_id=case_id)
        return service.project_chargeback(db, case)
    except RefundCaseError as exc:
        raise _error(exc) from exc
