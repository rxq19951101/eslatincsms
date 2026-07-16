#
# APP用户 - 钱包API（简化版）
# - 余额存放在 end_users.balance
# - 流水存放在 wallet_transactions
#

from typing import List, Dict, Any, Optional
from decimal import Decimal
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.api_logging import log_api_request, log_api_response, log_api_error, log_business_operation
from app.core.auth import get_current_user
from app.database.base import get_db, SuperSessionLocal
from app.database.models import AppUser, AppUserPaymentMethod, AppWalletTransaction, ChargePoint, Tenant
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
    currency: str = "COP"


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
    try:
        log_api_request(
            method="GET",
            path="/api/v1/app/wallet/balance",
            operation="get_wallet_balance",
            current_user=current_user_obj
        )
        
        # 余额权威字段：app_users.balance（平台统一钱包）
        bal = current_user_obj.balance or 0
        try:
            bal_float = float(bal)
        except Exception:
            bal_float = 0.0
        
        log_api_response(
            method="GET",
            path="/api/v1/app/wallet/balance",
            operation="get_wallet_balance",
            result="success",
            current_user=current_user_obj,
            details={"balance": bal_float}
        )
        
        return WalletBalanceResponse(balance=bal_float, currency="COP")
    except Exception as e:
        log_api_error(
            method="GET",
            path="/api/v1/app/wallet/balance",
            operation="get_wallet_balance",
            error=e,
            current_user=current_user_obj
        )
        raise


class SavedPaymentMethodItem(BaseModel):
    id: str
    provider: str
    last_four: Optional[str] = None
    payment_method_brand: Optional[str] = None
    is_default: bool = False


class SavedPaymentMethodsResponse(BaseModel):
    items: List[SavedPaymentMethodItem]
    hint: str = (
        "云端绑卡（Mercado Pago Customers / Checkout Pro）接入后可在此列出；"
        "Webhook 处理支付成功后可同步 card 信息至本表。"
    )


@router.get(
    "/saved-payment-methods",
    response_model=SavedPaymentMethodsResponse,
    summary="已保存支付方式（占位，供 MP 绑卡后回填）",
)
def list_saved_payment_methods(
    current_user_obj: AppUser = Depends(get_current_app_user),
) -> SavedPaymentMethodsResponse:
    """查询当前用户已保存卡。表结构已就绪，业务写入待 MP Customers + Webhook 扩展。"""
    db = SuperSessionLocal()
    try:
        rows = (
            db.query(AppUserPaymentMethod)
            .filter(AppUserPaymentMethod.app_user_id == current_user_obj.id)
            .order_by(AppUserPaymentMethod.is_default.desc(), AppUserPaymentMethod.created_at.desc())
            .all()
        )
        items = [
            SavedPaymentMethodItem(
                id=str(r.id),
                provider=r.provider,
                last_four=r.last_four,
                payment_method_brand=r.payment_method_brand,
                is_default=bool(r.is_default),
            )
            for r in rows
        ]
        return SavedPaymentMethodsResponse(items=items)
    finally:
        db.close()


@router.get("/transactions", response_model=List[WalletTransactionResponse], summary="获取钱包交易记录（终端用户）")
def list_wallet_transactions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> List[WalletTransactionResponse]:
    try:
        log_api_request(
            method="GET",
            path="/api/v1/app/wallet/transactions",
            operation="list_wallet_transactions",
            current_user=current_user_obj,
            params={"limit": limit, "offset": offset}
        )
        
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

        log_api_response(
            method="GET",
            path="/api/v1/app/wallet/transactions",
            operation="list_wallet_transactions",
            result="success",
            current_user=current_user_obj,
            details={"count": len(result), "limit": limit, "offset": offset}
        )

        return result
    except Exception as e:
        log_api_error(
            method="GET",
            path="/api/v1/app/wallet/transactions",
            operation="list_wallet_transactions",
            error=e,
            current_user=current_user_obj,
            params={"limit": limit, "offset": offset}
        )
        raise


@router.post("/top-up", response_model=WalletBalanceResponse, summary="模拟充值（仅开发/测试环境）")
def top_up(
    req: TopUpRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
) -> WalletBalanceResponse:
    allow_mock = os.getenv("ALLOW_MOCK_WALLET_TOP_UP", "false").lower() in ("true", "1", "yes")
    if not allow_mock:
        raise HTTPException(
            status_code=403,
            detail="Mock top-up is disabled. Use payment gateway to add funds.",
        )
    try:
        log_api_request(
            method="POST",
            path="/api/v1/app/wallet/top-up",
            operation="top_up",
            current_user=current_user_obj,
            params={"amount": req.amount}
        )
        
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

            log_business_operation(
                operation="钱包充值",
                entity_type="user",
                entity_id=str(app_user.id),
                result="success",
                current_user=current_user_obj,
                details={"amount": float(amount), "new_balance": float(app_user.balance or 0)}
            )

            log_api_response(
                method="POST",
                path="/api/v1/app/wallet/top-up",
                operation="top_up",
                result="success",
                current_user=current_user_obj,
                details={"amount": float(amount), "new_balance": float(app_user.balance or 0)}
            )

            return WalletBalanceResponse(balance=float(app_user.balance or 0), currency="USD")
        except HTTPException:
            raise
        except Exception as e:
            log_api_error(
                method="POST",
                path="/api/v1/app/wallet/top-up",
                operation="top_up",
                error=e,
                current_user=current_user_obj,
                params={"amount": req.amount}
            )
            raise
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="POST",
            path="/api/v1/app/wallet/top-up",
            operation="top_up",
            error=e,
            current_user=current_user_obj,
            params={"amount": req.amount}
        )
        raise


