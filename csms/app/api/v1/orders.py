#
# 订单管理API
# 提供充电订单的查询和管理（使用新表结构）
#

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from datetime import datetime, timezone, timedelta

from app.database.base import get_db
from app.database.models import Order, ChargePoint, Invoice, ChargingSession, Payment
from app.core.auth import get_current_admin_user, require_permission
from app.core.tenant_middleware import get_tenant_id
from app.core.logging_config import get_logger
from fastapi import Request

logger = get_logger("ocpp_csms")

router = APIRouter(prefix="/orders", tags=["订单管理"])


# ==================== 响应模型 ====================

class OrderResponse(BaseModel):
    """订单响应"""
    id: str
    tenant_id: Optional[str]
    session_id: Optional[int]
    charge_point_id: str
    user_id: str
    id_tag: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    energy_kwh: Optional[float]
    duration_minutes: Optional[int]
    total_cost: Optional[float]
    status: str
    created_at: datetime


class OrderDetailResponse(OrderResponse):
    """订单详情响应"""
    invoice_id: Optional[str]
    payment_status: Optional[str]
    charge_point_name: Optional[str]
    user_name: Optional[str]


class RefundRequest(BaseModel):
    """退款请求"""
    reason: str
    amount: Optional[float] = None  # 如果为空，则全额退款


# ==================== 订单管理端点 ====================

@router.get("", response_model=List[OrderResponse], summary="获取订单列表")
async def list_orders(
    user_id: Optional[str] = Query(None, description="用户ID"),
    charge_point_id: Optional[str] = Query(None, description="充电桩ID"),
    status: Optional[str] = Query(None, description="状态过滤"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    request: Request,
    current_user = Depends(require_permission("orders:view")),
    db: Session = Depends(get_db)
):
    """
    获取订单列表
    
    - 支持多租户过滤
    - 支持按用户、充电桩、状态、日期筛选
    - 需要 orders:view 权限
    """
    tenant_id = get_tenant_id(request)
    
    query = db.query(Order)
    
    # 多租户过滤
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Order.tenant_id == tenant_id)
    
    # 筛选条件
    if user_id:
        query = query.filter(Order.user_id == user_id)
    if charge_point_id:
        query = query.filter(Order.charge_point_id == charge_point_id)
    if status:
        query = query.filter(Order.status == status)
    
    # 日期筛选
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            query = query.filter(Order.created_at >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="开始日期格式错误，应为 YYYY-MM-DD"
            )
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
            query = query.filter(Order.created_at <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="结束日期格式错误，应为 YYYY-MM-DD"
            )
    
    orders = query.order_by(desc(Order.created_at)).offset(offset).limit(limit).all()
    
    # 构建响应
    result = []
    for o in orders:
        # 获取关联的发票信息
        invoice = db.query(Invoice).filter(Invoice.order_id == o.id).first()
        total_cost = float(invoice.total_amount) if invoice and invoice.total_amount else None
        
        # 从ChargingSession获取energy_kwh
        energy_kwh = None
        duration_minutes = None
        if o.session_id:
            session = db.query(ChargingSession).filter(ChargingSession.id == o.session_id).first()
            if session:
                if session.meter_start is not None and session.meter_stop is not None:
                    energy_kwh = float(session.meter_stop - session.meter_start) / 1000.0
                if session.start_time and session.end_time:
                    duration = session.end_time - session.start_time
                    duration_minutes = int(duration.total_seconds() / 60)
        
        result.append(OrderResponse(
            id=o.id,
            tenant_id=o.tenant_id,
            session_id=o.session_id,
            charge_point_id=o.charge_point_id,
            user_id=o.user_id,
            id_tag=o.id_tag,
            start_time=o.start_time,
            end_time=o.end_time,
            energy_kwh=energy_kwh,
            duration_minutes=duration_minutes,
            total_cost=total_cost,
            status=o.status,
            created_at=o.created_at
        ))
    
    return result


