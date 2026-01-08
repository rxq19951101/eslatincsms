#
# 多租户管理API
# 提供租户的CRUD、配置管理、订阅和限制管理
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timezone

from app.database.base import get_db
from app.database.models import (
    Tenant, TenantSubscription, TenantLimit, AdminUser,
    Site, ChargePoint, Order, Invoice
)
from app.core.auth import get_current_admin_user, require_permission
from app.core.exceptions import PermissionDenied
from app.core.id_generator import generate_order_id

router = APIRouter(prefix="/tenants", tags=["多租户管理"])


# ==================== 请求/响应模型 ====================

class TenantResponse(BaseModel):
    """租户响应"""
    id: str
    name: str
    code: str
    contact_name: Optional[str]
    contact_phone: Optional[str]
    contact_email: Optional[str]
    logo_url: Optional[str]
    theme_color: Optional[str]
    domain: Optional[str]
    status: str
    expires_at: Optional[datetime]
    site_count: int = 0
    charge_point_count: int = 0
    admin_user_count: int = 0
    created_at: datetime
    
    class Config:
        from_attributes = True


class TenantCreateRequest(BaseModel):
    """创建租户请求"""
    name: str
    code: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    logo_url: Optional[str] = None
    theme_color: Optional[str] = None
    domain: Optional[str] = None
    expires_at: Optional[datetime] = None


class TenantUpdateRequest(BaseModel):
    """更新租户请求"""
    name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    logo_url: Optional[str] = None
    theme_color: Optional[str] = None
    domain: Optional[str] = None
    status: Optional[str] = None
    expires_at: Optional[datetime] = None


class TenantSubscriptionRequest(BaseModel):
    """租户订阅请求"""
    module_code: str
    is_enabled: bool = True
    expires_at: Optional[datetime] = None


class TenantLimitRequest(BaseModel):
    """租户限制请求"""
    limit_type: str  # max_sites, max_charge_points, max_admin_users, etc.
    limit_value: int


# ==================== 租户管理端点 ====================

@router.get("", response_model=List[TenantResponse], summary="获取租户列表")
async def get_tenants(
    status_filter: Optional[str] = Query(None, description="按状态筛选"),
    current_user: AdminUser = Depends(require_permission("tenants:view")),
    db: Session = Depends(get_db)
):
    """
    获取租户列表
    
    - 普通用户只能看到自己租户
    - 超级管理员可以看到所有租户
    """
    query = db.query(Tenant)
    
    # 非超级管理员只能看到自己租户
    if not current_user.is_super_admin:
        query = query.filter(Tenant.id == current_user.tenant_id)
    
    if status_filter:
        query = query.filter(Tenant.status == status_filter)
    
    tenants = query.order_by(desc(Tenant.created_at)).all()
    
    # 构建响应（包含统计信息）
    result = []
    for tenant in tenants:
        # 统计站点数
        site_count = db.query(func.count(Site.id)).filter(
            Site.tenant_id == tenant.id
        ).scalar() or 0
        
        # 统计充电桩数
        charge_point_count = db.query(func.count(ChargePoint.id)).filter(
            ChargePoint.tenant_id == tenant.id
        ).scalar() or 0
        
        # 统计管理员用户数
        admin_user_count = db.query(func.count(AdminUser.id)).filter(
            AdminUser.tenant_id == tenant.id
        ).scalar() or 0
        
        result.append(TenantResponse(
            id=tenant.id,
            name=tenant.name,
            code=tenant.code,
            contact_name=tenant.contact_name,
            contact_phone=tenant.contact_phone,
            contact_email=tenant.contact_email,
            logo_url=tenant.logo_url,
            theme_color=tenant.theme_color,
            domain=tenant.domain,
            status=tenant.status,
            expires_at=tenant.expires_at,
            site_count=site_count,
            charge_point_count=charge_point_count,
            admin_user_count=admin_user_count,
            created_at=tenant.created_at
        ))
    
    return result


