#
# 充电站管理API
# 提供站点的CRUD和运营统计功能
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from datetime import datetime, timezone, timedelta

from app.database.base import get_db
from app.database.models import Site, ChargePoint, Order, Invoice, Tenant, ChargingSession
from app.core.auth import get_current_admin_user, require_permission, get_tenant_filter
from app.core.tenant_middleware import get_tenant_id
from app.core.exceptions import PermissionDenied
from app.core.id_generator import generate_site_id
from fastapi import Request

router = APIRouter(prefix="/sites", tags=["充电站管理"])


# ==================== 请求/响应模型 ====================

class SiteResponse(BaseModel):
    """站点响应"""
    id: str
    tenant_id: Optional[str]
    name: str
    address: str
    latitude: float
    longitude: float
    is_active: bool
    operating_hours: Optional[str]
    charge_point_count: int = 0
    online_charge_points: int = 0
    today_energy_kwh: float = 0.0
    today_revenue: float = 0.0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SiteCreateRequest(BaseModel):
    """创建站点请求"""
    name: str
    address: str
    latitude: float
    longitude: float
    operating_hours: Optional[str] = None


class SiteUpdateRequest(BaseModel):
    """更新站点请求"""
    name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = None
    operating_hours: Optional[str] = None


class SiteDetailResponse(SiteResponse):
    """站点详情响应"""
    charge_points: List[dict] = []


# ==================== 站点管理端点 ====================

@router.get("", response_model=List[SiteResponse], summary="获取站点列表")
async def get_sites(
    is_active: Optional[bool] = Query(None, description="按状态筛选"),
    request: Request,
    current_user = Depends(require_permission("sites:view")),
    db: Session = Depends(get_db)
):
    """
    获取站点列表
    
    - 支持按状态筛选
    - 自动应用租户过滤
    """
    tenant_id = get_tenant_id(request)
    
    query = db.query(Site)
    
    # 多租户过滤
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Site.tenant_id == tenant_id)
    
    if is_active is not None:
        query = query.filter(Site.is_active == is_active)
    
    sites = query.order_by(desc(Site.created_at)).all()
    
    # 构建响应（包含统计信息）
    result = []
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    for site in sites:
        # 统计充电桩数量
        cp_query = db.query(ChargePoint).filter(ChargePoint.site_id == site.id)
        charge_point_count = cp_query.count()
        
        # 统计在线充电桩（通过EVSE状态）
        from app.database.models import EVSEStatus
        online_cp_ids = db.query(EVSEStatus.charge_point_id).join(ChargePoint).filter(
            and_(
                ChargePoint.site_id == site.id,
                EVSEStatus.last_seen >= datetime.now(timezone.utc) - timedelta(seconds=30)
            )
        ).distinct().all()
        online_charge_points = len(online_cp_ids)
        
        # 今日充电量和收入
        today_invoices = db.query(Invoice).join(ChargingSession).join(ChargePoint).filter(
            and_(
                ChargePoint.site_id == site.id,
                Invoice.issued_at >= today_start
            )
        ).all()
        today_energy_kwh = sum(float(inv.energy_kwh) for inv in today_invoices)
        today_revenue = sum(float(inv.total_amount) for inv in today_invoices)
        
        result.append(SiteResponse(
            id=site.id,
            tenant_id=site.tenant_id,
            name=site.name,
            address=site.address,
            latitude=site.latitude,
            longitude=site.longitude,
            is_active=site.is_active,
            operating_hours=site.operating_hours,
            charge_point_count=charge_point_count,
            online_charge_points=online_charge_points,
            today_energy_kwh=round(today_energy_kwh, 2),
            today_revenue=round(today_revenue, 2),
            created_at=site.created_at,
            updated_at=site.updated_at
        ))
    
    return result


