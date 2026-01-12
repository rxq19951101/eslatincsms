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
from app.database.base import get_db, tenant_id_context
from app.database.models import EndUser, WalletTransaction, ChargePoint
from app.core.id_generator import generate_order_id

logger = get_logger("ocpp_csms")

router = APIRouter()


async def get_current_end_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EndUser:
    user_id = current_user_payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    end_user = db.query(EndUser).filter(EndUser.id == user_id).first()
    if not end_user:
        raise HTTPException(status_code=404, detail="User not found")

    return end_user


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
    current_user_obj: EndUser = Depends(get_current_end_user),
) -> WalletBalanceResponse:
    # 余额权威字段：end_users.balance
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
    current_user_obj: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
) -> List[WalletTransactionResponse]:
    tenant_id = tenant_id_context.get()

    query = db.query(WalletTransaction).filter(WalletTransaction.end_user_id == current_user_obj.id)
    if tenant_id:
        query = query.filter(WalletTransaction.tenant_id == tenant_id)

    txs = query.order_by(WalletTransaction.created_at.desc()).offset(offset).limit(limit).all()

    # 批量取 charge_point 名称（可选）
    cp_ids = [t.charge_point_id for t in txs if t.charge_point_id]
    cp_name_map: Dict[str, str] = {}
    if cp_ids:
        cps = db.query(ChargePoint).filter(ChargePoint.id.in_(cp_ids)).all()
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
    current_user_obj: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
) -> WalletBalanceResponse:
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        # 正常情况下 tenant_middleware 会设置 tenant_id_context
        # 但为了避免认证阶段或特殊情况误伤，这里做一次兜底
        tenant_id = current_user_obj.tenant_id

    amount = Decimal(str(req.amount))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    # 更新余额（直接写入 EndUser.balance）
    current_balance = current_user_obj.balance or Decimal("0")
    try:
        new_balance = Decimal(str(current_balance)) + amount
    except Exception:
        new_balance = amount

    current_user_obj.balance = new_balance

    # 写入流水
    tx = WalletTransaction(
        id=generate_order_id(),  # 复用ID生成器，保证可读且唯一（无需严格语义）
        tenant_id=tenant_id,
        end_user_id=current_user_obj.id,
        charge_point_id=None,
        type="top_up",
        amount=amount,
        description=f"模拟充值 ${amount}",
    )

    db.add(tx)
    db.add(current_user_obj)
    db.commit()
    db.refresh(current_user_obj)

    logger.info(f"[APP API] top-up user={current_user_obj.id} amount={amount} new_balance={current_user_obj.balance}")

    return WalletBalanceResponse(balance=float(current_user_obj.balance or 0), currency="USD")

