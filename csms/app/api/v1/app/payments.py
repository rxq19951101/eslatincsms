#
# App Provider Webhook adapters
#
# App 业务支付统一由 payment_checkout.py 的 Checkout Session 契约承载。
# 本模块只向公共路由注册 Provider-specific Webhook；文件前半段的历史
# create/status handlers 保留为未注册代码，避免把旧接口继续暴露给 App。
#

import hashlib
import hmac
import json
import os
from typing import Dict, Any, Literal, Optional
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.api_logging import log_api_request, log_api_response, log_api_error, log_business_operation
from app.core.auth import get_current_user
from app.database.base import get_db, SuperSessionLocal
from app.database.models import (
    AppUser, PaymentOrder, PaymentWebhookEvent, 
    ChargingSession, ChargePoint, AppWalletTransaction, Tenant
)
from app.services.wompi_service import get_wompi_service
from app.services.mercadopago_service import get_mercadopago_service
from app.services.payment_providers.base import (
    CreatePaymentCommand,
    PaymentCapabilityResult,
    PaymentProviderError,
    ProviderCapabilityError,
    ProviderPaymentStatus,
)
from app.services.payment_providers.registry import get_payment_provider_registry
from app.services.payment_reconciliation import (
    PaymentReconciliationError,
    PaymentReconciliationService,
)
from app.services.refund_cases import RefundCaseService
from app.services.payment_providers.merchant_context import (
    MerchantContextError,
    PaymentPurpose,
    PlatformMerchantAccountResolver,
)
from app.services.runtime_rail_control import RailError, RuntimeRailControlService
from app.domain.payment import transition_status
from app.core.id_generator import generate_order_id
from app.core.config import get_settings
from app.api.validation import StrictRequestModel
from email_validator import validate_email, EmailNotValidError

logger = get_logger("ocpp_csms")

router = APIRouter()

PAYMENT_DISABLED_DETAIL = (
    "In-app payment is not enabled. Wallet balance is managed by the operator. "
    "Contact support or use an account with prepaid balance."
)


def _require_payment_rails_enabled() -> None:
    if not get_settings().payment_rails_enabled:
        raise HTTPException(status_code=403, detail=PAYMENT_DISABLED_DETAIL)


async def get_current_app_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppUser:
    """获取当前 App 用户"""
    user_id = current_user_payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    app_user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not app_user:
        raise HTTPException(status_code=404, detail="User not found")

    return app_user


# ==================== 请求/响应模型 ====================

class CreatePaymentRequest(BaseModel):
    """Wompi 支付请求（保留兼容）"""
    type: str = Field(..., description="订单类型：top_up 或 charging")
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2, description="支付金额")
    currency: str = Field("COP", description="货币（默认 COP）")
    idempotency_key: Optional[str] = Field(None, description="支付创建幂等键")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据（充电支付时需要 session_id）")


class CreateMercadoPagoPaymentRequest(BaseModel):
    """Mercado Pago 支付请求"""
    type: str = Field(..., description="订单类型：top_up 或 charging")
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2, description="支付金额")
    currency: str = Field("COP", description="货币（默认 COP）")
    token: str = Field(..., description="前端获取的 card token")
    email: str = Field(..., description="用户邮箱（MP 强制要求）")
    payment_method_id: str = Field(..., description="支付方式（如 'visa', 'master'）")
    idempotency_key: str = Field(..., description="幂等性键（UUID v4）")
    device_id: Optional[str] = Field(None, description="设备指纹（可选，防止风控）")
    description: Optional[str] = Field(None, description="支付描述（可选，默认根据订单类型生成）")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据（充电支付时需要 session_id）")


class WompiPaymentData(BaseModel):
    public_key: str
    reference: str
    integrity_signature: str
    amount_in_cents: int
    currency: str
    redirect_url: str


class CreatePaymentResponse(BaseModel):
    order_id: str
    reference: str
    payment_data: WompiPaymentData
    checkout_url: Optional[str] = None


class MercadoPagoPaymentResponse(BaseModel):
    """Mercado Pago 支付响应"""
    order_id: str
    payment_id: str
    status: str
    external_reference: str
    amount: Decimal
    currency: str


class PaymentStatusResponse(BaseModel):
    order_id: str
    purpose: str = ""
    status: str
    status_detail: Optional[str] = None
    wompi_transaction_id: Optional[str] = None
    mercadopago_payment_id: Optional[str] = None
    amount: Decimal
    currency: str
    invoice_id: Optional[str] = None
    session_id: Optional[str] = None
    next_action: Optional[Dict[str, str]] = None
    paid_at: Optional[str] = None
    expires_at: str
    is_expired: bool


class SimPaymentWebhookRequest(StrictRequestModel):
    """Narrow development/test webhook payload used by the scenario runner."""

    event_id: str = Field(..., min_length=1, max_length=255)
    provider: Literal["fake"]
    status: Literal["approved", "pending", "rejected", "timeout"]
    session_id: Optional[UUID] = None
    payment_order_id: Optional[UUID] = None


