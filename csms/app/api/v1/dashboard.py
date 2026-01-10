#
# 仪表板API
# 提供运营数据总览和关键指标
#

from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, timezone, timedelta

from app.database.base import get_db
from app.database.models import (
    ChargePoint, EVSEStatus, Order, Invoice, 
    ChargingSession, Site, EndUser, Alert
)
from app.core.permissions import get_current_admin_user
from app.database.base import tenant_id_context
from fastapi import Request, Depends

router = APIRouter(tags=["仪表板"])  # prefix 在 __init__.py 中统一设置


# ==================== 响应模型 ====================

class DashboardSummaryResponse(BaseModel):
    """仪表板总览响应"""
    # 设备统计
    total_charge_points: int
    online_charge_points: int
    offline_charge_points: int
    faulted_charge_points: int
    charging_charge_points: int
    available_charge_points: int
    
    # 站点统计
    total_sites: int
    active_sites: int
    
    # 订单统计
    today_orders: int
    today_energy_kwh: float
    today_revenue: float
    
    # 用户统计
    total_users: int
    active_users_today: int
    
    # 告警统计
    critical_alerts: int
    warning_alerts: int
    info_alerts: int


class TrendDataPoint(BaseModel):
    """趋势数据点"""
    date: str
    value: float


class DashboardTrendsResponse(BaseModel):
    """仪表板趋势数据响应"""
    energy_trend: List[TrendDataPoint]  # 充电量趋势
    revenue_trend: List[TrendDataPoint]  # 收入趋势
    orders_trend: List[TrendDataPoint]  # 订单趋势


# ==================== 仪表板端点 ====================