@router.get("/{tenant_id}", response_model=TenantResponse, summary="获取租户详情")
async def get_tenant(
    tenant_id: str,
    current_user: AdminUser = Depends(require_permission("tenants:view")),
    db: Session = Depends(get_db)
):
    """获取租户详情"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="租户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if tenant.id != current_user.tenant_id:
            raise PermissionDenied("无权查看其他租户")
    
    # 统计信息
    site_count = db.query(func.count(Site.id)).filter(
        Site.tenant_id == tenant.id
    ).scalar() or 0
    
    charge_point_count = db.query(func.count(ChargePoint.id)).filter(
        ChargePoint.tenant_id == tenant.id
    ).scalar() or 0
    
    admin_user_count = db.query(func.count(AdminUser.id)).filter(
        AdminUser.tenant_id == tenant.id
    ).scalar() or 0
    
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        code=tenant.code,
        contact_name=tenant.contact_name,
        contact_phone=tenant.contact_phone,
        contact_email=tenant.contact_email,
        logo_url=tenant.logo_url,
        theme_color=tenant.theme_color,
        domain=tenant.domain,
        status=tenant.status,
        expires_at=tenant.expires_at,
        site_count=site_count,
        charge_point_count=charge_point_count,
        admin_user_count=admin_user_count,
        created_at=tenant.created_at
    )


@router.post("", response_model=TenantResponse, summary="创建租户")
async def create_tenant(
    tenant_data: TenantCreateRequest,
    current_user: AdminUser = Depends(require_permission("tenants:create")),
    db: Session = Depends(get_db)
):
    """
    创建租户
    
    - 需要 tenants:create 权限（通常只有超级管理员）
    """
    # 检查租户代码是否已存在
    existing = db.query(Tenant).filter(Tenant.code == tenant_data.code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"租户代码 {tenant_data.code} 已存在"
        )
    
    # 生成租户ID
    tenant_id = f"tenant_{generate_order_id()}"
    
    # 创建租户
    tenant = Tenant(
        id=tenant_id,
        name=tenant_data.name,
        code=tenant_data.code,
        contact_name=tenant_data.contact_name,
        contact_phone=tenant_data.contact_phone,
        contact_email=tenant_data.contact_email,
        logo_url=tenant_data.logo_url,
        theme_color=tenant_data.theme_color,
        domain=tenant_data.domain,
        status="active",
        expires_at=tenant_data.expires_at
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        code=tenant.code,
        contact_name=tenant.contact_name,
        contact_phone=tenant.contact_phone,
        contact_email=tenant.contact_email,
        logo_url=tenant.logo_url,
        theme_color=tenant.theme_color,
        domain=tenant.domain,
        status=tenant.status,
        expires_at=tenant.expires_at,
        site_count=0,
        charge_point_count=0,
        admin_user_count=0,
        created_at=tenant.created_at
    )


@router.put("/{tenant_id}", response_model=TenantResponse, summary="更新租户")
async def update_tenant(
    tenant_id: str,
    tenant_data: TenantUpdateRequest,
    current_user: AdminUser = Depends(require_permission("tenants:edit")),
    db: Session = Depends(get_db)
):
    """更新租户"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="租户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if tenant.id != current_user.tenant_id:
            raise PermissionDenied("无权修改其他租户")
    
    # 更新字段
    if tenant_data.name is not None:
        tenant.name = tenant_data.name
    if tenant_data.contact_name is not None:
        tenant.contact_name = tenant_data.contact_name
    if tenant_data.contact_phone is not None:
        tenant.contact_phone = tenant_data.contact_phone
    if tenant_data.contact_email is not None:
        tenant.contact_email = tenant_data.contact_email
    if tenant_data.logo_url is not None:
        tenant.logo_url = tenant_data.logo_url
    if tenant_data.theme_color is not None:
        tenant.theme_color = tenant_data.theme_color
    if tenant_data.domain is not None:
        tenant.domain = tenant_data.domain
    if tenant_data.status is not None:
        tenant.status = tenant_data.status
    if tenant_data.expires_at is not None:
        tenant.expires_at = tenant_data.expires_at
    
    db.commit()
    db.refresh(tenant)
    
    # 统计信息
    site_count = db.query(func.count(Site.id)).filter(
        Site.tenant_id == tenant.id
    ).scalar() or 0
    
    charge_point_count = db.query(func.count(ChargePoint.id)).filter(
        ChargePoint.tenant_id == tenant.id
    ).scalar() or 0
    
    admin_user_count = db.query(func.count(AdminUser.id)).filter(
        AdminUser.tenant_id == tenant.id
    ).scalar() or 0
    
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        code=tenant.code,
        contact_name=tenant.contact_name,
        contact_phone=tenant.contact_phone,
        contact_email=tenant.contact_email,
        logo_url=tenant.logo_url,
        theme_color=tenant.theme_color,
        domain=tenant.domain,
        status=tenant.status,
        expires_at=tenant.expires_at,
        site_count=site_count,
        charge_point_count=charge_point_count,
        admin_user_count=admin_user_count,
        created_at=tenant.created_at
    )