# ==================== API 端点 ====================

TERMINAL_STATES = {"approved", "declined", "voided", "error", "refunded"}


def _validate_common_request(order_type: str, metadata: Optional[Dict[str, Any]]) -> None:
    if order_type not in ["top_up", "charging"]:
        raise HTTPException(status_code=400, detail="Invalid order type. Must be 'top_up' or 'charging'")
    if order_type == "charging" and (not metadata or "session_id" not in metadata):
        raise HTTPException(status_code=400, detail="session_id is required for charging payment")


def _apply_approved_business_logic(
    db: Session,
    order: PaymentOrder,
    app_user: AppUser,
    provider_display_name: str,
    provider_ref: Optional[str] = None,
) -> None:
    if order.type == "top_up":
        app_user = db.query(AppUser).filter(AppUser.id == app_user.id).with_for_update().one()
        ledger_id = f"payment_topup_{order.id}"
        ledger = db.query(AppWalletTransaction).filter(
            AppWalletTransaction.transaction_number == ledger_id
        ).first()
        if ledger:
            return
        current_balance = Decimal(str(app_user.balance or 0))
        app_user.balance = current_balance + Decimal(str(order.amount))
        operator_tenant = db.query(Tenant).order_by(Tenant.created_at.asc()).first()
        if not operator_tenant:
            raise ValueError("No operator tenant available for wallet ledger")
        tx = AppWalletTransaction(
            transaction_number=ledger_id,
            app_user_id=app_user.id,
            payment_order_id=order.id,
            operator_tenant_id=operator_tenant.id,
            charge_point_id=None,
            type="top_up",
            amount=Decimal(str(order.amount)),
            description="Wallet top-up",
        )
        db.add(tx)
        logger.info(
            f"[APP API] {provider_display_name} top-up completed: user={app_user.id}, "
            f"amount={order.amount}, new_balance={app_user.balance}"
        )
    elif order.type == "charging":
        session_id = order.order_metadata.get("session_id") if order.order_metadata else None
        if session_id:
            session = db.query(ChargingSession).filter(ChargingSession.id == session_id).first()
            if session:
                session.payment_status = "paid"
                session.payment_order_id = order.id
                logger.info(
                    f"[APP API] {provider_display_name} charging payment completed: session={session_id}, "
                    f"order={order.id}"
                )


def _apply_refund_ledger(db: Session, order: PaymentOrder, amount: Decimal) -> None:
    """Legacy helper kept safe for callers outside the BE-7 service."""
    amount = Decimal(str(amount))
    if amount <= 0 or amount > Decimal(str(order.amount)):
        raise ValueError("Invalid refund amount")
    user = db.query(AppUser).filter(AppUser.id == order.app_user_id).with_for_update().one()
    balance = Decimal(str(user.balance or 0))
    if balance < amount:
        raise ValueError("Wallet balance is insufficient for refund")
    ledger_id = f"payment_refund_{order.id}"
    if db.query(AppWalletTransaction).filter(
        AppWalletTransaction.transaction_number == ledger_id
    ).first():
        return
    user.balance = balance - amount
    tenant = db.query(Tenant).order_by(Tenant.created_at.asc()).first()
    if tenant:
        db.add(AppWalletTransaction(
            transaction_number=ledger_id,
            app_user_id=user.id,
            payment_order_id=order.id,
            operator_tenant_id=tenant.id,
            charge_point_id=None,
            type="charge",
            amount=-amount,
            description="Payment refund",
        ))


def build_sim_webhook_signature(payload: Dict[str, Any], secret: str) -> str:
    """Return the canonical HMAC-SHA256 signature for a SIM webhook payload."""
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _sim_webhook_invariants(
    db: Session,
    order: PaymentOrder,
    event_id: str,
    *,
    replayed: bool,
) -> Dict[str, Any]:
    session = db.query(ChargingSession).filter(
        ChargingSession.payment_order_id == order.id
    ).first()
    event = db.query(PaymentWebhookEvent).filter(
        PaymentWebhookEvent.payment_provider == "fake",
        PaymentWebhookEvent.payment_provider_id == str(order.id),
        PaymentWebhookEvent.event_id == event_id,
    ).one()
    return {
        "provider": "fake",
        "status": (event.payload or {}).get("status"),
        "order_status": order.status,
        "event_id": event_id,
        "payment_order_id": str(order.id),
        "session_id": str(session.id) if session else None,
        "session_payment_status": session.payment_status if session else None,
        "wallet_balance": str(order.app_user.balance),
        "webhook_event_count": 1,
        "ledger_entry_count": db.query(AppWalletTransaction).filter(
            AppWalletTransaction.payment_order_id == order.id
        ).count(),
        "replayed": replayed,
    }


