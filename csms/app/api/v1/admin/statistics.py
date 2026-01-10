#
# 统计报表API
# 提供各种统计报表和数据分析功能
#

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from app.database.base import get_db, tenant_id_context, is_super_admin_context
from app.core.permissions import get_current_admin_user
from app.services.report_service import ReportService
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class RevenueDataPoint(BaseModel):
    date: str
    total_revenue: float
    total_energy_kwh: float
    invoice_count: int


class EnergyDataPoint(BaseModel):
    date: str
    total_energy_kwh: float
    session_count: int


class OrdersDataPoint(BaseModel):
    date: str
    order_count: int
    completed_count: int


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
    days: int = Query(7, ge=1, le=365, description="查询天数"),
    group_by: str = Query("day", description="分组方式: day, week, month"),
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
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # 根据是否有 tenant_id 决定查询方式
    if tenant_id:
        # 查询特定租户
        data = ReportService.get_revenue_report(
            db=db,
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
    else:
        # 超级管理员查询所有租户（汇总）
        data = ReportService.get_all_tenants_revenue_report(
            db=db,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
    
    return [
        RevenueDataPoint(
            date=d["date"],
            total_revenue=d["total_revenue"],
            total_energy_kwh=d["total_energy_kwh"],
            invoice_count=d["invoice_count"]
        )
        for d in data
    ]


@router.get("/energy", response_model=List[EnergyDataPoint], summary="获取充电量统计")
async def get_energy_statistics(
    days: int = Query(7, ge=1, le=365, description="查询天数"),
    group_by: str = Query("day", description="分组方式: day, week, month"),
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
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    if tenant_id:
        data = ReportService.get_energy_report(
            db=db,
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
    else:
        data = ReportService.get_all_tenants_energy_report(
            db=db,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
    
    return [
        EnergyDataPoint(
            date=d["date"],
            total_energy_kwh=d["total_energy_kwh"],
            session_count=d["session_count"]
        )
        for d in data
    ]


@router.get("/orders", response_model=List[OrdersDataPoint], summary="获取订单统计")
async def get_orders_statistics(
    days: int = Query(7, ge=1, le=365, description="查询天数"),
    group_by: str = Query("day", description="分组方式: day, week, month"),
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
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    if tenant_id:
        data = ReportService.get_orders_report(
            db=db,
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
    else:
        data = ReportService.get_all_tenants_orders_report(
            db=db,
            start_date=start_date,
            end_date=end_date,
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
    report_type: str = Query(..., description="报表类型: revenue, energy, orders"),
    days: int = Query(30, ge=1, le=365),
    format: str = Query("csv", description="导出格式: csv, excel, json"),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """导出报表"""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    file_content = ReportService.export_report(
        db=db,
        tenant_id=tenant_id,
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        format=format
    )
    
    from fastapi.responses import Response
    
    content_type_map = {
        "csv": "text/csv",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "json": "application/json"
    }
    
    return Response(
        content=file_content,
        media_type=content_type_map.get(format, "application/octet-stream"),
        headers={
            "Content-Disposition": f"attachment; filename=report_{report_type}_{start_date.date()}_{end_date.date()}.{format}"
        }
    )
