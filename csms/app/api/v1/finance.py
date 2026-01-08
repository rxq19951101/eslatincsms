#
# 财务管理API
# 提供收入统计、发票管理和报表导出功能
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from datetime import datetime, timezone, timedelta

from app.database.base import get_db
from app.database.models import Invoice, Payment, Order, ChargePoint, Site
from app.core.auth import get_current_admin_user, require_permission
from app.core.tenant_middleware import get_tenant_id
from fastapi import Request

router = APIRouter(prefix="/finance", tags=["财务管理"])


# ==================== 响应模型 ====================

class RevenueSummaryResponse(BaseModel):
    """收入汇总响应"""
    today_revenue: float
    month_revenue: float
    year_revenue: float
    total_revenue: float


class InvoiceResponse(BaseModel):
    """发票响应"""
    id: str
    tenant_id: Optional[str]
    order_id: Optional[str]
    session_id: int
    energy_kwh: float
    duration_minutes: float
    total_amount: float
    status: str
    issued_at: datetime
    paid_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class InvoiceDetailResponse(InvoiceResponse):
    """发票详情响应"""
    charge_point_id: Optional[str]
    user_id: Optional[str]
    payment_method: Optional[str]
    payment_status: Optional[str]


# ==================== 财务管理端点 ====================

@router.get("/revenue", response_model=RevenueSummaryResponse, summary="获取收入统计")
async def get_revenue_summary(
    request: Request,
    current_user = Depends(require_permission("finance:view")),
    db: Session = Depends(get_db)
):
    """
    获取收入统计
    
    - 今日收入
    - 本月收入
    - 本年收入
    - 总收入
    """
    tenant_id = get_tenant_id(request)
    
    query = db.query(Invoice)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Invoice.tenant_id == tenant_id)
    
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # 今日收入
    today_revenue = query.filter(
        Invoice.issued_at >= today_start
    ).with_entities(func.sum(Invoice.total_amount)).scalar() or 0
    
    # 本月收入
    month_revenue = query.filter(
        Invoice.issued_at >= month_start
    ).with_entities(func.sum(Invoice.total_amount)).scalar() or 0
    
    # 本年收入
    year_revenue = query.filter(
        Invoice.issued_at >= year_start
    ).with_entities(func.sum(Invoice.total_amount)).scalar() or 0
    
    # 总收入
    total_revenue = query.with_entities(func.sum(Invoice.total_amount)).scalar() or 0
    
    return RevenueSummaryResponse(
        today_revenue=round(float(today_revenue), 2),
        month_revenue=round(float(month_revenue), 2),
        year_revenue=round(float(year_revenue), 2),
        total_revenue=round(float(total_revenue), 2)
    )


@router.get("/invoices", response_model=List[InvoiceResponse], summary="获取发票列表")
async def get_invoices(
    status: Optional[str] = Query(None, description="按状态筛选"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    request: Request,
    current_user = Depends(require_permission("finance:view")),
    db: Session = Depends(get_db)
):
    """获取发票列表"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Invoice)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Invoice.tenant_id == tenant_id)
    
    if status:
        query = query.filter(Invoice.status == status)
    
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        query = query.filter(Invoice.issued_at >= start_dt)
    
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
        query = query.filter(Invoice.issued_at <= end_dt)
    
    invoices = query.order_by(desc(Invoice.issued_at)).offset(offset).limit(limit).all()
    
    return invoices


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailResponse, summary="获取发票详情")
async def get_invoice(
    invoice_id: str,
    request: Request,
    current_user = Depends(require_permission("finance:view")),
    db: Session = Depends(get_db)
):
    """获取发票详情"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Invoice).filter(Invoice.id == invoice_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Invoice.tenant_id == tenant_id)
    
    invoice = query.first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="发票不存在"
        )
    
    # 获取支付信息
    payment = db.query(Payment).filter(Payment.invoice_id == invoice_id).first()
    
    # 获取订单和充电桩信息
    order = None
    charge_point_id = None
    user_id = None
    if invoice.order_id:
        order = db.query(Order).filter(Order.id == invoice.order_id).first()
        if order:
            charge_point_id = order.charge_point_id
            user_id = order.user_id
    
    return InvoiceDetailResponse(
        id=invoice.id,
        tenant_id=invoice.tenant_id,
        order_id=invoice.order_id,
        session_id=invoice.session_id,
        energy_kwh=float(invoice.energy_kwh),
        duration_minutes=float(invoice.duration_minutes),
        total_amount=float(invoice.total_amount),
        status=invoice.status,
        issued_at=invoice.issued_at,
        paid_at=invoice.paid_at,
        charge_point_id=charge_point_id,
        user_id=user_id,
        payment_method=payment.payment_method if payment else None,
        payment_status=payment.status if payment else None
    )