def _create_order_from_command(
    db: Session,
    current_user_obj: AppUser,
    command: CreatePaymentCommand,
) -> tuple[PaymentOrder, Dict[str, Any]]:
    # 必须与 db 为同一 Session 加载用户；否则 create-mp 等使用 SuperSessionLocal 时，
    # 余额改在 get_db 的 AppUser 上，commit 却只提交 super 连接，导致流水有记录、balance 仍为 0。
    app_user = db.query(AppUser).filter(AppUser.id == current_user_obj.id).first()
    if not app_user:
        raise ValueError("App user not found")

    if command.idempotency_key:
        existing = db.query(PaymentOrder).filter(
            PaymentOrder.app_user_id == app_user.id,
            PaymentOrder.idempotency_key == command.idempotency_key,
        ).first()
        if existing:
            checkout = {}
            if existing.payment_provider == "wompi" and existing.reference:
                checkout = get_wompi_service().create_payment_checkout_data(
                    existing.reference, Decimal(str(existing.amount)), existing.currency, existing.redirect_url
                )
            return existing, checkout

    _validate_common_request(command.order_type, command.metadata)
    merchant_context = None
    if command.provider == "mercadopago":
        purpose = (
            PaymentPurpose.WALLET_TOP_UP
            if command.order_type == "top_up"
            else PaymentPurpose.CHARGING_DIRECT
        )
        tenant_id = None
        if command.metadata and command.metadata.get("operator_tenant_id"):
            tenant_id = UUID(str(command.metadata["operator_tenant_id"]))
        elif command.order_type == "charging" and command.metadata:
            session = db.query(ChargingSession).filter(
                ChargingSession.id == command.metadata.get("session_id")
            ).first()
            tenant_id = session.tenant_id if session is not None else None
        try:
            merchant_context = PlatformMerchantAccountResolver().resolve(
                operator_tenant_id=tenant_id,
                payment_purpose=purpose,
            )
        except (MerchantContextError, ValueError) as exc:
            raise ValueError("Unable to resolve payment merchant") from exc
        command.metadata = dict(command.metadata or {})
        command.metadata.setdefault("payment_purpose", purpose.value)
        command.metadata.setdefault(
            "operator_tenant_id", str(tenant_id) if tenant_id is not None else None
        )
        command.metadata.setdefault("merchant", merchant_context.safe_snapshot())
        site_id = None
        if command.metadata.get("session_id"):
            session = db.query(ChargingSession).filter(
                ChargingSession.id == command.metadata.get("session_id"),
                ChargingSession.tenant_id == tenant_id,
            ).first()
            if session is not None:
                site_id = db.query(ChargePoint.site_id).filter(
                    ChargePoint.id == session.charge_point_id,
                    ChargePoint.tenant_id == tenant_id,
                ).scalar()
        RuntimeRailControlService.require_payment_creation_open(
            db, provider=command.provider, tenant_id=tenant_id, site_id=site_id
        )
    registry = get_payment_provider_registry()
    provider = registry.get(command.provider)
    if merchant_context is None:
        result = provider.create_payment(command)
    else:
        result = provider.create_payment(command, merchant_context=merchant_context)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    payment_deadline_at = None
    if command.order_type == "charging":
        payment_deadline_at = datetime.now(timezone.utc) + timedelta(minutes=60)

    order = PaymentOrder(
        app_user_id=app_user.id,
        type=command.order_type,
        amount=command.amount,
        currency=command.currency.upper(),
        payment_provider=command.provider,
        idempotency_key=command.idempotency_key,
        reference=result.provider_order_ref if command.provider == "wompi" else None,
        integrity_signature=(result.checkout_payload or {}).get("integrity_signature") if command.provider == "wompi" else None,
        external_reference=result.provider_order_ref if command.provider == "mercadopago" else None,
        mercadopago_payment_id=result.provider_payment_id if command.provider == "mercadopago" else None,
        status=result.status,
        redirect_url=result.redirect_url,
        expires_at=expires_at,
        payment_deadline_at=payment_deadline_at,
        order_metadata=command.metadata or {},
    )
    if result.status == "approved":
        order.paid_at = datetime.now(timezone.utc)

    db.add(order)
    db.flush()

    if result.status == "approved":
        provider_display = "MercadoPago" if command.provider == "mercadopago" else "Wompi"
        _apply_approved_business_logic(
            db=db,
            order=order,
            app_user=app_user,
            provider_display_name=provider_display,
            provider_ref=result.provider_order_ref,
        )

    db.commit()
    db.refresh(order)
    return order, (result.checkout_payload or {})


