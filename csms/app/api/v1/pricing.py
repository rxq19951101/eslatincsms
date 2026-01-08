#
# 定价管理API
# 提供定价规则的配置和管理功能
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from datetime import datetime, timezone

from app.database.base import get_db
from app.database.models import Tariff, PricingSnapshot, Site, ChargePoint, Tenant
from app.core.auth import get_current_admin_user, require_permission
from app.core.tenant_middleware import get_tenant_id
from app.core.exceptions import PermissionDenied
from fastapi import Request

router = APIRouter(prefix="/pricing", tags=["定价管理"])


# ==================== 请求/响应模型 ====================

class TariffResponse(BaseModel):
    """定价规则响应"""
    id: int
    tenant_id: Optional[str]
    site_id: Optional[str]
    charge_point_id: Optional[str]
    name: str
    base_price_per_kwh: float
    service_fee: float
    time_based_rules: Optional[dict]
    valid_from: datetime
    valid_until: Optional[datetime]
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class TariffCreateRequest(BaseModel):
    """创建定价规则请求"""
    name: str
    site_id: Optional[str] = None
    charge_point_id: Optional[str] = None
    base_price_per_kwh: float
    service_fee: float = 0.0
    time_based_rules: Optional[dict] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None


class TariffUpdateRequest(BaseModel):
    """更新定价规则请求"""
    name: Optional[str] = None
    base_price_per_kwh: Optional[float] = None
    service_fee: Optional[float] = None
    time_based_rules: Optional[dict] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    is_active: Optional[bool] = None


# ==================== 定价管理端点 ====================

@router.get("/rules", response_model=List[TariffResponse], summary="获取定价规则列表")
async def get_tariffs(
    site_id: Optional[str] = Query(None, description="按站点筛选"),
    charge_point_id: Optional[str] = Query(None, description="按充电桩筛选"),
    is_active: Optional[bool] = Query(None, description="按状态筛选"),
    request: Request,
    current_user = Depends(require_permission("pricing:view")),
    db: Session = Depends(get_db)
):
    """
    获取定价规则列表
    
    - 支持按站点、充电桩筛选
    - 自动应用租户过滤
    """
    tenant_id = get_tenant_id(request)
    
    query = db.query(Tariff)
    
    # 多租户过滤
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Tariff.tenant_id == tenant_id)
    
    if site_id:
        query = query.filter(Tariff.site_id == site_id)
    if charge_point_id:
        query = query.filter(Tariff.charge_point_id == charge_point_id)
    if is_active is not None:
        query = query.filter(Tariff.is_active == is_active)
    
    tariffs = query.order_by(desc(Tariff.created_at)).all()
    
    return tariffs


@router.get("/rules/{tariff_id}", response_model=TariffResponse, summary="获取定价规则详情")
async def get_tariff(
    tariff_id: int,
    request: Request,
    current_user = Depends(require_permission("pricing:view")),
    db: Session = Depends(get_db)
):
    """获取定价规则详情"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Tariff).filter(Tariff.id == tariff_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Tariff.tenant_id == tenant_id)
    
    tariff = query.first()
    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="定价规则不存在"
        )
    
    return tariff


@router.post("/rules", response_model=TariffResponse, summary="创建定价规则")
async def create_tariff(
    tariff_data: TariffCreateRequest,
    request: Request,
    current_user = Depends(require_permission("pricing:create")),
    db: Session = Depends(get_db)
):
    """创建定价规则"""
    tenant_id = get_tenant_id(request)
    
    # 验证站点或充电桩是否存在且属于当前租户
    if tariff_data.site_id:
        site = db.query(Site).filter(Site.id == tariff_data.site_id).first()
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="站点不存在"
            )
        if tenant_id and not current_user.is_super_admin:
            if site.tenant_id != tenant_id:
                raise PermissionDenied("无权为其他租户的站点创建定价规则")
    
    if tariff_data.charge_point_id:
        cp = db.query(ChargePoint).filter(ChargePoint.id == tariff_data.charge_point_id).first()
        if not cp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="充电桩不存在"
            )
        if tenant_id and not current_user.is_super_admin:
            if cp.tenant_id != tenant_id:
                raise PermissionDenied("无权为其他租户的充电桩创建定价规则")
    
    # 创建定价规则
    tariff = Tariff(
        tenant_id=tenant_id,
        site_id=tariff_data.site_id,
        charge_point_id=tariff_data.charge_point_id,
        name=tariff_data.name,
        base_price_per_kwh=tariff_data.base_price_per_kwh,
        service_fee=tariff_data.service_fee,
        time_based_rules=tariff_data.time_based_rules,
        valid_from=tariff_data.valid_from,
        valid_until=tariff_data.valid_until,
        is_active=True
    )
    db.add(tariff)
    db.commit()
    db.refresh(tariff)
    
    return tariff


@router.put("/rules/{tariff_id}", response_model=TariffResponse, summary="更新定价规则")
async def update_tariff(
    tariff_id: int,
    tariff_data: TariffUpdateRequest,
    request: Request,
    current_user = Depends(require_permission("pricing:edit")),
    db: Session = Depends(get_db)
):
    """更新定价规则"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Tariff).filter(Tariff.id == tariff_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Tariff.tenant_id == tenant_id)
    
    tariff = query.first()
    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="定价规则不存在"
        )
    
    # 更新字段
    if tariff_data.name is not None:
        tariff.name = tariff_data.name
    if tariff_data.base_price_per_kwh is not None:
        tariff.base_price_per_kwh = tariff_data.base_price_per_kwh
    if tariff_data.service_fee is not None:
        tariff.service_fee = tariff_data.service_fee
    if tariff_data.time_based_rules is not None:
        tariff.time_based_rules = tariff_data.time_based_rules
    if tariff_data.valid_from is not None:
        tariff.valid_from = tariff_data.valid_from
    if tariff_data.valid_until is not None:
        tariff.valid_until = tariff_data.valid_until
    if tariff_data.is_active is not None:
        tariff.is_active = tariff_data.is_active
    
    db.commit()
    db.refresh(tariff)
    
    return tariff


@router.delete("/rules/{tariff_id}", summary="删除定价规则")
async def delete_tariff(
    tariff_id: int,
    request: Request,
    current_user = Depends(require_permission("pricing:delete")),
    db: Session = Depends(get_db)
):
    """删除定价规则"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Tariff).filter(Tariff.id == tariff_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Tariff.tenant_id == tenant_id)
    
    tariff = query.first()
    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="定价规则不存在"
        )
    
    db.delete(tariff)
    db.commit()
    
    return {"message": "定价规则已删除"}
