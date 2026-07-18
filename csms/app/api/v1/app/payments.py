#
# APP用户 - 支付API（Wompi）
# 提供创建支付订单、查询状态、Webhook 回调等功能
#

from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.api_logging import log_api_request, log_api_response, log_api_error, log_business_operation
from app.core.auth import get_current_user
from app.database.base import get_db, SuperSessionLocal
from app.database.models import (
    AppUser, PaymentOrder, PaymentWebhookEvent, 
    ChargingSession, AppWalletTransaction, Tenant
)
from app.services.wompi_service import get_wompi_service
from app.services.mercadopago_service import get_mercadopago_service
from app.services.payment_providers.base import CreatePaymentCommand
from app.services.payment_providers.registry import get_payment_provider_registry
from app.domain.payment import transition_status
from app.core.id_generator import generate_order_id
from app.core.config import get_settings
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
    amount: Decimal = Field(..., gt=0, description="支付金额")
    currency: str = Field("COP", description="货币（默认 COP）")
    idempotency_key: Optional[str] = Field(None, description="支付创建幂等键")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据（充电支付时需要 session_id）")


class CreateMercadoPagoPaymentRequest(BaseModel):
    """Mercado Pago 支付请求"""
    type: str = Field(..., description="订单类型：top_up 或 charging")
    amount: Decimal = Field(..., gt=0, description="支付金额")
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
    status: str
    wompi_transaction_id: Optional[str] = None
    mercadopago_payment_id: Optional[str] = None
    amount: Decimal
    currency: str
    paid_at: Optional[str] = None
    expires_at: str
    is_expired: bool


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
            description=f"{provider_display_name} 充值（订单 {provider_ref or order.id}）",
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
    """把退款作为反向账本分录落库，订单状态只是账务状态的投影。"""
    amount = Decimal(str(amount))
    if amount <= 0 or amount > Decimal(str(order.amount)):
        raise ValueError("Invalid refund amount")
    user = db.query(AppUser).filter(AppUser.id == order.app_user_id).with_for_update().one()
    ledger_id = f"payment_refund_{order.id}"
    if db.query(AppWalletTransaction).filter(
        AppWalletTransaction.transaction_number == ledger_id
    ).first():
        return
    user.balance = Decimal(str(user.balance or 0)) - amount
    tenant = db.query(Tenant).order_by(Tenant.created_at.asc()).first()
    if tenant:
        db.add(AppWalletTransaction(
            transaction_number=ledger_id,
            app_user_id=user.id,
            payment_order_id=order.id,
            operator_tenant_id=tenant.id,
            charge_point_id=None,
            type="refund",
            amount=-amount,
            description=f"支付退款（订单 {order.id}）",
        ))


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
    registry = get_payment_provider_registry()
    provider = registry.get(command.provider)
    result = provider.create_payment(command)

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
                amount=float(order.amount),
                currency=order.currency,
            )
        finally:
            db.close()
    except HTTPException:
        raise
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
            
            # 检查是否过期
            now = datetime.now(timezone.utc)
            is_expired = False
            
            # 如果超过 expires_at 且仍非终态，标记为过期
            terminal_states = ["approved", "declined", "voided", "error", "refunded"]
            if order.expires_at and order.expires_at < now and order.status not in terminal_states:
                is_expired = True
                if order.status != "expired":
                    order.status = "expired"
                    db.commit()
                    logger.info(f"Order {order_id} marked as expired")
            
            log_api_response(
                method="GET",
                path=f"/api/v1/app/wallet/payments/{order_id}/status",
                operation="get_payment_status",
                result="success",
                current_user=current_user_obj,
                details={"order_id": order_id, "status": order.status, "is_expired": is_expired}
            )
            
            return PaymentStatusResponse(
                order_id=str(order.id),
                status=order.status,
                wompi_transaction_id=order.wompi_transaction_id,
                mercadopago_payment_id=order.mercadopago_payment_id,
                amount=float(order.amount),
                currency=order.currency,
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


@router.post("/webhook-mp", summary="Mercado Pago Webhook 回调")
async def handle_mercadopago_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-Id"),
):
    """
    Mercado Pago Webhook 回调处理：
    1. 验证 Webhook 签名
    2. 提取 payment_id 和 event_id
    3. 使用 external_reference 或 payment_id 查找订单
    4. 主动反查支付状态（重要：MP 推送不可信）
    5. 金额/币种校验
    6. 幂等性检查
    7. 更新订单状态和业务逻辑

    扩展（待办）：收到 card/customer 类通知或 Checkout 绑卡回调时，写入 app_user_payment_methods，
    与 APP 端「已保存卡」列表对齐。
    """
    db = SuperSessionLocal()
    try:
        mp_service = get_mercadopago_service()
        
        # 获取请求体
        payload = await request.json()
        
        action = payload.get("action")
        data_id = payload.get("data", {}).get("id")
        
        if not data_id:
            logger.error("Payment ID not found in webhook payload")
            raise HTTPException(status_code=400, detail="Payment ID not found")
        
        if not x_request_id:
            logger.warning("X-Request-Id not found in headers")
            x_request_id = data_id  # 使用 payment_id 作为 fallback
        
        # 签名是强制要求；不能把未签名回调当作开发环境例外放行。
        if not x_signature or not x_request_id or not mp_service.verify_webhook_signature(x_signature, x_request_id, data_id):
            logger.error("Webhook signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # 主动反查支付状态（重要：MP 推送不可信，必须反查）
        payment_info = mp_service.get_payment_status(data_id)
        if not payment_info.get("success"):
            logger.error(f"Failed to get payment status from MercadoPago: {data_id}")
            raise HTTPException(status_code=500, detail="Failed to verify payment status")
        
        mp_payment = payment_info.get("payment", {})
        external_ref = mp_payment.get("external_reference")
        mp_status = mp_payment.get("status")
        mp_amount = Decimal(str(mp_payment.get("transaction_amount", 0)))
        mp_currency = mp_payment.get("currency_id", "").upper()
        
        # 查找订单（优先使用 external_reference，否则使用 payment_id）
        order = None
        if external_ref:
            order = db.query(PaymentOrder).filter(PaymentOrder.external_reference == external_ref).first()
        
        if not order:
            order = db.query(PaymentOrder).filter(PaymentOrder.mercadopago_payment_id == data_id).first()
        
        if not order:
            logger.error(f"Order not found for payment_id: {data_id}, external_reference: {external_ref}")
            raise HTTPException(status_code=404, detail="Order not found")

        if order.mercadopago_payment_id and order.mercadopago_payment_id != data_id:
            raise HTTPException(status_code=400, detail="Payment/order ownership mismatch")
        order = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).with_for_update().one()
        
        # 金额/币种校验（防串单/篡改）
        if mp_amount != order.amount or mp_currency != order.currency:
            logger.error(
                f"Amount/currency mismatch: order={order.id}, "
                f"order_amount={order.amount}, mp_amount={mp_amount}, "
                f"order_currency={order.currency}, mp_currency={mp_currency}"
            )
            order.status = "error"
            order.updated_at = datetime.now(timezone.utc)
            db.commit()
            raise HTTPException(status_code=400, detail="Amount or currency mismatch")
        
        # 幂等性检查
        event_id = payload.get("id") or data_id  # 使用 notification id 或 payment id
        
        existing_event = db.query(PaymentWebhookEvent).filter(
            PaymentWebhookEvent.payment_provider == "mercadopago",
            PaymentWebhookEvent.payment_provider_id == data_id,
            PaymentWebhookEvent.event_id == event_id
        ).first()
        
        if existing_event and existing_event.processed:
            logger.info(f"Webhook event already processed: payment_id={data_id}, event_id={event_id}")
            return {"status": "ok", "message": "Already processed"}
        
        # 如果没有记录，创建事件记录
        if not existing_event:
            webhook_event = PaymentWebhookEvent(
                payment_order_id=order.id,
                payment_provider="mercadopago",
                payment_provider_id=data_id,
                event_id=event_id,
                event_type=action,
                payload=payload,
                processed=False,
            )
            db.add(webhook_event)
            db.flush()
        else:
            webhook_event = existing_event
        
        # 映射 MP 状态到内部状态
        internal_status = mp_service.map_status(mp_status)
        
        # 状态推进规则：只能向终态推进，不允许回退
        terminal_states = ["approved", "declined", "voided", "error", "refunded"]
        old_status = order.status
        
        # 如果已经是终态，不允许回退
        try:
            internal_status = transition_status(old_status, internal_status)
        except ValueError:
            logger.warning("Payment status transition rejected: order=%s %s -> %s", order.id, old_status, internal_status)
            internal_status = old_status
        order.status = internal_status
        
        # 更新订单信息
        order.mercadopago_payment_id = data_id
        if internal_status == "approved":
            order.paid_at = datetime.now(timezone.utc)
        
        order.updated_at = datetime.now(timezone.utc)
        
        # 业务逻辑处理（与 Wompi 相同）
        if internal_status == "approved":
            if order.type == "top_up":
                app_user = db.query(AppUser).filter(AppUser.id == order.app_user_id).with_for_update().one_or_none()
                if app_user:
                    _apply_approved_business_logic(db, order, app_user, "MercadoPago", external_ref or data_id)
            
            elif order.type == "charging":
                # 充电支付：标记充电会话为已支付
                session_id = order.order_metadata.get("session_id") if order.order_metadata else None
                if session_id:
                    session = db.query(ChargingSession).filter(ChargingSession.id == session_id).first()
                    if session:
                        session.payment_status = "paid"
                        session.payment_order_id = order.id
                        logger.info(
                            f"[APP API] MercadoPago charging payment completed: session={session_id}, "
                            f"order={order.id}"
                        )
        
        elif internal_status in ["declined", "error", "voided"]:
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
                            f"[APP API] MercadoPago charging payment failed: session={session_id}, "
                            f"order={order.id}, status={internal_status}"
                        )
        
        # 标记事件为已处理
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(timezone.utc)
        
        db.commit()
        
        logger.info(
            f"[APP API] MercadoPago webhook processed: order={order.id}, "
            f"payment_id={data_id}, status={internal_status}"
        )
        
        return {"status": "ok", "order_id": str(order.id), "status": internal_status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing MercadoPago webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/webhook", summary="Wompi Webhook 回调（保留兼容）")
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