@router.get("/reports/revenue", summary="收入报表")
async def get_revenue_report(
    period: str = Query("day", description="统计周期: day, month, year"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    request: Request,
    current_user = Depends(require_permission("finance:report:view")),
    db: Session = Depends(get_db)
):
    """
    获取收入报表
    
    - 支持按日/月/年统计
    - 支持日期范围筛选
    """
    tenant_id = get_tenant_id(request)
    
    query = db.query(Invoice)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Invoice.tenant_id == tenant_id)
    
    # 日期范围
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        query = query.filter(Invoice.issued_at >= start_dt)
    else:
        # 默认最近30天
        start_dt = datetime.now(timezone.utc) - timedelta(days=30)
        query = query.filter(Invoice.issued_at >= start_dt)
    
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
        query = query.filter(Invoice.issued_at <= end_dt)
    
    # 按周期聚合
    if period == "day":
        results = query.with_entities(
            func.date(Invoice.issued_at).label("date"),
            func.sum(Invoice.total_amount).label("revenue")
        ).group_by(func.date(Invoice.issued_at)).order_by("date").all()
    elif period == "month":
        results = query.with_entities(
            func.date_trunc("month", Invoice.issued_at).label("date"),
            func.sum(Invoice.total_amount).label("revenue")
        ).group_by(func.date_trunc("month", Invoice.issued_at)).order_by("date").all()
    else:  # year
        results = query.with_entities(
            func.date_trunc("year", Invoice.issued_at).label("date"),
            func.sum(Invoice.total_amount).label("revenue")
        ).group_by(func.date_trunc("year", Invoice.issued_at)).order_by("date").all()
    
    return [
        {
            "date": str(result.date),
            "revenue": round(float(result.revenue), 2)
        }
        for result in results
    ]


@router.get("/reports/export", summary="导出财务报表")
async def export_finance_report(
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    request: Request,
    current_user = Depends(require_permission("finance:report:export")),
    db: Session = Depends(get_db)
):
    """导出财务报表（CSV格式）"""
    from fastapi.responses import StreamingResponse
    import csv
    import io
    
    tenant_id = get_tenant_id(request)
    
    query = db.query(Invoice)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Invoice.tenant_id == tenant_id)
    
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        query = query.filter(Invoice.issued_at >= start_dt)
    
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
        query = query.filter(Invoice.issued_at <= end_dt)
    
    invoices = query.order_by(desc(Invoice.issued_at)).all()
    
    # 生成CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "发票ID", "订单ID", "充电量(kWh)", "时长(分钟)", "金额", "状态", "开票时间", "支付时间"
    ])
    
    for invoice in invoices:
        writer.writerow([
            invoice.id,
            invoice.order_id or "",
            float(invoice.energy_kwh),
            float(invoice.duration_minutes),
            float(invoice.total_amount),
            invoice.status,
            invoice.issued_at.isoformat() if invoice.issued_at else "",
            invoice.paid_at.isoformat() if invoice.paid_at else ""
        ])
    
    output.seek(0)
    filename = f"finance_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
