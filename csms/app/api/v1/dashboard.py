#
# 仪表板API
# 提供运营数据总览和关键指标
#

from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.database.base import get_db
from app.database.models import (
    ChargePoint, EVSEStatus, Order, Invoice, 
    ChargingSession, Site, EndUser, Alert
)
from app.core.permissions import get_current_admin_user
from app.database.base import tenant_id_context
from fastapi import Request, Depends
from app.core.logging_config import get_logger

router = APIRouter(tags=["仪表板"])  # prefix 在 __init__.py 中统一设置

logger = get_logger("ocpp_csms")


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
    today_revenue: Decimal
    
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


class DashboardSiteItem(BaseModel):
    """站点维度运营汇总（用于仪表盘站点分析）"""

    site_id: str
    site_name: str
    address: Optional[str] = None

    charge_points_count: int
    online_charge_points_count: int

    faulted_charge_points: int
    charging_charge_points: int
    available_charge_points: int

    orders_count: int
    energy_kwh: float
    revenue: Decimal


# ==================== 仪表板端点 ====================

@router.get("/summary", response_model=DashboardSummaryResponse, summary="获取仪表板总览")
async def get_dashboard_summary(
    request: Request,
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
    # 获取 tenant_id（super_admin 可能为 None）
    try:
        tenant_id = tenant_id_context.get()
    except LookupError:
        tenant_id = None
    
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
    # 注意：某些部署的 end_users 表可能缺少模型中的部分字段（例如 password_hash）。
    # 使用 count(EndUser.id) 避免 ORM 在子查询中选择所有列导致 UndefinedColumn。
    total_users_q = db.query(func.count(EndUser.id))
    if tenant_id and not current_user.is_super_admin:
        total_users_q = total_users_q.filter(EndUser.tenant_id == tenant_id)
    total_users = int(total_users_q.scalar() or 0)

    active_users_today_q = db.query(func.count(EndUser.id)).filter(EndUser.last_login_at >= today_start)
    if tenant_id and not current_user.is_super_admin:
        active_users_today_q = active_users_today_q.filter(EndUser.tenant_id == tenant_id)
    active_users_today = int(active_users_today_q.scalar() or 0)
    
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
    request: Request,
    days: int = Query(7, description="天数", ge=1, le=30),
    site_id: Optional[str] = Query(None, description="站点ID（可选）：按站点过滤趋势数据"),
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取趋势数据
    
    - 充电量趋势（过去N天）
    - 收入趋势（过去N天）
    - 订单趋势（过去N天）
    """
    # 获取 tenant_id（super_admin 可能为 None）
    try:
        tenant_id = tenant_id_context.get()
    except LookupError:
        tenant_id = None
    
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

    # 站点过滤：Invoice 通过 session -> charge_point -> site 关联；Order 通过 charge_point_id -> site 关联
    if site_id:
        invoice_query = (
            invoice_query.join(ChargingSession, ChargingSession.id == Invoice.session_id)
            .join(ChargePoint, ChargePoint.id == ChargingSession.charge_point_id)
            .filter(ChargePoint.site_id == site_id)
        )
        order_query = (
            order_query.join(ChargePoint, ChargePoint.id == Order.charge_point_id)
            .filter(ChargePoint.site_id == site_id)
        )
    
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


@router.get("/sites", response_model=List[DashboardSiteItem], summary="获取站点维度运营汇总")
async def get_dashboard_sites(
    request: Request,
    days: int = Query(7, description="统计窗口天数（近 N 天）", ge=1, le=30),
    limit: int = Query(50, description="返回站点数量上限", ge=1, le=200),
    current_user=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> List[DashboardSiteItem]:
    """
    站点维度汇总（用于 Admin 仪表盘按站点分析）：
    - 站点下充电桩数量（charge_points_count）
    - 在线充电桩数量（online_charge_points_count，近 30 秒有心跳）
    - 站点健康：Faulted/Charging/Available（按 EVSEStatus 统计 distinct charge_point）
    - 近 N 天：订单数、充电量(kWh)、收入
    """
    # #region agent log
    x_tenant_id_header = request.headers.get("X-Tenant-Id") or request.headers.get("x-tenant-id")
    logger.info(
        f"[DEBUG] /dashboard/sites ENTRY - method={request.method}, path={request.url.path}, "
        f"X-Tenant-Id={x_tenant_id_header}, current_user_id={current_user.id if current_user else None}, "
        f"is_super_admin={current_user.is_super_admin if current_user else None}, days={days}, limit={limit}"
    )
    # #endregion

    try:
        tenant_id = tenant_id_context.get()
    except LookupError:
        tenant_id = None

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    online_threshold = now - timedelta(seconds=30)

    # 站点基础查询
    site_q = db.query(Site).filter(Site.is_active == True)  # noqa: E712
    if tenant_id and not current_user.is_super_admin:
        site_q = site_q.filter(Site.tenant_id == tenant_id)

    # 站点下充电桩数量
    cp_count_sq = (
        db.query(
            ChargePoint.site_id.label("site_id"),
            func.count(ChargePoint.id).label("cp_count"),
        )
        .filter(ChargePoint.is_active == True)  # noqa: E712
        .group_by(ChargePoint.site_id)
        .subquery()
    )

    # 在线充电桩数量（近 30 秒心跳）
    online_cp_sq = (
        db.query(
            ChargePoint.site_id.label("site_id"),
            func.count(func.distinct(ChargePoint.id)).label("online_cp_count"),
        )
        .join(EVSEStatus, EVSEStatus.charge_point_id == ChargePoint.id)
        .filter(EVSEStatus.last_seen >= online_threshold)
        .group_by(ChargePoint.site_id)
        .subquery()
    )

    # 健康状态：Faulted / Charging / Available（distinct charge_point）
    faulted_sq = (
        db.query(
            ChargePoint.site_id.label("site_id"),
            func.count(func.distinct(ChargePoint.id)).label("faulted_cp_count"),
        )
        .join(EVSEStatus, EVSEStatus.charge_point_id == ChargePoint.id)
        .filter(EVSEStatus.last_seen >= online_threshold, EVSEStatus.status == "Faulted")
        .group_by(ChargePoint.site_id)
        .subquery()
    )
    charging_sq = (
        db.query(
            ChargePoint.site_id.label("site_id"),
            func.count(func.distinct(ChargePoint.id)).label("charging_cp_count"),
        )
        .join(EVSEStatus, EVSEStatus.charge_point_id == ChargePoint.id)
        .filter(EVSEStatus.last_seen >= online_threshold, EVSEStatus.status == "Charging")
        .group_by(ChargePoint.site_id)
        .subquery()
    )
    available_sq = (
        db.query(
            ChargePoint.site_id.label("site_id"),
            func.count(func.distinct(ChargePoint.id)).label("available_cp_count"),
        )
        .join(EVSEStatus, EVSEStatus.charge_point_id == ChargePoint.id)
        .filter(EVSEStatus.last_seen >= online_threshold, EVSEStatus.status == "Available")
        .group_by(ChargePoint.site_id)
        .subquery()
    )

    # 近 N 天订单数（按站点聚合）
    orders_sq = (
        db.query(
            ChargePoint.site_id.label("site_id"),
            func.count(Order.id).label("orders_count"),
        )
        .join(ChargePoint, ChargePoint.id == Order.charge_point_id)
        .filter(Order.created_at >= start_date)
        .group_by(ChargePoint.site_id)
        .subquery()
    )

    # 近 N 天电量/收入（Invoice -> Session -> ChargePoint -> Site）
    invoice_sq = (
        db.query(
            ChargePoint.site_id.label("site_id"),
            func.coalesce(func.sum(Invoice.energy_kwh), 0).label("energy_kwh"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("revenue"),
        )
        .join(ChargingSession, ChargingSession.id == Invoice.session_id)
        .join(ChargePoint, ChargePoint.id == ChargingSession.charge_point_id)
        .filter(Invoice.issued_at >= start_date)
        .group_by(ChargePoint.site_id)
        .subquery()
    )

    rows = (
        site_q.outerjoin(cp_count_sq, cp_count_sq.c.site_id == Site.id)
        .outerjoin(online_cp_sq, online_cp_sq.c.site_id == Site.id)
        .outerjoin(faulted_sq, faulted_sq.c.site_id == Site.id)
        .outerjoin(charging_sq, charging_sq.c.site_id == Site.id)
        .outerjoin(available_sq, available_sq.c.site_id == Site.id)
        .outerjoin(orders_sq, orders_sq.c.site_id == Site.id)
        .outerjoin(invoice_sq, invoice_sq.c.site_id == Site.id)
        .with_entities(
            Site,
            cp_count_sq.c.cp_count,
            online_cp_sq.c.online_cp_count,
            faulted_sq.c.faulted_cp_count,
            charging_sq.c.charging_cp_count,
            available_sq.c.available_cp_count,
            orders_sq.c.orders_count,
            invoice_sq.c.energy_kwh,
            invoice_sq.c.revenue,
        )
        .order_by(invoice_sq.c.revenue.desc().nullslast(), Site.created_at.desc())
        .limit(limit)
        .all()
    )

    result: List[DashboardSiteItem] = []
    for (
        site,
        cp_count,
        online_cp_count,
        faulted_cp_count,
        charging_cp_count,
        available_cp_count,
        orders_count,
        energy_kwh,
        revenue,
    ) in rows:
        # Numeric/Decimal -> float
        energy_f = float(energy_kwh or 0)
        revenue_f = float(revenue or 0)

        result.append(
            DashboardSiteItem(
                site_id=site.id,
                site_name=site.name,
                address=site.address,
                charge_points_count=int(cp_count or 0),
                online_charge_points_count=int(online_cp_count or 0),
                faulted_charge_points=int(faulted_cp_count or 0),
                charging_charge_points=int(charging_cp_count or 0),
                available_charge_points=int(available_cp_count or 0),
                orders_count=int(orders_count or 0),
                energy_kwh=round(energy_f, 3),
                revenue=round(revenue_f, 2),
            )
        )

    return result