@router.get("/{order_id}", response_model=OrderDetailResponse, summary="获取订单详情")
async def get_order(
    order_id: str,
    request: Request,
    current_user = Depends(require_permission("orders:detail")),
    db: Session = Depends(get_db)
):
    """获取订单详情"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Order).filter(Order.id == order_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Order.tenant_id == tenant_id)
    
    order = query.first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="订单不存在"
        )
    
    # 获取发票信息
    invoice = db.query(Invoice).filter(Invoice.order_id == order_id).first()
    payment_status = None
    if invoice:
        payment = db.query(Payment).filter(Payment.invoice_id == invoice.id).first()
        payment_status = payment.status if payment else invoice.status
    
    # 获取充电桩信息
    charge_point = db.query(ChargePoint).filter(ChargePoint.id == order.charge_point_id).first()
    
    # 获取用户信息
    from app.database.models import EndUser
    user = db.query(EndUser).filter(EndUser.id == order.user_id).first()
    
    # 计算电量
    energy_kwh = None
    duration_minutes = None
    if order.session_id:
        session = db.query(ChargingSession).filter(ChargingSession.id == order.session_id).first()
        if session:
            if session.meter_start is not None and session.meter_stop is not None:
                energy_kwh = float(session.meter_stop - session.meter_start) / 1000.0
            if session.start_time and session.end_time:
                duration = session.end_time - session.start_time
                duration_minutes = int(duration.total_seconds() / 60)
    
    return OrderDetailResponse(
        id=order.id,
        tenant_id=order.tenant_id,
        session_id=order.session_id,
        charge_point_id=order.charge_point_id,
        charge_point_name=f"{charge_point.vendor} {charge_point.model}" if charge_point else None,
        user_id=order.user_id,
        user_name=user.username if user else None,
        id_tag=order.id_tag,
        start_time=order.start_time,
        end_time=order.end_time,
        energy_kwh=energy_kwh,
        duration_minutes=duration_minutes,
        total_cost=float(invoice.total_amount) if invoice and invoice.total_amount else None,
        status=order.status,
        created_at=order.created_at,
        invoice_id=invoice.id if invoice else None,
        payment_status=payment_status
    )


@router.post("/{order_id}/refund", summary="处理退款")
async def refund_order(
    order_id: str,
    refund_data: RefundRequest,
    request: Request,
    current_user = Depends(require_permission("orders:refund")),
    db: Session = Depends(get_db)
):
    """
    处理订单退款
    
    - 需要 orders:refund 权限
    - 检查订单状态和支付状态
    - 创建退款记录
    """
    tenant_id = get_tenant_id(request)
    
    query = db.query(Order).filter(Order.id == order_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Order.tenant_id == tenant_id)
    
    order = query.first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="订单不存在"
        )
    
    # 检查订单状态
    if order.status not in ["completed", "cancelled"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能对已完成或已取消的订单进行退款"
        )
    
    # 获取发票
    invoice = db.query(Invoice).filter(Invoice.order_id == order_id).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="订单没有关联的发票"
        )
    
    # 检查发票状态
    if invoice.status == "refunded":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="订单已退款"
        )
    
    # 计算退款金额
    refund_amount = refund_data.amount if refund_data.amount else float(invoice.total_amount)
    
    if refund_amount > float(invoice.total_amount):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="退款金额不能超过订单金额"
        )
    
    # 更新发票状态
    invoice.status = "refunded"
    
    # 创建退款支付记录
    from app.core.id_generator import generate_order_id
    refund_payment = Payment(
        id=f"refund_{generate_order_id()}",
        invoice_id=invoice.id,
        amount=refund_amount,
        payment_method="refund",
        status="completed",
        completed_at=datetime.now(timezone.utc)
    )
    db.add(refund_payment)
    
    # 记录审计日志
    from app.database.models import AuditLog
    audit_log = AuditLog(
        tenant_id=tenant_id,
        admin_user_id=current_user.id,
        action="order_refund",
        resource_type="order",
        resource_id=order_id,
        details={
            "refund_amount": refund_amount,
            "reason": refund_data.reason
        },
        ip_address=request.client.host if request.client else None
    )
    db.add(audit_log)
    
    db.commit()
    
    return {"message": "退款处理成功", "refund_amount": refund_amount}


@router.get("/export/csv", summary="导出订单CSV")
async def export_orders_csv(
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    request: Request,
    current_user = Depends(require_permission("orders:export")),
    db: Session = Depends(get_db)
):
    """
    导出订单为CSV格式
    
    - 需要 orders:export 权限
    - 支持日期范围筛选
    """
    from fastapi.responses import StreamingResponse
    import csv
    import io
    
    tenant_id = get_tenant_id(request)
    
    query = db.query(Order)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Order.tenant_id == tenant_id)
    
    # 日期筛选
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        query = query.filter(Order.created_at >= start_dt)
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
        query = query.filter(Order.created_at <= end_dt)
    
    orders = query.order_by(desc(Order.created_at)).all()
    
    # 生成CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # 写入表头
    writer.writerow([
        "订单ID", "用户ID", "充电桩ID", "开始时间", "结束时间",
        "充电量(kWh)", "时长(分钟)", "金额", "状态", "创建时间"
    ])
    
    # 写入数据
    for order in orders:
        invoice = db.query(Invoice).filter(Invoice.order_id == order.id).first()
        total_cost = float(invoice.total_amount) if invoice and invoice.total_amount else 0
        
        energy_kwh = None
        duration_minutes = None
        if order.session_id:
            session = db.query(ChargingSession).filter(ChargingSession.id == order.session_id).first()
            if session:
                if session.meter_start is not None and session.meter_stop is not None:
                    energy_kwh = float(session.meter_stop - session.meter_start) / 1000.0
                if session.start_time and session.end_time:
                    duration = session.end_time - session.start_time
                    duration_minutes = int(duration.total_seconds() / 60)
        
        writer.writerow([
            order.id,
            order.user_id,
            order.charge_point_id,
            order.start_time.isoformat() if order.start_time else "",
            order.end_time.isoformat() if order.end_time else "",
            energy_kwh or "",
            duration_minutes or "",
            total_cost,
            order.status,
            order.created_at.isoformat() if order.created_at else ""
        ])
    
    output.seek(0)
    
    # 生成文件名
    filename = f"orders_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

