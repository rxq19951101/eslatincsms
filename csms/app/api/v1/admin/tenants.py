#
# 租户管理API
# 提供租户的CRUD操作（仅超级管理员）
#

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.database.base import get_db
from app.database.models import Tenant
from app.core.auth import get_current_user
from app.core.permissions import get_current_admin_user
from app.services.tenant_service import TenantService
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class CreateTenantRequest(BaseModel):
    name: str
    domain: Optional[str] = None
    subscription_plan: str = "free"
    max_charge_points: int = 10
    max_users: int = 100
    settings: Optional[dict] = None


class UpdateTenantRequest(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    status: Optional[str] = None
    subscription_plan: Optional[str] = None
    max_charge_points: Optional[int] = None
    max_users: Optional[int] = None
    settings: Optional[dict] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    domain: Optional[str]
    status: str
    subscription_plan: str
    max_charge_points: int
    max_users: int
    settings: dict
    created_at: str
    updated_at: str


# ==================== 辅助函数 ====================

def require_super_admin(current_user_obj = Depends(get_current_admin_user)):
    """要求超级管理员权限"""
    if not current_user_obj.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Super admin access required"
        )
    return current_user_obj


# ==================== 租户端点 ====================

@router.get("", response_model=List[TenantResponse], summary="获取租户列表")
async def list_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    current_user_obj = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """获取租户列表（仅超级管理员）"""
    tenants = TenantService.list_tenants(db=db, skip=skip, limit=limit, status=status)
    
    return [
        TenantResponse(
            id=str(t.id),
            name=t.name,
            domain=t.domain,
            status=t.status,
            subscription_plan=t.subscription_plan,
            max_charge_points=t.max_charge_points,
            max_users=t.max_users,
            settings=t.settings or {},
            created_at=t.created_at.isoformat() if t.created_at else "",
            updated_at=t.updated_at.isoformat() if t.updated_at else ""
        )
        for t in tenants
    ]


@router.post("", response_model=TenantResponse, summary="创建租户")
async def create_tenant(
    request_data: CreateTenantRequest,
    current_user_obj = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """创建租户（仅超级管理员）"""
    tenant = TenantService.create_tenant(
        db=db,
        name=request_data.name,
        domain=request_data.domain,
        subscription_plan=request_data.subscription_plan,
        max_charge_points=request_data.max_charge_points,
        max_users=request_data.max_users,
        settings=request_data.settings
    )
    
    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        domain=tenant.domain,
        status=tenant.status,
        subscription_plan=tenant.subscription_plan,
        max_charge_points=tenant.max_charge_points,
        max_users=tenant.max_users,
        settings=tenant.settings or {},
        created_at=tenant.created_at.isoformat() if tenant.created_at else "",
        updated_at=tenant.updated_at.isoformat() if tenant.updated_at else ""
    )


@router.get("/{tenant_id}", response_model=TenantResponse, summary="获取租户详情")
async def get_tenant(
    tenant_id: UUID,
    current_user_obj = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """获取租户详情（仅超级管理员）"""
    tenant = TenantService.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        domain=tenant.domain,
        status=tenant.status,
        subscription_plan=tenant.subscription_plan,
        max_charge_points=tenant.max_charge_points,
        max_users=tenant.max_users,
        settings=tenant.settings or {},
        created_at=tenant.created_at.isoformat() if tenant.created_at else "",
        updated_at=tenant.updated_at.isoformat() if tenant.updated_at else ""
    )


@router.put("/{tenant_id}", response_model=TenantResponse, summary="更新租户")
async def update_tenant(
    tenant_id: UUID,
    request_data: UpdateTenantRequest,
    current_user_obj = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """更新租户（仅超级管理员）"""
    tenant = TenantService.update_tenant(
        db=db,
        tenant_id=tenant_id,
        name=request_data.name,
        domain=request_data.domain,
        status=request_data.status,
        subscription_plan=request_data.subscription_plan,
        max_charge_points=request_data.max_charge_points,
        max_users=request_data.max_users,
        settings=request_data.settings
    )
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        domain=tenant.domain,
        status=tenant.status,
        subscription_plan=tenant.subscription_plan,
        max_charge_points=tenant.max_charge_points,
        max_users=tenant.max_users,
        settings=tenant.settings or {},
        created_at=tenant.created_at.isoformat() if tenant.created_at else "",
        updated_at=tenant.updated_at.isoformat() if tenant.updated_at else ""
    )


@router.delete("/{tenant_id}", summary="删除租户")
async def delete_tenant(
    tenant_id: UUID,
    current_user_obj = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """删除租户（仅超级管理员）"""
    success = TenantService.delete_tenant(db, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return {"message": "Tenant deleted successfully"}


@router.get("/{tenant_id}/statistics", summary="获取租户统计信息")
async def get_tenant_statistics(
    tenant_id: UUID,
    current_user_obj = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """获取租户统计信息（仅超级管理员）"""
    stats = TenantService.get_tenant_statistics(db, tenant_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return stats