@router.post("/create-mp", response_model=MercadoPagoPaymentResponse, summary="创建 Mercado Pago 支付订单")
def create_mercadopago_payment_order(
    req: CreateMercadoPagoPaymentRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    _require_payment_rails_enabled()
    try:
        log_api_request(
            method="POST",
            path="/api/v1/app/wallet/payments/create-mp",
            operation="create_mercadopago_payment_order",
            current_user=current_user_obj,
            params={"type": req.type, "amount": req.amount, "currency": req.currency},
        )
        try:
            validate_email(req.email)
        except EmailNotValidError as e:
            raise HTTPException(status_code=400, detail=f"Invalid email format: {str(e)}")

        db = SuperSessionLocal()
        try:
            command = CreatePaymentCommand(
                provider="mercadopago",
                order_type=req.type,
                amount=Decimal(str(req.amount)),
                currency=req.currency.upper(),
                metadata=req.metadata or {},
                email=req.email,
                token=req.token,
                payment_method_id=req.payment_method_id,
                idempotency_key=req.idempotency_key,
                device_id=req.device_id,
                description=req.description,
            )
            order, _ = _create_order_from_command(db, current_user_obj, command)
            return MercadoPagoPaymentResponse(
                order_id=str(order.id),
                payment_id=order.mercadopago_payment_id or "",
                status=order.status,
                external_reference=order.external_reference or "",
                amount=Decimal(str(order.amount)),
                currency=order.currency,
            )
        finally:
            db.close()
    except HTTPException:
        raise
    except RailError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"code": e.code, "message": str(e), "retryable": e.retryable},
        ) from e
    except ValueError as e:
        # MP 侧或入参问题；message 由 _extract_mp_api_error 等拼出
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating MercadoPago payment order: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/create", response_model=CreatePaymentResponse, summary="创建支付订单（Wompi，保留兼容）")
def create_payment_order(
    req: CreatePaymentRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    _require_payment_rails_enabled()
    try:
        log_api_request(
            method="POST",
            path="/api/v1/app/wallet/payments/create",
            operation="create_payment_order",
            current_user=current_user_obj,
            params={"type": req.type, "amount": req.amount, "currency": req.currency},
        )
        db = SuperSessionLocal()
        try:
            command = CreatePaymentCommand(
                provider="wompi",
                order_type=req.type,
                amount=Decimal(str(req.amount)),
                currency=req.currency.upper(),
                metadata=req.metadata or {},
                idempotency_key=req.idempotency_key,
            )
            order, checkout_payload = _create_order_from_command(db, current_user_obj, command)
            return CreatePaymentResponse(
                order_id=str(order.id),
                reference=order.reference or "",
                payment_data=WompiPaymentData(**checkout_payload),
                checkout_url=f"https://checkout.wompi.co/l/{order.reference}",
            )
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="POST",
            path="/api/v1/app/wallet/payments/create",
            operation="create_payment_order",
            error=e,
            current_user=current_user_obj,
            params={"type": req.type, "amount": req.amount},
        )
        raise


@router.get("/{order_id}/status", response_model=PaymentStatusResponse, summary="查询支付状态")
def get_payment_status(
    order_id: str,
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """查询支付订单状态"""
    try:
        log_api_request(
            method="GET",
            path=f"/api/v1/app/wallet/payments/{order_id}/status",
            operation="get_payment_status",
            current_user=current_user_obj,
            params={"order_id": order_id}
        )
        
        db = SuperSessionLocal()
        try:
            order = db.query(PaymentOrder).filter(
                PaymentOrder.id == order_id,
                PaymentOrder.app_user_id == current_user_obj.id
            ).first()
            
            if not order:
                log_api_error(
                    method="GET",
                    path=f"/api/v1/app/wallet/payments/{order_id}/status",
                    operation="get_payment_status",
                    error=HTTPException(status_code=404, detail="Payment order not found"),
                    current_user=current_user_obj,
                    params={"order_id": order_id}
                )
                raise HTTPException(status_code=404, detail="Payment order not found")
            
            # Status reads are also the user-facing reconciliation path after
            # the App has been closed. Webhooks and admin reconciliation call
            # the same service.
            now = datetime.now(timezone.utc)
            is_expired = False

            if (
                order.payment_provider == "mercadopago"
                and order.mercadopago_payment_id
                and order.status in {"created", "processing"}
            ):
                try:
                    PaymentReconciliationService().query_and_reconcile(
                        db,
                        payment_order_id=order.id,
                    )
                    order = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).one()
                except (PaymentReconciliationError, PaymentProviderError, ProviderCapabilityError):
                    db.rollback()

            terminal_states = ["approved", "declined", "voided", "error", "expired", "refunded"]
            if order.expires_at and order.expires_at < now and order.status not in terminal_states:
                is_expired = True
                try:
                    PaymentReconciliationService().reconcile(
                        db,
                        payment_order_id=order.id,
                        status="expired",
                        provider_payment_id=order.mercadopago_payment_id,
                        external_reference=order.external_reference,
                        amount=Decimal(str(order.amount)),
                        currency=order.currency,
                    )
                    order = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).one()
                except PaymentReconciliationError:
                    db.rollback()
            
            log_api_response(
                method="GET",
                path=f"/api/v1/app/wallet/payments/{order_id}/status",
                operation="get_payment_status",
                result="success",
                current_user=current_user_obj,
                details={"order_id": order_id, "status": order.status, "is_expired": is_expired}
            )
            
            projected_status = (
                "action_required"
                if isinstance((order.order_metadata or {}).get("next_action"), dict)
                else order.status
            )
            return PaymentStatusResponse(
                order_id=str(order.id),
                purpose=str((order.order_metadata or {}).get("payment_purpose") or order.type),
                status=projected_status,
                status_detail=(order.order_metadata or {}).get("provider_status"),
                wompi_transaction_id=order.wompi_transaction_id,
                mercadopago_payment_id=order.mercadopago_payment_id,
                amount=Decimal(str(order.amount)),
                currency=order.currency,
                invoice_id=(order.order_metadata or {}).get("invoice_id"),
                session_id=(order.order_metadata or {}).get("session_id"),
                next_action=(order.order_metadata or {}).get("next_action"),
                paid_at=order.paid_at.isoformat() if order.paid_at else None,
                expires_at=order.expires_at.isoformat(),
                is_expired=is_expired,
            )
        except HTTPException:
            raise
        except Exception as e:
            log_api_error(
                method="GET",
                path=f"/api/v1/app/wallet/payments/{order_id}/status",
                operation="get_payment_status",
                error=e,
                current_user=current_user_obj,
                params={"order_id": order_id}
            )
            raise
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="GET",
            path=f"/api/v1/app/wallet/payments/{order_id}/status",
            operation="get_payment_status",
            error=e,
            current_user=current_user_obj,
            params={"order_id": order_id},
        )
        raise


