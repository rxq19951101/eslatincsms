#
# App 终端用户管理（平台钱包）
# 用于审核/内测：列表用户、调整余额并写入 wallet 流水
#

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.api_logging import log_business_operation
from app.core.id_generator import generate_order_id
from app.core.logging_config import get_logger
from app.core.permissions import get_current_admin_user
from app.database.base import SuperSessionLocal, get_db
from app.database.models import AppUser, AppWalletTransaction, Tenant

logger = get_logger("ocpp_csms")

router = APIRouter()


class AppUserResponse(BaseModel):
    id: str
    email: str
    phone: Optional[str] = None
    full_name: Optional[str] = None
    balance: float
    status: str
    has_unpaid_charges: bool = False
    email_verified: bool = False
    created_at: Optional[str] = None


class AdjustBalanceRequest(BaseModel):
    """amount > 0 入账，amount < 0 扣减；调整后余额不得为负。"""
    amount: float = Field(..., description="调整金额（可为负）")
    description: Optional[str] = Field(None, description="流水备注")


class AdjustBalanceResponse(BaseModel):
    id: str
    balance: float
    currency: str = "COP"
    transaction_id: str


@router.get("", response_model=List[AppUserResponse], summary="列出 App 用户")
def list_app_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, description="按邮箱/姓名模糊搜索"),
    _admin=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> List[AppUserResponse]:
    sdb = SuperSessionLocal()
    try:
        query = sdb.query(AppUser).filter(AppUser.status != "deleted")
        if q and q.strip():
            like = f"%{q.strip()}%"
            query = query.filter(
                (AppUser.email.ilike(like)) | (AppUser.full_name.ilike(like))
            )
        rows = (
            query.order_by(AppUser.created_at.desc()).offset(offset).limit(limit).all()
        )
        return [
            AppUserResponse(
                id=str(u.id),
                email=u.email,
                phone=u.phone,
                full_name=u.full_name,
                balance=float(u.balance or 0),
                status=u.status,
                has_unpaid_charges=bool(u.has_unpaid_charges),
                email_verified=bool(u.email_verified),
                created_at=u.created_at.isoformat() if u.created_at else None,
            )
            for u in rows
        ]
    finally:
        sdb.close()


@router.post(
    "/{user_id}/adjust-balance",
    response_model=AdjustBalanceResponse,
    summary="调整 App 用户钱包余额",
)
def adjust_app_user_balance(
    user_id: UUID,
    req: AdjustBalanceRequest,
    admin=Depends(get_current_admin_user),
) -> AdjustBalanceResponse:
    if req.amount == 0:
        raise HTTPException(status_code=400, detail="amount must not be zero")

    sdb = SuperSessionLocal()
    try:
        user = sdb.query(AppUser).filter(AppUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="App user not found")

        delta = Decimal(str(req.amount))
        current = Decimal(str(user.balance or 0))
        new_balance = current + delta
        if new_balance < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance: current={current}, delta={delta}",
            )

        operator_tenant = sdb.query(Tenant).order_by(Tenant.created_at.asc()).first()
        if not operator_tenant:
            raise HTTPException(status_code=500, detail="No tenant found")

        user.balance = new_balance
        tx_type = "top_up" if delta > 0 else "charge"
        desc = req.description or (
            f"Admin credit ({admin.username})"
            if delta > 0
            else f"Admin debit ({admin.username})"
        )
        tx_id = generate_order_id()
        tx = AppWalletTransaction(
            id=tx_id,
            app_user_id=user.id,
            operator_tenant_id=operator_tenant.id,
            charge_point_id=None,
            type=tx_type,
            amount=delta,
            description=desc,
        )
        sdb.add(tx)
        sdb.add(user)
        sdb.commit()
        sdb.refresh(user)

        log_business_operation(
            operation="admin_adjust_app_user_balance",
            entity_type="app_user",
            entity_id=str(user.id),
            result="success",
            current_user=admin,
            details={
                "amount": float(delta),
                "new_balance": float(user.balance or 0),
                "transaction_id": tx_id,
            },
        )

        return AdjustBalanceResponse(
            id=str(user.id),
            balance=float(user.balance or 0),
            transaction_id=tx_id,
        )
    except HTTPException:
        sdb.rollback()
        raise
    except Exception as e:
        sdb.rollback()
        logger.error(f"adjust_app_user_balance failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        sdb.close()