@router.get("/{site_id}", response_model=SiteDetailResponse, summary="获取站点详情")
async def get_site(
    site_id: str,
    request: Request,
    current_user = Depends(require_permission("sites:view")),
    db: Session = Depends(get_db)
):
    """获取站点详情"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Site).filter(Site.id == site_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Site.tenant_id == tenant_id)
    
    site = query.first()
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="站点不存在"
        )
    
    # 获取充电桩列表
    charge_points = db.query(ChargePoint).filter(ChargePoint.site_id == site_id).all()
    cp_list = []
    for cp in charge_points:
        from app.database.models import EVSEStatus
        evse_status = db.query(EVSEStatus).filter(
            EVSEStatus.charge_point_id == cp.id
        ).first()
        
        cp_list.append({
            "id": cp.id,
            "vendor": cp.vendor,
            "model": cp.model,
            "status": evse_status.status if evse_status else "Unknown",
            "last_seen": evse_status.last_seen.isoformat() if evse_status and evse_status.last_seen else None
        })
    
    # 统计信息
    charge_point_count = len(charge_points)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_invoices = db.query(Invoice).join(ChargingSession).join(ChargePoint).filter(
        and_(
            ChargePoint.site_id == site.id,
            Invoice.issued_at >= today_start
        )
    ).all()
    today_energy_kwh = sum(float(inv.energy_kwh) for inv in today_invoices)
    today_revenue = sum(float(inv.total_amount) for inv in today_invoices)
    
    return SiteDetailResponse(
        id=site.id,
        tenant_id=site.tenant_id,
        name=site.name,
        address=site.address,
        latitude=site.latitude,
        longitude=site.longitude,
        is_active=site.is_active,
        operating_hours=site.operating_hours,
        charge_point_count=charge_point_count,
        online_charge_points=charge_point_count,  # 简化处理
        today_energy_kwh=round(today_energy_kwh, 2),
        today_revenue=round(today_revenue, 2),
        created_at=site.created_at,
        updated_at=site.updated_at,
        charge_points=cp_list
    )


@router.post("", response_model=SiteResponse, summary="创建站点")
async def create_site(
    site_data: SiteCreateRequest,
    request: Request,
    current_user = Depends(require_permission("sites:create")),
    db: Session = Depends(get_db)
):
    """创建站点"""
    tenant_id = get_tenant_id(request)
    
    # 生成站点ID
    site_id = generate_site_id()
    
    # 创建站点
    site = Site(
        id=site_id,
        tenant_id=tenant_id,
        name=site_data.name,
        address=site_data.address,
        latitude=site_data.latitude,
        longitude=site_data.longitude,
        operating_hours=site_data.operating_hours,
        is_active=True
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    
    return SiteResponse(
        id=site.id,
        tenant_id=site.tenant_id,
        name=site.name,
        address=site.address,
        latitude=site.latitude,
        longitude=site.longitude,
        is_active=site.is_active,
        operating_hours=site.operating_hours,
        charge_point_count=0,
        online_charge_points=0,
        today_energy_kwh=0.0,
        today_revenue=0.0,
        created_at=site.created_at,
        updated_at=site.updated_at
    )


@router.put("/{site_id}", response_model=SiteResponse, summary="更新站点")
async def update_site(
    site_id: str,
    site_data: SiteUpdateRequest,
    request: Request,
    current_user = Depends(require_permission("sites:edit")),
    db: Session = Depends(get_db)
):
    """更新站点"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Site).filter(Site.id == site_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Site.tenant_id == tenant_id)
    
    site = query.first()
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="站点不存在"
        )
    
    # 更新字段
    if site_data.name is not None:
        site.name = site_data.name
    if site_data.address is not None:
        site.address = site_data.address
    if site_data.latitude is not None:
        site.latitude = site_data.latitude
    if site_data.longitude is not None:
        site.longitude = site_data.longitude
    if site_data.is_active is not None:
        site.is_active = site_data.is_active
    if site_data.operating_hours is not None:
        site.operating_hours = site_data.operating_hours
    
    db.commit()
    db.refresh(site)
    
    # 统计信息
    charge_point_count = db.query(ChargePoint).filter(ChargePoint.site_id == site_id).count()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_invoices = db.query(Invoice).join(ChargingSession).join(ChargePoint).filter(
        and_(
            ChargePoint.site_id == site.id,
            Invoice.issued_at >= today_start
        )
    ).all()
    today_energy_kwh = sum(float(inv.energy_kwh) for inv in today_invoices)
    today_revenue = sum(float(inv.total_amount) for inv in today_invoices)
    
    return SiteResponse(
        id=site.id,
        tenant_id=site.tenant_id,
        name=site.name,
        address=site.address,
        latitude=site.latitude,
        longitude=site.longitude,
        is_active=site.is_active,
        operating_hours=site.operating_hours,
        charge_point_count=charge_point_count,
        online_charge_points=charge_point_count,
        today_energy_kwh=round(today_energy_kwh, 2),
        today_revenue=round(today_revenue, 2),
        created_at=site.created_at,
        updated_at=site.updated_at
    )


@router.delete("/{site_id}", summary="删除站点")
async def delete_site(
    site_id: str,
    request: Request,
    current_user = Depends(require_permission("sites:delete")),
    db: Session = Depends(get_db)
):
    """删除站点"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Site).filter(Site.id == site_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Site.tenant_id == tenant_id)
    
    site = query.first()
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="站点不存在"
        )
    
    # 检查是否有关联的充电桩
    charge_point_count = db.query(ChargePoint).filter(ChargePoint.site_id == site_id).count()
    if charge_point_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法删除站点：仍有 {charge_point_count} 个充电桩关联到此站点"
        )
    
    db.delete(site)
    db.commit()
    
    return {"message": "站点已删除"}
