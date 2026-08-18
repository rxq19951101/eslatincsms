#
# APP用户 - 钱包API（简化版）
# - 余额存放在 app_users.balance
# - 流水存放在 wallet_transactions
#

from typing import List, Dict, Any, Optional
from decimal import Decimal
from uuid import UUID
import hashlib
import os
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.api_logging import log_api_request, log_api_response, log_api_error, log_business_operation
from app.core.auth import get_current_user
from app.database.base import get_db, SuperSessionLocal
from app.database.models import (
    AppUser,
    AppWalletTransaction,
    ChargePoint,
    ChargingSession,
    Invoice,
    Site,
    Tenant,
)
from app.core.id_generator import generate_order_id
from app.services.billing_service import BillingService

logger = get_logger("ocpp_csms")

router = APIRouter()


async def get_current_app_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppUser:
    user_id = current_user_payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        user_id = UUID(str(user_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    app_user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not app_user:
        raise HTTPException(status_code=404, detail="User not found")

    return app_user


class WalletBalanceResponse(BaseModel):
    balance: Decimal
    currency: str = "COP"


class WalletTransactionResponse(BaseModel):
    id: str
    type: str
    reference: str
    amount: Decimal
    description: Optional[str] = None
    created_at: str
    charge_point_name: Optional[str] = None
    ocpp_identity: Optional[str] = None
    charging_session_id: Optional[str] = None


_UUID_TEXT = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
)


def _public_wallet_reference(transaction: AppWalletTransaction) -> str:
    """Expose a stable business reference without leaking embedded DB UUIDs."""
    candidate = (transaction.transaction_number or "").strip()
    if candidate and not _UUID_TEXT.search(candidate):
        return candidate
    digest_source = candidate or str(transaction.id)
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:12].upper()
    return f"WLT-{digest}"


def get_app_wallet_db():
    db = SuperSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TopUpRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2, description="充值金额（正数）")
    idempotency_key: str = Field(..., min_length=8, description="充值幂等键")


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


