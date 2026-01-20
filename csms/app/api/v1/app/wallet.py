#
# APP用户 - 钱包API（简化版）
# - 余额存放在 end_users.balance
# - 流水存放在 wallet_transactions
#

from typing import List, Dict, Any, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.auth import get_current_user
from app.database.base import get_db, SuperSessionLocal
from app.database.models import AppUser, AppWalletTransaction, ChargePoint, Tenant
from app.core.id_generator import generate_order_id

logger = get_logger("ocpp_csms")

router = APIRouter()


async def get_current_app_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppUser:
    user_id = current_user_payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    app_user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not app_user:
        raise HTTPException(status_code=404, detail="User not found")

    return app_user


class WalletBalanceResponse(BaseModel):
    balance: float
    currency: str = "USD"


class WalletTransactionResponse(BaseModel):
    id: str
    type: str
    amount: float
    description: Optional[str] = None
    created_at: str
    charge_point_name: Optional[str] = None


class TopUpRequest(BaseModel):
    amount: float = Field(..., gt=0, description="充值金额（正数）")


@router.get("/balance", response_model=WalletBalanceResponse, summary="获取钱包余额（终端用户）")
def get_wallet_balance(
    current_user_obj: AppUser = Depends(get_current_app_user),
) -> WalletBalanceResponse:
    # 余额权威字段：app_users.balance（平台统一钱包）
    bal = current_user_obj.balance or 0
    try:
        bal_float = float(bal)
    except Exception:
        bal_float = 0.0
    return WalletBalanceResponse(balance=bal_float, currency="USD")


@router.get("/transactions", response_model=List[WalletTransactionResponse], summary="获取钱包交易记录（终端用户）")
def list_wallet_transactions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> List[WalletTransactionResponse]:
    query = db.query(AppWalletTransaction).filter(AppWalletTransaction.app_user_id == current_user_obj.id)
    txs = query.order_by(AppWalletTransaction.created_at.desc()).offset(offset).limit(limit).all()

    # 批量取 charge_point 名称（可选）
    cp_ids = [t.charge_point_id for t in txs if t.charge_point_id]
    cp_name_map: Dict[str, str] = {}
    if cp_ids:
        # charge_points 启用了 RLS，平台用户这里用 super session 读一下用于展示
        sdb = SuperSessionLocal()
        try:
            cps = sdb.query(ChargePoint).filter(ChargePoint.id.in_(cp_ids)).all()
        finally:
            sdb.close()
        for cp in cps:
            # 站点名称在 APP chargers 返回的是 site_name，这里优先用 charge_point_id 作为兜底展示
            cp_name_map[cp.id] = cp.id

    result: List[WalletTransactionResponse] = []
    for t in txs:
        result.append(
            WalletTransactionResponse(
                id=t.id,
                type=t.type,
                amount=float(t.amount) if t.amount is not None else 0.0,
                description=t.description,
                created_at=t.created_at.isoformat() if t.created_at else "",
                charge_point_name=cp_name_map.get(t.charge_point_id) if t.charge_point_id else None,
            )
        )
    return result


@router.post("/top-up", response_model=WalletBalanceResponse, summary="模拟充值（终端用户）")
def top_up(
    req: TopUpRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
) -> WalletBalanceResponse:
    # 平台钱包充值：不依赖 tenant_id_context
    db = SuperSessionLocal()
    try:
        # 兜底：选择最早创建的 tenant 作为 operator_tenant_id（测试环境足够）
        operator_tenant = db.query(Tenant).order_by(Tenant.created_at.asc()).first()
        if not operator_tenant:
            raise HTTPException(status_code=500, detail="No tenant found")
        amount = Decimal(str(req.amount))
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Invalid amount")

        app_user = db.query(AppUser).filter(AppUser.id == current_user_obj.id).first()
        if not app_user:
            raise HTTPException(status_code=404, detail="User not found")

        # 更新余额（直接写入 AppUser.balance）
        current_balance = app_user.balance or Decimal("0")
        try:
            new_balance = Decimal(str(current_balance)) + amount
        except Exception:
            new_balance = amount

        app_user.balance = new_balance

        # 写入流水
        tx = AppWalletTransaction(
            id=generate_order_id(),  # 复用ID生成器，保证可读且唯一（无需严格语义）
            app_user_id=app_user.id,
            operator_tenant_id=operator_tenant.id,
            charge_point_id=None,
            type="top_up",
            amount=amount,
            description=f"模拟充值 ${amount}",
        )

        db.add(tx)
        db.add(app_user)
        db.commit()
        db.refresh(app_user)

        logger.info(f"[APP API] top-up user={app_user.id} amount={amount} new_balance={app_user.balance}")

        return WalletBalanceResponse(balance=float(app_user.balance or 0), currency="USD")
    finally:
        db.close()

