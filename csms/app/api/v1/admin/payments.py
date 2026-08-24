#
# Admin - 支付管理API
# 提供支付订单列表、详情、对账等功能
#

from typing import List, Dict, Any, Optional
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.logging_config import get_logger
from app.core.api_logging import log_api_request, log_api_response, log_api_error, log_business_operation
from app.core.auth import get_current_user
from app.core.permissions import get_current_admin_user as get_verified_admin_user
from app.database.base import get_db, SuperSessionLocal
from app.database.models import PaymentOrder, PaymentWebhookEvent, AppUser
from app.services.wompi_service import get_wompi_service
from app.services.payment_reconciliation import (
    PaymentReconciliationError,
    PaymentReconciliationService,
)
from app.services.payment_providers.base import PaymentProviderError
from app.services.payment_refunds import (
    PaymentRefundService,
    RefundManualReviewRequired,
    RefundRequestInvalid,
    RefundRetryable,
)

logger = get_logger("ocpp_csms")

router = APIRouter()


async def get_current_admin_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
):
    """验证当前用户是管理员"""
    user_type = current_user_payload.get("user_type")
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user_payload


async def require_platform_payment_admin(
    admin=Depends(get_verified_admin_user),
):
    """支付订单当前是平台级模型，租户级支付视图尚未具备安全归属字段。"""
    if not admin.is_super_admin:
        raise HTTPException(status_code=403, detail="Platform payment admin access required")
    return admin


# ==================== 请求/响应模型 ====================

class PaymentOrderListItem(BaseModel):
    id: str
    app_user_id: str
    user_email: Optional[str]
    type: str
    amount: Decimal
    currency: str
    payment_provider: str
    reference: Optional[str]  # Wompi
    external_reference: Optional[str]  # Mercado Pago
    status: str
    wompi_transaction_id: Optional[str]
    mercadopago_payment_id: Optional[str]
    created_at: str
    paid_at: Optional[str]


class PaymentOrderDetail(PaymentOrderListItem):
    integrity_signature: Optional[str]
    redirect_url: Optional[str]
    expires_at: str
    payment_deadline_at: Optional[str]
    metadata: Optional[Dict[str, Any]]
    updated_at: str


class PaymentWebhookEventItem(BaseModel):
    id: str
    payment_provider: str
    wompi_transaction_id: Optional[str]
    wompi_event_id: Optional[str]
    payment_provider_id: Optional[str]  # 通用字段
    event_id: Optional[str]  # 通用字段
    event_type: Optional[str]
    processed: bool
    processed_at: Optional[str]
    created_at: str


class PaymentOrderDetailWithEvents(PaymentOrderDetail):
    webhook_events: List[PaymentWebhookEventItem]


class ReconcileResponse(BaseModel):
    success: bool
    message: str
    order_status: Optional[str]
    provider_status: Optional[str]  # Wompi 或 Mercado Pago 状态


class RefundRequest(BaseModel):
    amount: Optional[Decimal] = Field(None, description="退款金额（None 表示全额退款）")


class RefundResponse(BaseModel):
    success: bool
    message: str
    refund_id: Optional[str]
    status: Optional[str]


# ==================== API 端点 ====================

