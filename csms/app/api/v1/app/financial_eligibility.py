"""PAY-MP-002 financial eligibility and charging preflight API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.v1.app.payment_checkout import get_current_checkout_app_user
from app.api.validation import StrictRequestModel
from app.database.base import get_db
from app.database.models import AppUser
from app.services.asset_lifecycle_service import AssetNotOperationalError
from app.services.financial_eligibility import (
    ChargingAdmissionPreflight,
    FinancialEligibilityEvaluator,
)
from app.services.qr_service import InvalidQrTokenError


router = APIRouter()


class ChargingPreflightRequest(StrictRequestModel):
    qr_token: str = Field(..., min_length=1, max_length=128)
    settlement_method: Literal["wallet", "direct_card"] = "wallet"


@router.get("/financial-eligibility", summary="Read canonical financial eligibility")
def get_financial_eligibility(
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
):
    return FinancialEligibilityEvaluator.evaluate(
        db, app_user_id=current_user.id
    ).public_projection()


@router.post("/charging/preflight", summary="Evaluate charging admission preflight")
def charging_preflight(
    payload: ChargingPreflightRequest,
    current_user: AppUser = Depends(get_current_checkout_app_user),
    db: Session = Depends(get_db),
):
    try:
        result = ChargingAdmissionPreflight.evaluate(
            db,
            app_user_id=current_user.id,
            qr_token=payload.qr_token,
            settlement_method=payload.settlement_method,
        )
    except (InvalidQrTokenError, AssetNotOperationalError, ValueError) as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Charging resource not found."},
        ) from exc
    return result.public_projection()