@router.delete("/{tenant_id}", summary="删除租户")
async def delete_tenant(
    tenant_id: str,
    current_user: AdminUser = Depends(require_permission("tenants:delete")),
    db: Session = Depends(get_db)
):
    """
    删除租户
    
    - 需要 tenants:delete 权限（通常只有超级管理员）
    - 删除前会检查是否有关联数据
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="租户不存在"
        )
    
    # 检查是否有关联数据
    site_count = db.query(func.count(Site.id)).filter(
        Site.tenant_id == tenant_id
    ).scalar() or 0
    
    if site_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法删除租户：仍有 {site_count} 个站点关联到此租户"
        )
    
    db.delete(tenant)
    db.commit()
    
    return {"message": "租户已删除"}


# ==================== 租户订阅管理端点 ====================

@router.get("/{tenant_id}/subscriptions", summary="获取租户订阅列表")
async def get_tenant_subscriptions(
    tenant_id: str,
    current_user: AdminUser = Depends(require_permission("tenants:view")),
    db: Session = Depends(get_db)
):
    """获取租户的功能模块订阅列表"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="租户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if tenant.id != current_user.tenant_id:
            raise PermissionDenied("无权查看其他租户的订阅")
    
    subscriptions = db.query(TenantSubscription).filter(
        TenantSubscription.tenant_id == tenant_id
    ).all()
    
    return subscriptions


@router.post("/{tenant_id}/subscriptions", summary="添加租户订阅")
async def add_tenant_subscription(
    tenant_id: str,
    subscription_data: TenantSubscriptionRequest,
    current_user: AdminUser = Depends(require_permission("tenants:edit")),
    db: Session = Depends(get_db)
):
    """为租户添加功能模块订阅"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="租户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if tenant.id != current_user.tenant_id:
            raise PermissionDenied("无权修改其他租户的订阅")
    
    # 检查是否已存在
    existing = db.query(TenantSubscription).filter(
        and_(
            TenantSubscription.tenant_id == tenant_id,
            TenantSubscription.module_code == subscription_data.module_code
        )
    ).first()
    
    if existing:
        existing.is_enabled = subscription_data.is_enabled
        existing.expires_at = subscription_data.expires_at
    else:
        subscription = TenantSubscription(
            tenant_id=tenant_id,
            module_code=subscription_data.module_code,
            is_enabled=subscription_data.is_enabled,
            expires_at=subscription_data.expires_at
        )
        db.add(subscription)
    
    db.commit()
    
    return {"message": "订阅已更新"}


# ==================== 租户限制管理端点 ====================

@router.get("/{tenant_id}/limits", summary="获取租户限制列表")
async def get_tenant_limits(
    tenant_id: str,
    current_user: AdminUser = Depends(require_permission("tenants:view")),
    db: Session = Depends(get_db)
):
    """获取租户的使用量限制列表"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="租户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if tenant.id != current_user.tenant_id:
            raise PermissionDenied("无权查看其他租户的限制")
    
    limits = db.query(TenantLimit).filter(
        TenantLimit.tenant_id == tenant_id
    ).all()
    
    return limits


@router.post("/{tenant_id}/limits", summary="设置租户限制")
async def set_tenant_limit(
    tenant_id: str,
    limit_data: TenantLimitRequest,
    current_user: AdminUser = Depends(require_permission("tenants:edit")),
    db: Session = Depends(get_db)
):
    """设置租户的使用量限制"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="租户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if tenant.id != current_user.tenant_id:
            raise PermissionDenied("无权修改其他租户的限制")
    
    # 检查是否已存在
    existing = db.query(TenantLimit).filter(
        and_(
            TenantLimit.tenant_id == tenant_id,
            TenantLimit.limit_type == limit_data.limit_type
        )
    ).first()
    
    if existing:
        existing.limit_value = limit_data.limit_value
    else:
        limit = TenantLimit(
            tenant_id=tenant_id,
            limit_type=limit_data.limit_type,
            limit_value=limit_data.limit_value,
            current_value=0
        )
        db.add(limit)
    
    db.commit()
    
    return {"message": "限制已设置"}
