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
from sqlalchemy.exc import IntegrityError

from app.core.api_logging import log_business_operation
from app.core.id_generator import generate_order_id
from app.core.logging_config import get_logger
from app.core.permissions import get_current_admin_user
from app.database.base import SuperSessionLocal, get_db, tenant_id_context
from app.database.models import AppUser, AppWalletTransaction, AuditLog, Tenant
from app.api.validation import StrictRequestModel

logger = get_logger("ocpp_csms")

router = APIRouter()


def require_platform_wallet_admin(admin=Depends(get_current_admin_user)):
    """App 用户钱包是平台级账务，暂只允许平台总管理员操作。"""
    if not admin.is_super_admin:
        raise HTTPException(status_code=403, detail="Platform wallet admin access required")
    return admin


class AppUserResponse(BaseModel):
    id: str
    email: str
    phone: Optional[str] = None
    full_name: Optional[str] = None
    balance: Decimal
    status: str
    has_unpaid_charges: bool = False
    email_verified: bool = False
    created_at: Optional[str] = None


class AdjustBalanceRequest(StrictRequestModel):
    """amount > 0 入账，amount < 0 扣减；调整后余额不得为负。"""
    amount: Decimal = Field(..., ne=0, max_digits=10, decimal_places=2, description="调整金额（可为负）")
    description: str = Field(..., min_length=1, max_length=500, description="调账原因")
    idempotency_key: str = Field(..., min_length=8, max_length=255, pattern=r"^[A-Za-z0-9._:-]+$")


class AdjustBalanceResponse(BaseModel):
    id: str
    balance: Decimal
    currency: str = "COP"
    transaction_id: str


@router.get("", response_model=List[AppUserResponse], summary="列出 App 用户")
def list_app_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, description="按邮箱/姓名模糊搜索"),
    _admin=Depends(require_platform_wallet_admin),
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
    admin=Depends(require_platform_wallet_admin),
    db: Session = Depends(get_db),
) -> AdjustBalanceResponse:
    sdb = db
    try:
        user = sdb.query(AppUser).filter(AppUser.id == user_id).with_for_update().first()
        if not user:
            raise HTTPException(status_code=404, detail="App user not found")

        existing = sdb.query(AppWalletTransaction).filter(
            AppWalletTransaction.app_user_id == user.id,
            AppWalletTransaction.idempotency_key == req.idempotency_key,
        ).first()
        if existing:
            return AdjustBalanceResponse(
                id=str(user.id),
                balance=Decimal(str(user.balance or 0)),
                transaction_id=existing.transaction_number,
            )

        delta = req.amount
        current = Decimal(str(user.balance or 0))
        new_balance = current + delta
        if new_balance < 0:
            raise HTTPException(
                status_code=422,
                detail=f"Insufficient balance: current={current}, delta={delta}",
            )

        operator_tenant_id = tenant_id_context.get()
        operator_tenant = sdb.query(Tenant).filter(Tenant.id == operator_tenant_id).first() if operator_tenant_id else None
        if not operator_tenant:
            raise HTTPException(status_code=403, detail="Tenant context required for wallet adjustment")

        user.balance = new_balance
        tx_type = "top_up" if delta > 0 else "charge"
        tx_id = generate_order_id()
        tx = AppWalletTransaction(
            transaction_number=tx_id,
            app_user_id=user.id,
            operator_tenant_id=operator_tenant.id,
            charge_point_id=None,
            type=tx_type,
            amount=delta,
            description=req.description,
            idempotency_key=req.idempotency_key,
            adjusted_by_admin_id=admin.id,
        )
        sdb.add(tx)
        sdb.add(user)
        sdb.add(AuditLog(
            tenant_id=operator_tenant.id,
            actor_id=admin.id,
            actor_type="admin",
            action="wallet.adjust_balance",
            resource_type="app_user",
            resource_id=str(user.id),
            before_data={"balance": str(current)},
            after_data={"balance": str(new_balance), "amount": str(delta), "description": req.description},
            audit_metadata={"transaction_id": tx_id, "idempotency_key": req.idempotency_key},
        ))
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
            balance=Decimal(str(user.balance or 0)),
            transaction_id=tx_id,
        )
    except HTTPException:
        sdb.rollback()
        raise
    except IntegrityError as e:
        sdb.rollback()
        existing = sdb.query(AppWalletTransaction).filter(
            AppWalletTransaction.app_user_id == user_id,
            AppWalletTransaction.idempotency_key == req.idempotency_key,
        ).first()
        if existing:
            user = sdb.query(AppUser).filter(AppUser.id == user_id).first()
            return AdjustBalanceResponse(id=str(user_id), balance=Decimal(str(user.balance or 0)), transaction_id=existing.transaction_number)
        logger.error(f"adjust_app_user_balance integrity error: {e}", exc_info=True)
        raise HTTPException(status_code=409, detail="Wallet adjustment conflict")
    except Exception as e:
        sdb.rollback()
        logger.error(f"adjust_app_user_balance failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