@router.get("/transactions", response_model=List[WalletTransactionResponse], summary="获取钱包交易记录（终端用户）")
def list_wallet_transactions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_app_wallet_db),
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

        invoice_ids = [t.invoice_id for t in txs if t.type == "charge" and t.invoice_id]
        owned_session_by_invoice: Dict[UUID, UUID] = {}
        if invoice_ids:
            id_tag = f"APP{str(current_user_obj.id).replace('-', '')[:17]}"
            owned_invoices = (
                db.query(Invoice.id, Invoice.session_id)
                .join(ChargingSession, Invoice.session_id == ChargingSession.id)
                .filter(
                    Invoice.id.in_(invoice_ids),
                    or_(
                        ChargingSession.app_user_id == current_user_obj.id,
                        ChargingSession.user_id == str(current_user_obj.id),
                        ChargingSession.id_tag == id_tag,
                    ),
                )
                .all()
            )
            owned_session_by_invoice = {
                invoice_id: session_id for invoice_id, session_id in owned_invoices
            }

        # 批量取 charge_point 名称（可选）
        cp_ids = [t.charge_point_id for t in txs if t.charge_point_id]
        cp_name_map: Dict[UUID, Optional[str]] = {}
        cp_identity_map: Dict[UUID, str] = {}
        if cp_ids:
            # charge_points 启用了 RLS，平台用户这里用 super session 读一下用于展示
            sdb = SuperSessionLocal()
            try:
                charge_point_names = (
                    sdb.query(ChargePoint.id, ChargePoint.ocpp_identity, Site.name)
                    .outerjoin(Site, ChargePoint.site_id == Site.id)
                    .filter(ChargePoint.id.in_(cp_ids))
                    .all()
                )
            finally:
                sdb.close()
            for charge_point_id, ocpp_identity, site_name in charge_point_names:
                cp_name_map[charge_point_id] = site_name
                cp_identity_map[charge_point_id] = ocpp_identity

        result: List[WalletTransactionResponse] = []
        for t in txs:
            result.append(
                WalletTransactionResponse(
                    id=str(t.id),
                    type=t.type,
                    reference=_public_wallet_reference(t),
                    amount=Decimal(str(t.amount)) if t.amount is not None else Decimal("0"),
                    description=t.description,
                    created_at=t.created_at.isoformat() if t.created_at else "",
                    charge_point_name=cp_name_map.get(t.charge_point_id) if t.charge_point_id else None,
                    ocpp_identity=cp_identity_map.get(t.charge_point_id) if t.charge_point_id else None,
                    charging_session_id=(
                        str(owned_session_by_invoice[t.invoice_id])
                        if t.type == "charge" and t.invoice_id in owned_session_by_invoice
                        else None
                    ),
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

            ledger_id = f"mock_topup_{app_user.id}_{req.idempotency_key}"
            existing_tx = db.query(AppWalletTransaction).filter(
                AppWalletTransaction.transaction_number == ledger_id
            ).first()
            if existing_tx:
                return WalletBalanceResponse(balance=Decimal(str(app_user.balance or 0)), currency="COP")

            app_user = db.query(AppUser).filter(AppUser.id == app_user.id).with_for_update().one()
            app_user.balance = Decimal(str(app_user.balance or 0)) + amount
            tx = AppWalletTransaction(
                transaction_number=ledger_id,
                app_user_id=app_user.id,
                operator_tenant_id=operator_tenant.id,
                charge_point_id=None,
                type="top_up",
                amount=amount,
                description="Wallet top-up",
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

            return WalletBalanceResponse(balance=float(app_user.balance or 0), currency="COP")
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
    session_id: str
    charge_point_id: str
    amount: Decimal
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
                    ChargingSession.app_user_id == current_user_obj.id,
                    ChargingSession.payment_status == "unpaid",
                )
                .order_by(ChargingSession.created_at.desc())
                .all()
            )

            result = []
            for session in unpaid_sessions:
                invoice = (
                    sdb.query(Invoice)
                    .filter(
                        Invoice.session_id == session.id,
                        Invoice.tenant_id == session.tenant_id,
                        Invoice.status == "pending",
                    )
                    .first()
                )
                if invoice is None or Decimal(str(invoice.total_amount)) <= Decimal("0.00"):
                    continue
                amount = Decimal(str(invoice.total_amount))

                result.append(
                    UnpaidChargeResponse(
                        session_id=str(session.id),
                        charge_point_id=str(session.charge_point_id),
                        amount=amount,
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
    session_id: UUID = Field(..., description="内部充电会话 UUID")


@router.post("/pay-unpaid-charge", summary="补缴欠费（创建新的支付订单）")
def pay_unpaid_charge(
    req: PayUnpaidChargeRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """Use the wallet to atomically settle the current Invoice fact."""
    try:
        log_api_request(
            method="POST",
            path="/api/v1/app/wallet/pay-unpaid-charge",
            operation="pay_unpaid_charge",
            current_user=current_user_obj,
            params={"session_id": req.session_id}
        )
        
        sdb = SuperSessionLocal()
        try:
            result = BillingService.pay_unpaid_charge(
                sdb,
                app_user_id=current_user_obj.id,
                session_id=req.session_id,
                idempotency_key=idempotency_key,
            )
            if result.payment_status == "unpaid":
                raise HTTPException(
                    status_code=402,
                    detail={
                        "code": "INSUFFICIENT_WALLET_BALANCE",
                        "message": "Wallet balance is insufficient to pay this charging invoice.",
                    },
                )
            return {
                "session_id": str(req.session_id),
                "invoice_id": result.invoice_id,
                "payment_status": result.payment_status,
                "charged_amount": format(result.charged_amount, ".2f"),
                "currency": result.currency,
                "balance": format(result.balance or Decimal("0.00"), ".2f"),
                "already_settled": result.already_settled,
            }
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Unpaid charging session not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
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