@router.get("", summary="获取支付订单列表")
def list_payment_orders(
    status: Optional[str] = Query(None, description="订单状态筛选"),
    type: Optional[str] = Query(None, description="订单类型筛选：top_up 或 charging"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(require_platform_payment_admin),
    db: Session = Depends(get_db),
) -> List[PaymentOrderListItem]:
    """获取支付订单列表（管理员）"""
    try:
        log_api_request(
            method="GET",
            path="/api/v1/admin/payments",
            operation="list_payment_orders",
            current_user=current_user,
            params={"status": status, "type": type, "limit": limit, "offset": offset}
        )
        
        sdb = SuperSessionLocal()
        try:
            query = sdb.query(PaymentOrder)

            # 状态筛选
            if status:
                query = query.filter(PaymentOrder.status == status)

            # 类型筛选
            if type:
                query = query.filter(PaymentOrder.type == type)

            # 排序和分页
            orders = query.order_by(desc(PaymentOrder.created_at)).offset(offset).limit(limit).all()

            # 批量获取用户邮箱
            user_ids = [str(order.app_user_id) for order in orders]
            users = sdb.query(AppUser).filter(AppUser.id.in_(user_ids)).all()
            user_map = {str(user.id): user.email for user in users}

            result = []
            for order in orders:
                result.append(
                    PaymentOrderListItem(
                        id=str(order.id),
                        app_user_id=str(order.app_user_id),
                        user_email=user_map.get(str(order.app_user_id)),
                        type=order.type,
                        amount=float(order.amount),
                        currency=order.currency,
                        payment_provider=order.payment_provider or "wompi",
                        reference=order.reference,
                        external_reference=order.external_reference,
                        status=order.status,
                        wompi_transaction_id=order.wompi_transaction_id,
                        mercadopago_payment_id=order.mercadopago_payment_id,
                        created_at=order.created_at.isoformat() if order.created_at else "",
                        paid_at=order.paid_at.isoformat() if order.paid_at else None,
                    )
                )

            log_api_response(
                method="GET",
                path="/api/v1/admin/payments",
                operation="list_payment_orders",
                result="success",
                current_user=current_user,
                details={"count": len(result)}
            )

            return result
        except Exception as e:
            log_api_error(
                method="GET",
                path="/api/v1/admin/payments",
                operation="list_payment_orders",
                error=e,
                current_user=current_user,
                params={"status": status, "type": type}
            )
            raise
        finally:
            sdb.close()
    except Exception as e:
        log_api_error(
            method="GET",
            path="/api/v1/admin/payments",
            operation="list_payment_orders",
            error=e,
            current_user=current_user
        )
        raise


@router.get("/{order_id}", summary="获取支付订单详情")
def get_payment_order_detail(
    order_id: str,
    current_user: Dict[str, Any] = Depends(require_platform_payment_admin),
    db: Session = Depends(get_db),
) -> PaymentOrderDetailWithEvents:
    """获取支付订单详情（包含 Webhook 事件记录）"""
    sdb = SuperSessionLocal()
    try:
        order = sdb.query(PaymentOrder).filter(PaymentOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Payment order not found")
        
        # 获取用户邮箱
        user = sdb.query(AppUser).filter(AppUser.id == order.app_user_id).first()
        user_email = user.email if user else None
        
        # 获取 Webhook 事件
        webhook_events = (
            sdb.query(PaymentWebhookEvent)
            .filter(PaymentWebhookEvent.payment_order_id == order.id)
            .order_by(desc(PaymentWebhookEvent.created_at))
            .all()
        )
        
        return PaymentOrderDetailWithEvents(
            id=str(order.id),
            app_user_id=str(order.app_user_id),
            user_email=user_email,
            type=order.type,
            amount=float(order.amount),
            currency=order.currency,
            payment_provider=order.payment_provider or "wompi",
            reference=order.reference,
            external_reference=order.external_reference,
            status=order.status,
            wompi_transaction_id=order.wompi_transaction_id,
            mercadopago_payment_id=order.mercadopago_payment_id,
            integrity_signature=order.integrity_signature,
            redirect_url=order.redirect_url,
            expires_at=order.expires_at.isoformat() if order.expires_at else "",
            payment_deadline_at=order.payment_deadline_at.isoformat() if order.payment_deadline_at else None,
            metadata=order.order_metadata,
            created_at=order.created_at.isoformat() if order.created_at else "",
            paid_at=order.paid_at.isoformat() if order.paid_at else None,
            updated_at=order.updated_at.isoformat() if order.updated_at else "",
            webhook_events=[
                PaymentWebhookEventItem(
                    id=str(event.id),
                    payment_provider=event.payment_provider or "wompi",
                    wompi_transaction_id=event.wompi_transaction_id,
                    wompi_event_id=event.wompi_event_id,
                    payment_provider_id=event.payment_provider_id,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    processed=event.processed,
                    processed_at=event.processed_at.isoformat() if event.processed_at else None,
                    created_at=event.created_at.isoformat() if event.created_at else "",
                )
                for event in webhook_events
            ],
        )
    finally:
        sdb.close()


@router.post("/{order_id}/reconcile", response_model=ReconcileResponse, summary="对账接口")
async def reconcile_payment_order(
    order_id: str,
    current_user: Dict[str, Any] = Depends(require_platform_payment_admin),
    db: Session = Depends(get_db),
) -> ReconcileResponse:
    """
    对账接口：触发后端使用 transaction_id 或 payment_id 去支付提供商查询一次
    更新订单状态（用于 webhook 丢失/延迟时的人工修复）
    支持 Wompi 和 Mercado Pago
    """
    sdb = SuperSessionLocal()
    try:
        order = sdb.query(PaymentOrder).filter(PaymentOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Payment order not found")
        
        payment_provider = order.payment_provider or "wompi"
        
        # Wompi 对账
        if payment_provider == "wompi":
            wompi_service = get_wompi_service()
            
            if not order.wompi_transaction_id:
                return ReconcileResponse(
                    success=False,
                    message="Cannot reconcile: no Wompi transaction ID found",
                    order_status=order.status,
                    provider_status=None,
                )
            
            wompi_transaction = await wompi_service.get_transaction_status(order.wompi_transaction_id)
            
            if not wompi_transaction:
                return ReconcileResponse(
                    success=False,
                    message="Failed to query transaction from Wompi",
                    order_status=order.status,
                    provider_status=None,
                )
            
            provider_status = wompi_transaction.get("status")
            status_message = wompi_transaction.get("status_message", provider_status)
            
            # 状态映射
            status_mapping = {
                "APPROVED": "approved",
                "DECLINED": "declined",
                "VOIDED": "voided",
                "ERROR": "error",
            }
            
            new_status = status_mapping.get(provider_status.upper(), "error")
        
        # Mercado Pago 对账
        elif payment_provider == "mercadopago":
            if not order.mercadopago_payment_id:
                return ReconcileResponse(
                    success=False,
                    message="Cannot reconcile: no Mercado Pago payment ID found",
                    order_status=order.status,
                    provider_status=None,
                )
            
            try:
                result = PaymentReconciliationService().query_and_reconcile(
                    sdb,
                    payment_order_id=order.id,
                )
            except (PaymentReconciliationError, PaymentProviderError):
                return ReconcileResponse(
                    success=False,
                    message="Failed to query payment from Mercado Pago",
                    order_status=order.status,
                    provider_status=None,
                )
            provider_status = result.api_status
            status_message = provider_status
            new_status = result.order_status
        
        else:
            return ReconcileResponse(
                success=False,
                message=f"Unknown payment provider: {payment_provider}",
                order_status=order.status,
                provider_status=None,
            )
        
        # 更新订单状态（如果不同）
        if order.status != new_status:
            old_status = order.status
            order.status = new_status
            if new_status == "approved" and not order.paid_at:
                from datetime import datetime, timezone
                order.paid_at = datetime.now(timezone.utc)
            
            sdb.commit()
            sdb.refresh(order)
            
            logger.info(
                f"[Admin API] Payment order reconciled: order_id={order_id}, "
                f"provider={payment_provider}, old_status={old_status}, new_status={new_status}"
            )
            
            return ReconcileResponse(
                success=True,
                message=f"Order status updated from {old_status} to {new_status}",
                order_status=new_status,
                provider_status=status_message,
            )
        else:
            return ReconcileResponse(
                success=True,
                message=f"Order status matches {payment_provider} status",
                order_status=order.status,
                provider_status=status_message,
            )
    finally:
        sdb.close()


@router.post("/{order_id}/refund", response_model=RefundResponse, summary="退款接口")
async def refund_payment_order(
    order_id: str,
    refund_req: RefundRequest = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current_user: Dict[str, Any] = Depends(require_platform_payment_admin),
    db: Session = Depends(get_db),
) -> RefundResponse:
    """
    退款接口：对已支付的订单进行退款
    支持 Mercado Pago
    amount 为空则全额退款，否则部分退款
    """
    sdb = SuperSessionLocal()
    try:
        try:
            result = PaymentRefundService().refund_payment_order(
                sdb,
                payment_order_id=order_id,
                amount=(Decimal(str(refund_req.amount)) if refund_req.amount is not None else None),
                idempotency_key=idempotency_key,
            )
        except RefundRequestInvalid as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RefundManualReviewRequired as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RefundRetryable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return RefundResponse(
            success=True,
            message="Refund processed successfully",
            refund_id=result.refund_id,
            status=result.status,
        )
    finally:
        sdb.close()
