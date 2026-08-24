#
# 统计报表API
# 提供各种统计报表和数据分析功能
#

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Literal, Optional
from uuid import UUID
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
from app.database.base import get_db, tenant_id_context, is_super_admin_context
from app.core.permissions import get_current_admin_user
from app.services.report_service import ReportService
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class RevenueDataPoint(BaseModel):
    date: str
    total_revenue: str
    total_energy_kwh: str
    invoice_count: int
    currency: str


class EnergyDataPoint(BaseModel):
    date: str
    total_energy_kwh: str
    session_count: int


class OrdersDataPoint(BaseModel):
    date: str
    order_count: int
    completed_count: int


def _resolve_report_range(
    *,
    days: int,
    start_date: Optional[date],
    end_date: Optional[date],
) -> tuple[datetime, datetime]:
    """Return a UTC left-closed/right-open report range."""
    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=422,
            detail="start_date and end_date must be provided together",
        )

    if start_date is not None and end_date is not None:
        if start_date > end_date:
            raise HTTPException(
                status_code=422,
                detail="start_date must be on or before end_date",
            )
        range_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        range_end = datetime.combine(
            end_date + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
        return range_start, range_end

    today = datetime.now(timezone.utc).date()
    range_end = datetime.combine(
        today + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )
    return range_end - timedelta(days=days), range_end


def _resolve_tenant_site(
    db: Session,
    *,
    tenant_id: Optional[UUID],
    site_id: Optional[str],
) -> Optional[UUID]:
    """Resolve a public site code or UUID without leaking another tenant's site."""
    if not site_id:
        return None
    if not tenant_id:
        raise HTTPException(
            status_code=422,
            detail="site_id requires a tenant scope",
        )

    from app.database.models import Site

    query = db.query(Site.id).filter(Site.tenant_id == tenant_id)
    try:
        internal_id = UUID(site_id)
    except (TypeError, ValueError):
        site = query.filter(Site.site_code == site_id).first()
    else:
        site = query.filter(Site.id == internal_id).first()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site.id


def _decimal_text(value, places: str) -> str:
    return format(Decimal(str(value or 0)).quantize(Decimal(places)), "f")


# ==================== 统计端点 ====================

@router.get("/overview", summary="获取总览统计")
async def get_overview(
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """获取总览统计（使用dashboard API）"""
    # 这个可以复用 dashboard API
    from app.api.v1.dashboard import get_dashboard_summary
    return await get_dashboard_summary(
        current_user=current_user_obj,
        db=db
    )


@router.get("/revenue", response_model=List[RevenueDataPoint], summary="获取收入统计")
async def get_revenue_statistics(
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    site_id: Optional[str] = Query(None, min_length=1, max_length=100),
    group_by: Literal["day"] = Query("day", description="分组方式: day"),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取收入统计
    
    - 普通管理员：查询指定租户数据（必须提供 X-Tenant-Id）
    - 超级管理员：
      - 提供 X-Tenant-Id：查询指定租户
      - 不提供 X-Tenant-Id：查询所有租户的汇总数据
    """
    tenant_id = tenant_id_context.get()
    is_super_admin = is_super_admin_context.get()
    
    # 非超级管理员必须提供 tenant_id
    if not tenant_id and not is_super_admin:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    range_start, range_end = _resolve_report_range(
        days=days,
        start_date=start_date,
        end_date=end_date,
    )
    resolved_site_id = _resolve_tenant_site(
        db,
        tenant_id=tenant_id,
        site_id=site_id,
    )
    
    # 根据是否有 tenant_id 决定查询方式
    if tenant_id:
        # 查询特定租户
        data = ReportService.get_revenue_report(
            db=db,
            tenant_id=tenant_id,
            start_date=range_start,
            end_date=range_end,
            group_by=group_by,
            site_id=resolved_site_id,
        )
    else:
        # 超级管理员查询所有租户（汇总）
        data = ReportService.get_all_tenants_revenue_report(
            db=db,
            start_date=range_start,
            end_date=range_end,
            group_by=group_by
        )
    
    return [
        RevenueDataPoint(
            date=d["date"],
            total_revenue=_decimal_text(d["total_revenue"], "0.01"),
            total_energy_kwh=_decimal_text(d["total_energy_kwh"], "0.001"),
            invoice_count=d["invoice_count"],
            currency=d.get("currency", "COP"),
        )
        for d in data
    ]


@router.get("/energy", response_model=List[EnergyDataPoint], summary="获取充电量统计")
async def get_energy_statistics(
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    site_id: Optional[str] = Query(None, min_length=1, max_length=100),
    group_by: Literal["day"] = Query("day", description="分组方式: day"),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取充电量统计
    
    - 超级管理员不提供 X-Tenant-Id 时：查询所有租户汇总数据
    """
    tenant_id = tenant_id_context.get()
    is_super_admin = is_super_admin_context.get()
    
    if not tenant_id and not is_super_admin:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    range_start, range_end = _resolve_report_range(
        days=days,
        start_date=start_date,
        end_date=end_date,
    )
    resolved_site_id = _resolve_tenant_site(
        db,
        tenant_id=tenant_id,
        site_id=site_id,
    )
    
    if tenant_id:
        data = ReportService.get_energy_report(
            db=db,
            tenant_id=tenant_id,
            start_date=range_start,
            end_date=range_end,
            group_by=group_by,
            site_id=resolved_site_id,
        )
    else:
        data = ReportService.get_all_tenants_energy_report(
            db=db,
            start_date=range_start,
            end_date=range_end,
            group_by=group_by
        )
    
    return [
        EnergyDataPoint(
            date=d["date"],
            total_energy_kwh=_decimal_text(d["total_energy_kwh"], "0.001"),
            session_count=d["session_count"]
        )
        for d in data
    ]


@router.get("/orders", response_model=List[OrdersDataPoint], summary="获取订单统计")
async def get_orders_statistics(
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    site_id: Optional[str] = Query(None, min_length=1, max_length=100),
    group_by: Literal["day"] = Query("day", description="分组方式: day"),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取订单统计
    
    - 超级管理员不提供 X-Tenant-Id 时：查询所有租户汇总数据
    """
    tenant_id = tenant_id_context.get()
    is_super_admin = is_super_admin_context.get()
    
    if not tenant_id and not is_super_admin:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    range_start, range_end = _resolve_report_range(
        days=days,
        start_date=start_date,
        end_date=end_date,
    )
    resolved_site_id = _resolve_tenant_site(
        db,
        tenant_id=tenant_id,
        site_id=site_id,
    )
    
    if tenant_id:
        data = ReportService.get_orders_report(
            db=db,
            tenant_id=tenant_id,
            start_date=range_start,
            end_date=range_end,
            group_by=group_by,
            site_id=resolved_site_id,
        )
    else:
        data = ReportService.get_all_tenants_orders_report(
            db=db,
            start_date=range_start,
            end_date=range_end,
            group_by=group_by
        )
    
    return [
        OrdersDataPoint(
            date=d["date"],
            order_count=d["order_count"],
            completed_count=d["completed_count"]
        )
        for d in data
    ]


@router.get("/users", summary="获取用户统计")
async def get_users_statistics(
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取用户统计
    
    - 超级管理员不提供 X-Tenant-Id 时：查询所有租户汇总数据
    """
    tenant_id = tenant_id_context.get()
    is_super_admin = is_super_admin_context.get()
    
    if not tenant_id and not is_super_admin:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    if tenant_id:
        return ReportService.get_user_statistics(db, tenant_id)
    else:
        return ReportService.get_all_tenants_user_statistics(db)


@router.get("/charge-points", summary="获取设备统计")
async def get_charge_points_statistics(
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取设备统计
    
    - 超级管理员不提供 X-Tenant-Id 时：查询所有租户汇总数据
    """
    tenant_id = tenant_id_context.get()
    is_super_admin = is_super_admin_context.get()
    
    if not tenant_id and not is_super_admin:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    if tenant_id:
        return ReportService.get_charge_point_statistics(db, tenant_id)
    else:
        return ReportService.get_all_tenants_charge_point_statistics(db)


@router.get("/trends", summary="获取趋势数据")
async def get_trends(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """获取趋势数据（复用dashboard API）"""
    from app.api.v1.dashboard import get_dashboard_trends
    return await get_dashboard_trends(
        days=days,
        current_user=current_user_obj,
        db=db
    )


@router.get("/export", summary="导出报表")
async def export_report(
    report_type: Literal["revenue", "energy", "orders"] = Query(...),
    days: int = Query(30, ge=1, le=365),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    site_id: Optional[str] = Query(None, min_length=1, max_length=100),
    group_by: Literal["day"] = Query("day"),
    format: Literal["csv"] = Query("csv"),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """导出报表"""
    tenant_id = tenant_id_context.get()
    is_super_admin = is_super_admin_context.get()
    if not tenant_id and not is_super_admin:
        raise HTTPException(status_code=403, detail="Tenant ID required")

    range_start, range_end = _resolve_report_range(
        days=days,
        start_date=start_date,
        end_date=end_date,
    )
    resolved_site_id = _resolve_tenant_site(
        db,
        tenant_id=tenant_id,
        site_id=site_id,
    )
    
    if tenant_id:
        file_content = ReportService.export_report(
            db=db,
            tenant_id=tenant_id,
            report_type=report_type,
            start_date=range_start,
            end_date=range_end,
            format=format,
            site_id=resolved_site_id,
        )
    else:
        file_content = ReportService.export_all_tenants_report(
            db=db,
            report_type=report_type,
            start_date=range_start,
            end_date=range_end,
            format=format,
        )
    
    from fastapi.responses import Response
    
    filename_end = (range_end - timedelta(days=1)).date()
    return Response(
        content=file_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=report_{report_type}_"
                f"{range_start.date()}_{filename_end}.csv"
            )
        }
    )