@router.get("/summary", response_model=DashboardSummaryResponse, summary="获取仪表板总览")
async def get_dashboard_summary(
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取仪表板总览数据
    
    - 设备统计（总数、在线、离线、故障、充电中、可用）
    - 站点统计
    - 今日订单、充电量、收入
    - 用户统计
    - 告警统计
    """
    tenant_id = tenant_id_context.get()
    
    # 构建基础查询（多租户过滤）
    # RLS 会自动过滤，但为了性能，我们也在应用层添加过滤
    charge_point_query = db.query(ChargePoint)
    if tenant_id and not current_user.is_super_admin:
        charge_point_query = charge_point_query.filter(ChargePoint.tenant_id == tenant_id)
    
    site_query = db.query(Site)
    if tenant_id and not current_user.is_super_admin:
        site_query = site_query.filter(Site.tenant_id == tenant_id)
    
    order_query = db.query(Order)
    if tenant_id and not current_user.is_super_admin:
        order_query = order_query.filter(Order.tenant_id == tenant_id)
    
    invoice_query = db.query(Invoice)
    if tenant_id and not current_user.is_super_admin:
        invoice_query = invoice_query.filter(Invoice.tenant_id == tenant_id)
    
    user_query = db.query(EndUser)
    if tenant_id and not current_user.is_super_admin:
        user_query = user_query.filter(EndUser.tenant_id == tenant_id)
    
    alert_query = db.query(Alert)
    if tenant_id and not current_user.is_super_admin:
        alert_query = alert_query.filter(Alert.tenant_id == tenant_id)
    
    # 设备统计
    total_charge_points = charge_point_query.filter(ChargePoint.is_active == True).count()
    
    # 获取EVSE状态统计
    evse_status_query = db.query(EVSEStatus).join(ChargePoint)
    if tenant_id and not current_user.is_super_admin:
        evse_status_query = evse_status_query.filter(ChargePoint.tenant_id == tenant_id)
    
    # 在线充电桩（最近30秒内有心跳）
    now = datetime.now(timezone.utc)
    online_threshold = now - timedelta(seconds=30)
    online_charge_points = evse_status_query.filter(
        EVSEStatus.last_seen >= online_threshold
    ).distinct(EVSEStatus.charge_point_id).count()
    
    offline_charge_points = total_charge_points - online_charge_points
    
    # 状态统计
    status_counts = evse_status_query.with_entities(
        EVSEStatus.status, func.count(func.distinct(EVSEStatus.charge_point_id))
    ).group_by(EVSEStatus.status).all()
    
    status_dict = {status: count for status, count in status_counts}
    faulted_charge_points = status_dict.get("Faulted", 0)
    charging_charge_points = status_dict.get("Charging", 0)
    available_charge_points = status_dict.get("Available", 0)
    
    # 站点统计
    total_sites = site_query.filter(Site.is_active == True).count()
    active_sites = total_sites  # 简化处理，实际可以根据充电桩活动判断
    
    # 今日订单统计
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_orders = order_query.filter(Order.created_at >= today_start).count()
    
    # 今日充电量和收入
    today_invoices = invoice_query.filter(Invoice.issued_at >= today_start).all()
    today_energy_kwh = sum(float(inv.energy_kwh) for inv in today_invoices)
    today_revenue = sum(float(inv.total_amount) for inv in today_invoices)
    
    # 用户统计
    total_users = user_query.count()
    active_users_today = user_query.filter(
        EndUser.last_login_at >= today_start
    ).count()
    
    # 告警统计
    critical_alerts = alert_query.filter(
        and_(
            Alert.severity == "critical",
            Alert.status == "pending"
        )
    ).count()
    
    warning_alerts = alert_query.filter(
        and_(
            Alert.severity == "warning",
            Alert.status == "pending"
        )
    ).count()
    
    info_alerts = alert_query.filter(
        and_(
            Alert.severity == "info",
            Alert.status == "pending"
        )
    ).count()
    
    return DashboardSummaryResponse(
        total_charge_points=total_charge_points,
        online_charge_points=online_charge_points,
        offline_charge_points=offline_charge_points,
        faulted_charge_points=faulted_charge_points,
        charging_charge_points=charging_charge_points,
        available_charge_points=available_charge_points,
        total_sites=total_sites,
        active_sites=active_sites,
        today_orders=today_orders,
        today_energy_kwh=round(today_energy_kwh, 2),
        today_revenue=round(today_revenue, 2),
        total_users=total_users,
        active_users_today=active_users_today,
        critical_alerts=critical_alerts,
        warning_alerts=warning_alerts,
        info_alerts=info_alerts
    )


@router.get("/trends", response_model=DashboardTrendsResponse, summary="获取趋势数据")
async def get_dashboard_trends(
    days: int = Query(7, description="天数", ge=1, le=30),
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取趋势数据
    
    - 充电量趋势（过去N天）
    - 收入趋势（过去N天）
    - 订单趋势（过去N天）
    """
    tenant_id = tenant_id_context.get()
    
    # 计算日期范围
    end_date = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59)
    start_date = (end_date - timedelta(days=days)).replace(hour=0, minute=0, second=0)
    
    # 构建查询
    invoice_query = db.query(Invoice)
    if tenant_id and not current_user.is_super_admin:
        invoice_query = invoice_query.filter(Invoice.tenant_id == tenant_id)
    
    order_query = db.query(Order)
    if tenant_id and not current_user.is_super_admin:
        order_query = order_query.filter(Order.tenant_id == tenant_id)
    
    # 按日期聚合数据
    energy_trend = []
    revenue_trend = []
    orders_trend = []
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        next_date = current_date + timedelta(days=1)
        
        # 充电量
        day_invoices = invoice_query.filter(
            and_(
                Invoice.issued_at >= current_date,
                Invoice.issued_at < next_date
            )
        ).all()
        day_energy = sum(float(inv.energy_kwh) for inv in day_invoices)
        energy_trend.append(TrendDataPoint(date=date_str, value=round(day_energy, 2)))
        
        # 收入
        day_revenue = sum(float(inv.total_amount) for inv in day_invoices)
        revenue_trend.append(TrendDataPoint(date=date_str, value=round(day_revenue, 2)))
        
        # 订单数
        day_orders = order_query.filter(
            and_(
                Order.created_at >= current_date,
                Order.created_at < next_date
            )
        ).count()
        orders_trend.append(TrendDataPoint(date=date_str, value=float(day_orders)))
        
        current_date = next_date
    
    return DashboardTrendsResponse(
        energy_trend=energy_trend,
        revenue_trend=revenue_trend,
        orders_trend=orders_trend
    )