class UnpaidChargeResponse(BaseModel):
    session_id: int
    charge_point_id: str
    amount: float
    currency: str
    created_at: str
    payment_order_id: Optional[str] = None


@router.get("/unpaid-charges", response_model=List[UnpaidChargeResponse], summary="获取用户欠费列表")
def get_unpaid_charges(
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> List[UnpaidChargeResponse]:
    """获取用户未支付的充电订单列表"""
    try:
        log_api_request(
            method="GET",
            path="/api/v1/app/wallet/unpaid-charges",
            operation="get_unpaid_charges",
            current_user=current_user_obj
        )
        
        from app.database.models import ChargingSession
        
        sdb = SuperSessionLocal()
        try:
            user_id = str(current_user_obj.id)

            unpaid_sessions = (
                sdb.query(ChargingSession)
                .filter(
                    ChargingSession.user_id == user_id,
                    ChargingSession.payment_status == "unpaid",
                )
                .order_by(ChargingSession.created_at.desc())
                .all()
            )

            result = []
            for session in unpaid_sessions:
                amount = Decimal("0")

                result.append(
                    UnpaidChargeResponse(
                        session_id=session.id,
                        charge_point_id=session.charge_point_id,
                        amount=float(amount),
                        currency="COP",
                        created_at=session.created_at.isoformat() if session.created_at else "",
                        payment_order_id=str(session.payment_order_id) if session.payment_order_id else None,
                    )
                )

            log_api_response(
                method="GET",
                path="/api/v1/app/wallet/unpaid-charges",
                operation="get_unpaid_charges",
                result="success",
                current_user=current_user_obj,
                details={"count": len(result)}
            )

            return result
        except Exception as e:
            log_api_error(
                method="GET",
                path="/api/v1/app/wallet/unpaid-charges",
                operation="get_unpaid_charges",
                error=e,
                current_user=current_user_obj
            )
            raise
        finally:
            sdb.close()
    except Exception as e:
        log_api_error(
            method="GET",
            path="/api/v1/app/wallet/unpaid-charges",
            operation="get_unpaid_charges",
            error=e,
            current_user=current_user_obj
        )
        raise


class PayUnpaidChargeRequest(BaseModel):
    session_id: int = Field(..., description="充电会话ID")


@router.post("/pay-unpaid-charge", summary="补缴欠费（创建新的支付订单）")
def pay_unpaid_charge(
    req: PayUnpaidChargeRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """补缴欠费：为未支付的充电会话创建新的 Wompi 支付订单"""
    try:
        log_api_request(
            method="POST",
            path="/api/v1/app/wallet/pay-unpaid-charge",
            operation="pay_unpaid_charge",
            current_user=current_user_obj,
            params={"session_id": req.session_id}
        )
        
        from app.database.models import ChargingSession
        from app.api.v1.app.payments import CreatePaymentRequest
        
        sdb = SuperSessionLocal()
        try:
            user_id = str(current_user_obj.id)

            session = (
                sdb.query(ChargingSession)
                .filter(
                    ChargingSession.id == req.session_id,
                    ChargingSession.user_id == user_id,
                    ChargingSession.payment_status == "unpaid",
                )
                .first()
            )

            if not session:
                log_api_error(
                    method="POST",
                    path="/api/v1/app/wallet/pay-unpaid-charge",
                    operation="pay_unpaid_charge",
                    error=HTTPException(status_code=404, detail="Unpaid charging session not found"),
                    current_user=current_user_obj,
                    params={"session_id": req.session_id}
                )
                raise HTTPException(status_code=404, detail="Unpaid charging session not found")

            amount = Decimal("10000")

            payment_req = CreatePaymentRequest(
                type="charging",
                amount=float(amount),
                currency="COP",
                metadata={"session_id": session.id},
            )

            log_api_response(
                method="POST",
                path="/api/v1/app/wallet/pay-unpaid-charge",
                operation="pay_unpaid_charge",
                result="redirect_required",
                current_user=current_user_obj,
                details={"session_id": session.id, "estimated_amount": float(amount)}
            )

            return {
                "message": "Please use /api/v1/app/wallet/payments/create to create payment order",
                "session_id": session.id,
                "estimated_amount": float(amount),
            }
        except HTTPException:
            raise
        except Exception as e:
            log_api_error(
                method="POST",
                path="/api/v1/app/wallet/pay-unpaid-charge",
                operation="pay_unpaid_charge",
                error=e,
                current_user=current_user_obj,
                params={"session_id": req.session_id}
            )
            raise
        finally:
            sdb.close()
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="POST",
            path="/api/v1/app/wallet/pay-unpaid-charge",
            operation="pay_unpaid_charge",
            error=e,
            current_user=current_user_obj,
            params={"session_id": req.session_id}
        )
        raise