# The legacy create/status router above is deliberately not included by
# api/v1/__init__.py.  From this point on, `router` is the canonical webhook
# adapter router exposed under /api/v1/app/payments.
legacy_router = router
router = APIRouter()


@router.post("/webhooks/sim", summary="本地场景支付 Webhook（仅 development/test）")
async def handle_sim_payment_webhook(
    request_data: SimPaymentWebhookRequest,
    x_sim_signature: Optional[str] = Header(None, alias="X-Sim-Signature"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """Drive the real payment state machine without exposing a production test API."""
    if os.getenv("ENVIRONMENT", "development").lower() not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="Not found")

    secret = os.getenv("SIM_E2E_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="SIM payment webhook is not configured")
    if idempotency_key != request_data.event_id:
        raise HTTPException(status_code=400, detail="Idempotency-Key must equal event_id")
    if (request_data.session_id is None) == (request_data.payment_order_id is None):
        raise HTTPException(
            status_code=422,
            detail="Exactly one of session_id or payment_order_id is required",
        )

    payload = request_data.model_dump(mode="json", exclude_none=True)
    expected_signature = build_sim_webhook_signature(payload, secret)
    if not x_sim_signature or not hmac.compare_digest(
        expected_signature, x_sim_signature
    ):
        raise HTTPException(status_code=401, detail="Invalid SIM webhook signature")

    db = SuperSessionLocal()
    try:
        session = None
        if request_data.session_id is not None:
            session = db.query(ChargingSession).filter(
                ChargingSession.id == request_data.session_id
            ).first()
            if not session or not session.payment_order_id:
                raise HTTPException(status_code=404, detail="Payment order not found")
            order_id = session.payment_order_id
        else:
            order_id = request_data.payment_order_id

        order = db.query(PaymentOrder).filter(
            PaymentOrder.id == order_id,
            PaymentOrder.payment_provider == "fake",
        ).with_for_update().first()
        if not order:
            raise HTTPException(status_code=404, detail="Payment order not found")

        provider_id = str(order.id)
        existing_event = db.query(PaymentWebhookEvent).filter(
            PaymentWebhookEvent.payment_provider == "fake",
            PaymentWebhookEvent.payment_provider_id == provider_id,
            PaymentWebhookEvent.event_id == request_data.event_id,
        ).first()
        if existing_event:
            if existing_event.payload != payload:
                raise HTTPException(
                    status_code=409,
                    detail="event_id was already used with a different payload",
                )
            if existing_event.processed:
                return _sim_webhook_invariants(
                    db, order, request_data.event_id, replayed=True
                )

        event = existing_event or PaymentWebhookEvent(
            payment_order_id=order.id,
            payment_provider="fake",
            payment_provider_id=provider_id,
            event_id=request_data.event_id,
            event_type="payment.updated",
            payload=payload,
            processed=False,
        )
        if not existing_event:
            db.add(event)
            db.flush()

        target_status = {
            "approved": "approved",
            "pending": "processing",
            "rejected": "declined",
            "timeout": "error",
        }[request_data.status]
        try:
            order.status = transition_status(order.status, target_status)
        except ValueError:
            # Formal providers also preserve terminal state against late callbacks.
            pass

        app_user = db.query(AppUser).filter(AppUser.id == order.app_user_id).one()
        if order.status == "approved":
            order.paid_at = order.paid_at or datetime.now(timezone.utc)
            _apply_approved_business_logic(db, order, app_user, "SIM fake", provider_id)
        elif target_status in {"declined", "error"} and order.type == "charging":
            if session is None:
                session = db.query(ChargingSession).filter(
                    ChargingSession.payment_order_id == order.id
                ).first()
            if session:
                session.payment_status = "unpaid"
                session.payment_order_id = order.id
                app_user.has_unpaid_charges = True

        order.updated_at = datetime.now(timezone.utc)
        event.processed = True
        event.processed_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            order = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).one()
            event = db.query(PaymentWebhookEvent).filter(
                PaymentWebhookEvent.payment_provider == "fake",
                PaymentWebhookEvent.payment_provider_id == provider_id,
                PaymentWebhookEvent.event_id == request_data.event_id,
            ).one_or_none()
            if not event or event.payload != payload or not event.processed:
                raise
            return _sim_webhook_invariants(
                db, order, request_data.event_id, replayed=True
            )

        return _sim_webhook_invariants(
            db, order, request_data.event_id, replayed=False
        )
    finally:
        db.close()


@router.post("/webhooks/mercadopago", summary="Mercado Pago Webhook 回调")
async def handle_mercadopago_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-Id"),
):
    """Verify, actively query and reconcile a Mercado Pago payment event."""
    db = SuperSessionLocal()
    try:
        payload = await request.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        data_id = data.get("id") if isinstance(data, dict) else None
        if not data_id:
            raise HTTPException(status_code=400, detail="Payment ID not found")
        if not x_signature or not x_request_id:
            raise HTTPException(status_code=401, detail="Invalid signature")

        # The payment id is the only trusted lookup key available before the
        # provider query. Merchant context is then derived from the persisted,
        # server-created order snapshot.
        webhook_external_reference = (
            payload.get("external_reference")
            or (data.get("external_reference") if isinstance(data, dict) else None)
        )
        order_query = db.query(PaymentOrder).filter(
            PaymentOrder.payment_provider == "mercadopago",
        )
        if webhook_external_reference:
            order_query = order_query.filter(
                (PaymentOrder.mercadopago_payment_id == str(data_id))
                | (PaymentOrder.external_reference == str(webhook_external_reference))
            )
        else:
            order_query = order_query.filter(
                PaymentOrder.mercadopago_payment_id == str(data_id)
            )
        order = order_query.first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        reconciliation = PaymentReconciliationService()
        try:
            context = reconciliation.merchant_context_for_order(
                payment_order=order,
                purpose=(
                    PaymentPurpose.RECONCILIATION
                    if order.type == "charging"
                    else PaymentPurpose.WALLET_TOP_UP
                ),
            )
            provider = get_payment_provider_registry().get(order.payment_provider)
            if not hasattr(provider, "verify_webhook_signature"):
                raise PaymentReconciliationError("Provider does not support webhook verification")
            if not provider.verify_webhook_signature(
                x_signature=x_signature,
                x_request_id=x_request_id,
                data_id=str(data_id),
                merchant_context=context,
            ):
                raise HTTPException(status_code=401, detail="Invalid signature")
            query_capability = getattr(provider, "query_payment", None)
            if callable(query_capability):
                canonical: PaymentCapabilityResult = query_capability(
                    str(data_id),
                    merchant_context=context,
                )
                facts = ProviderPaymentStatus(
                    status=PaymentReconciliationService._legacy_status(canonical.status),
                    provider_payment_id=canonical.provider_ref,
                    external_reference=canonical.merchant_ref,
                    amount=canonical.amount or Decimal(str(order.amount)),
                    currency=canonical.currency or order.currency,
                    next_action_url=(
                        canonical.next_action.url
                        if canonical.next_action and canonical.next_action.type == "open_url"
                        else None
                    ),
                )
            else:
                facts = provider.get_payment_status(
                    str(data_id),
                    merchant_context=context,
                )
        except HTTPException:
            raise
        except (PaymentReconciliationError, PaymentProviderError, ProviderCapabilityError):
            raise HTTPException(status_code=500, detail="Unable to verify payment")

        # Store only a minimal event envelope. The raw provider payload can
        # contain payer data and must never become a database/log artifact.
        event_id = str(payload.get("id") or data_id)[:255]
        safe_payload = {
            "id": event_id,
            "action": str(payload.get("action") or "")[:100],
            "data": {"id": str(data_id)},
        }
        existing_event = db.query(PaymentWebhookEvent).filter(
            PaymentWebhookEvent.payment_provider == "mercadopago",
            PaymentWebhookEvent.payment_provider_id == str(data_id),
            PaymentWebhookEvent.event_id == event_id,
        ).first()
        if existing_event and existing_event.processed:
            return {"status": "ok"}
        if existing_event and existing_event.payload != safe_payload:
            raise HTTPException(status_code=409, detail="Webhook event payload conflict")
        if not existing_event:
            webhook_event = PaymentWebhookEvent(
                payment_order_id=order.id,
                payment_provider="mercadopago",
                payment_provider_id=str(data_id),
                event_id=event_id,
                event_type=str(payload.get("action") or "payment.updated")[:100],
                payload=safe_payload,
                processed=False,
            )
            db.add(webhook_event)
            db.flush()
        else:
            webhook_event = existing_event

        reconciliation.reconcile(
            db,
            payment_order_id=order.id,
            status=facts.status,
            provider_payment_id=facts.provider_payment_id,
            external_reference=facts.external_reference,
            amount=facts.amount,
            currency=facts.currency,
            next_action_url=facts.next_action_url,
        )

        # A Mercado Pago dispute is still resolved through the same verified,
        # actively queried payment fact.  Only the provider-neutral dispute
        # fields cross into ChargebackCase authority; the webhook payload is
        # never passed to the projection or persisted as an evidence blob.
        if facts.status == "disputed":
            dispute_ingest = getattr(provider, "ingest_dispute_fact", None)
            if not callable(dispute_ingest):
                raise PaymentReconciliationError("Provider dispute capability is unavailable")
            dispute_ref = (
                (data.get("dispute_ref") if isinstance(data, dict) else None)
                or (data.get("dispute_id") if isinstance(data, dict) else None)
                or payload.get("dispute_ref")
                or payload.get("dispute_id")
                or payload.get("id")
                or data_id
            )
            dispute_fact = dispute_ingest(
                {
                    "payment_ref": str(facts.provider_payment_id or data_id),
                    "status": "disputed",
                    "amount": facts.amount,
                    "currency": facts.currency,
                    "dispute_ref": str(dispute_ref)[:255] if dispute_ref else None,
                    "reason_code": (
                        str(
                            (data.get("reason_code") if isinstance(data, dict) else None)
                            or payload.get("reason_code")
                        )[:100]
                        if (
                            (data.get("reason_code") if isinstance(data, dict) else None)
                            or payload.get("reason_code")
                        )
                        else None
                    ),
                },
                merchant_context=context,
            )
            dispute_amount = (
                dispute_fact.amount
                if dispute_fact.amount is not None
                else facts.amount
            )
            dispute_currency = dispute_fact.currency or facts.currency
            if (
                dispute_fact.status in {"disputed", "reversed"}
                and dispute_fact.dispute_ref
                and dispute_amount is not None
                and dispute_currency
            ):
                RefundCaseService().ingest_chargeback_fact(
                    db,
                    provider="mercadopago",
                    payment_ref=dispute_fact.payment_ref,
                    disputed_amount=dispute_amount,
                    currency=dispute_currency,
                    status=dispute_fact.status,
                    dispute_ref=dispute_fact.dispute_ref,
                    reason_code=dispute_fact.reason_code,
                    source_reference=event_id,
                )

        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except (PaymentReconciliationError, PaymentProviderError, ProviderCapabilityError):
        db.rollback()
        raise HTTPException(status_code=400, detail="Payment reconciliation failed")
    except Exception:
        db.rollback()
        logger.error("Error processing MercadoPago webhook", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@legacy_router.post("/webhook", summary="Wompi Webhook（未注册的历史实现）")
async def handle_wompi_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
):
    """
    Wompi Webhook 回调处理：
    1. 验证 Webhook 签名
    2. 提取 transaction_id 和 event_id
    3. 使用 reference 查找订单
    4. 金额/币种校验
    5. 幂等性检查
    6. 二次确认
    7. 更新订单状态和业务逻辑
    """
    db = SuperSessionLocal()
    try:
        wompi_service = get_wompi_service()
        
        # 获取请求体
        payload = await request.json()
        
        # 验证签名
        if not wompi_service.verify_webhook_signature(payload, x_signature):
            logger.error("Webhook signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # 提取关键信息
        transaction_id = payload.get("data", {}).get("transaction", {}).get("id")
        event_id = payload.get("event_id") or payload.get("id")
        reference = payload.get("data", {}).get("transaction", {}).get("reference")
        
        if not reference:
            logger.error("Reference not found in webhook payload")
            raise HTTPException(status_code=400, detail="Reference not found")
        
        if not transaction_id:
            logger.error("Transaction ID not found in webhook payload")
            raise HTTPException(status_code=400, detail="Transaction ID not found")
        
        if not event_id:
            logger.warning("Event ID not found, using transaction_id as event_id")
            event_id = transaction_id
        
        # 查找订单
        order = db.query(PaymentOrder).filter(PaymentOrder.reference == reference).first()
        if not order:
            logger.error(f"Order not found for reference: {reference}")
            raise HTTPException(status_code=404, detail="Order not found")
        
        # 幂等性检查
        existing_event = db.query(PaymentWebhookEvent).filter(
            PaymentWebhookEvent.wompi_transaction_id == transaction_id,
            PaymentWebhookEvent.wompi_event_id == event_id
        ).first()
        
        if existing_event and existing_event.processed:
            logger.info(f"Webhook event already processed: transaction_id={transaction_id}, event_id={event_id}")
            return {"status": "ok", "message": "Already processed"}
        
        # 如果没有记录，创建事件记录
        if not existing_event:
            webhook_event = PaymentWebhookEvent(
                payment_order_id=order.id,
                payment_provider="wompi",
                wompi_transaction_id=transaction_id,
                wompi_event_id=event_id,
                event_type=payload.get("event"),
                payload=payload,
                processed=False,
            )
            db.add(webhook_event)
            db.flush()
        else:
            webhook_event = existing_event
        
        # 二次确认：查询 Wompi 交易状态
        wompi_transaction = await wompi_service.get_transaction_status(transaction_id)
        if not wompi_transaction:
            logger.error(f"Failed to verify transaction from Wompi: {transaction_id}")
            raise HTTPException(status_code=500, detail="Failed to verify transaction")
        
        # 金额/币种校验（防串单/篡改）
        wompi_amount = Decimal(str(wompi_transaction.get("amount_in_cents", 0))) / 100
        wompi_currency = wompi_transaction.get("currency", "")
        
        is_valid, error_msg = wompi_service.validate_amount_and_currency(
            order_amount=order.amount,
            order_currency=order.currency,
            wompi_amount=wompi_amount,
            wompi_currency=wompi_currency
        )
        
        if not is_valid:
            logger.error(f"Amount/currency validation failed: {error_msg}")
            order.status = "error"
            order.updated_at = datetime.now(timezone.utc)
            webhook_event.processed = True
            webhook_event.processed_at = datetime.now(timezone.utc)
            db.commit()
            raise HTTPException(status_code=400, detail=error_msg)
        
        # 获取交易状态
        transaction_status = wompi_transaction.get("status")
        transaction_state = wompi_transaction.get("status_message") or transaction_status
        
        # 状态推进规则：由领域状态机统一处理，乱序回调不会覆盖已完成状态。
        old_status = order.status
        
        # 状态映射
        status_mapping = {
            "PENDING": "processing",
            "IN_PROCESS": "processing",
            "APPROVED": "approved",
            "DECLINED": "declined",
            "VOIDED": "voided",
            "ERROR": "error",
        }
        
        new_status = status_mapping.get(transaction_status.upper(), "error")
        
        # 如果已经是终态，不允许回退
        try:
            new_status = transition_status(old_status, new_status)
        except ValueError:
            logger.warning("Payment status transition rejected: order=%s %s -> %s", order.id, old_status, new_status)
            new_status = old_status
        order.status = new_status
        
        # 更新订单信息
        order.wompi_transaction_id = transaction_id
        if new_status == "approved":
            order.paid_at = datetime.now(timezone.utc)
        
        order.updated_at = datetime.now(timezone.utc)
        
        # 业务逻辑处理
        if new_status == "approved":
            if order.type == "top_up":
                app_user = db.query(AppUser).filter(AppUser.id == order.app_user_id).with_for_update().one_or_none()
                if app_user:
                    _apply_approved_business_logic(db, order, app_user, "Wompi", reference)
            
            elif order.type == "charging":
                # 充电支付：标记充电会话为已支付
                session_id = order.order_metadata.get("session_id") if order.order_metadata else None
                if session_id:
                    session = db.query(ChargingSession).filter(ChargingSession.id == session_id).first()
                    if session:
                        session.payment_status = "paid"
                        session.payment_order_id = order.id
                        logger.info(
                            f"[APP API] Charging payment completed: session={session_id}, "
                            f"order={order.id}"
                        )
        
        elif new_status in ["declined", "error", "voided"]:
            # 支付失败：如果是充电支付，标记为欠费
            if order.type == "charging":
                session_id = order.order_metadata.get("session_id") if order.order_metadata else None
                if session_id:
                    session = db.query(ChargingSession).filter(ChargingSession.id == session_id).first()
                    if session:
                        session.payment_status = "unpaid"
                        session.payment_order_id = order.id
                        
                        # 标记用户为有欠费
                        app_user = db.query(AppUser).filter(AppUser.id == order.app_user_id).first()
                        if app_user:
                            app_user.has_unpaid_charges = True
                        
                        logger.warning(
                            f"[APP API] Charging payment failed: session={session_id}, "
                            f"order={order.id}, status={new_status}"
                        )
        
        # 标记事件为已处理
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(timezone.utc)
        
        db.commit()
        
        logger.info(
            f"[APP API] Webhook processed: order={order.id}, "
            f"reference={reference}, status={new_status}"
        )
        
        return {"status": "ok", "order_id": str(order.id), "status": new_status}
    finally:
        db.close()
