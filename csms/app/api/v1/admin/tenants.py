#
# 租户管理API
# 提供租户的CRUD操作（仅超级管理员）
#

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from typing import Literal
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.database.base import get_db, tenant_id_context
from app.database.models import Tenant
from app.core.auth import get_current_user
from app.core.permissions import get_current_admin_user, require_permission
from app.services.tenant_service import TenantService
from app.core.logging_config import get_logger
from app.api.validation import ShortName, StrictRequestModel

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class CreateTenantRequest(StrictRequestModel):
    name: ShortName
    domain: Optional[str] = Field(None, min_length=3, max_length=200, pattern=r"^[A-Za-z0-9.-]+$")
    subscription_plan: Literal["free", "pro", "enterprise"] = "free"
    max_charge_points: int = Field(10, ge=1, le=100000)
    max_users: int = Field(100, ge=1, le=10000000)
    settings: Optional[dict] = None


class UpdateTenantRequest(StrictRequestModel):
    name: Optional[ShortName] = None
    domain: Optional[str] = Field(None, min_length=3, max_length=200, pattern=r"^[A-Za-z0-9.-]+$")
    status: Optional[Literal["active", "suspended", "deleted"]] = None
    subscription_plan: Optional[Literal["free", "pro", "enterprise"]] = None
    max_charge_points: Optional[int] = Field(None, ge=1, le=100000)
    max_users: Optional[int] = Field(None, ge=1, le=10000000)
    settings: Optional[dict] = None


class UpdateOwnTenantSettingsRequest(StrictRequestModel):
    name: Optional[ShortName] = None
    domain: Optional[str] = Field(None, min_length=3, max_length=200, pattern=r"^[A-Za-z0-9.-]+$")


class ProvisionAdminRequest(StrictRequestModel):
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=200)


class ProvisionTenantRequest(StrictRequestModel):
    tenant: CreateTenantRequest
    admin: ProvisionAdminRequest


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


class ProvisionAdminResponse(BaseModel):
    id: str
    username: str
    email: EmailStr
    full_name: Optional[str]
    is_active: bool
    is_super_admin: bool
    last_login_at: Optional[str]
    created_at: str
    updated_at: str


class ProvisionTenantResponse(BaseModel):
    tenant: TenantResponse
    admin: ProvisionAdminResponse
    membership_id: str


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

@router.get("/current", response_model=TenantResponse, summary="获取当前租户设置")
async def get_current_tenant_settings(
    current_user_obj = Depends(require_permission("tenant_settings.read")),
    db: Session = Depends(get_db),
):
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    tenant = TenantService.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantResponse(
        id=str(tenant.id), name=tenant.name, domain=tenant.domain, status=tenant.status,
        subscription_plan=tenant.subscription_plan, max_charge_points=tenant.max_charge_points,
        max_users=tenant.max_users, settings=tenant.settings or {},
        created_at=tenant.created_at.isoformat() if tenant.created_at else "",
        updated_at=tenant.updated_at.isoformat() if tenant.updated_at else "",
    )


@router.put("/current", response_model=TenantResponse, summary="更新当前租户设置")
async def update_current_tenant_settings(
    request_data: UpdateOwnTenantSettingsRequest,
    current_user_obj = Depends(require_permission("tenant_settings.write")),
    db: Session = Depends(get_db),
):
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    tenant = TenantService.update_tenant(
        db=db, tenant_id=tenant_id, name=request_data.name,
        domain=request_data.domain,
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantResponse(
        id=str(tenant.id), name=tenant.name, domain=tenant.domain, status=tenant.status,
        subscription_plan=tenant.subscription_plan, max_charge_points=tenant.max_charge_points,
        max_users=tenant.max_users, settings=tenant.settings or {},
        created_at=tenant.created_at.isoformat() if tenant.created_at else "",
        updated_at=tenant.updated_at.isoformat() if tenant.updated_at else "",
    )

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


@router.post("/provision", response_model=ProvisionTenantResponse, status_code=201, summary="原子开通租户")
async def provision_tenant(
    request_data: ProvisionTenantRequest,
    current_user_obj=Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """单事务创建租户、首个管理员、管理员角色和成员关系。"""
    tenant_payload = request_data.tenant.model_dump(exclude_none=True)
    tenant_payload["settings"] = tenant_payload.get("settings") or {}
    try:
        tenant, admin, membership = TenantService.provision_tenant(
            db,
            tenant_data=tenant_payload,
            admin_data=request_data.admin.model_dump(),
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Tenant domain, admin username or email already exists") from exc

    return ProvisionTenantResponse(
        tenant=TenantResponse(
            id=str(tenant.id),
            name=tenant.name,
            domain=tenant.domain,
            status=tenant.status,
            subscription_plan=tenant.subscription_plan,
            max_charge_points=tenant.max_charge_points,
            max_users=tenant.max_users,
            settings=tenant.settings or {},
            created_at=tenant.created_at.isoformat() if tenant.created_at else "",
            updated_at=tenant.updated_at.isoformat() if tenant.updated_at else "",
        ),
        admin=ProvisionAdminResponse(
            id=str(admin.id),
            username=admin.username,
            email=admin.email,
            full_name=admin.full_name,
            is_active=admin.is_active,
            is_super_admin=admin.is_super_admin,
            last_login_at=admin.last_login_at.isoformat() if admin.last_login_at else None,
            created_at=admin.created_at.isoformat() if admin.created_at else "",
            updated_at=admin.updated_at.isoformat() if admin.updated_at else "",
        ),
        membership_id=str(membership.id),
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
