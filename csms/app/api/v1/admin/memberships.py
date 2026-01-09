#
# 租户成员管理API
# 管理管理员用户与租户的关系
#

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.database.base import get_db
from app.database.models import TenantMembership, Tenant, AdminUser
from app.core.auth import get_current_user
from app.core.permissions import get_current_admin_user
from app.services.membership_service import MembershipService
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class AddUserToTenantRequest(BaseModel):
    admin_user_id: UUID
    is_primary: bool = False


class SetPrimaryTenantRequest(BaseModel):
    tenant_id: UUID


class MembershipResponse(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str
    admin_user_id: str
    admin_username: str
    is_primary: bool
    status: str
    created_at: str
    updated_at: str


# ==================== 成员端点 ====================

@router.get("", response_model=List[MembershipResponse], summary="获取租户成员列表")
async def list_tenant_members(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取租户的所有成员"""
    # 从请求中获取 tenant_id
    from app.database.base import tenant_id_context
    tenant_id = tenant_id_context.get()
    
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    memberships = MembershipService.get_tenant_members(db, tenant_id)
    
    result = []
    for m in memberships:
        tenant = db.query(Tenant).filter(Tenant.id == m.tenant_id).first()
        admin_user = db.query(AdminUser).filter(AdminUser.id == m.admin_user_id).first()
        
        result.append(MembershipResponse(
            id=str(m.id),
            tenant_id=str(m.tenant_id),
            tenant_name=tenant.name if tenant else "",
            admin_user_id=str(m.admin_user_id),
            admin_username=admin_user.username if admin_user else "",
            is_primary=m.is_primary,
            status=m.status,
            created_at=m.created_at.isoformat() if m.created_at else "",
            updated_at=m.updated_at.isoformat() if m.updated_at else ""
        ))
    
    return result


@router.post("", response_model=MembershipResponse, summary="添加用户到租户")
async def add_user_to_tenant(
    request_data: AddUserToTenantRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """将管理员用户添加到租户"""
    # 从请求中获取 tenant_id
    from app.database.base import tenant_id_context
    tenant_id = tenant_id_context.get()
    
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    try:
        membership = MembershipService.add_user_to_tenant(
            db=db,
            tenant_id=tenant_id,
            admin_user_id=request_data.admin_user_id,
            is_primary=request_data.is_primary
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    tenant = db.query(Tenant).filter(Tenant.id == membership.tenant_id).first()
    admin_user = db.query(AdminUser).filter(AdminUser.id == membership.admin_user_id).first()
    
    return MembershipResponse(
        id=str(membership.id),
        tenant_id=str(membership.tenant_id),
        tenant_name=tenant.name if tenant else "",
        admin_user_id=str(membership.admin_user_id),
        admin_username=admin_user.username if admin_user else "",
        is_primary=membership.is_primary,
        status=membership.status,
        created_at=membership.created_at.isoformat() if membership.created_at else "",
        updated_at=membership.updated_at.isoformat() if membership.updated_at else ""
    )


@router.delete("/{membership_id}", summary="从租户中移除用户")
async def remove_user_from_tenant(
    membership_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """从租户中移除管理员用户"""
    membership = db.query(TenantMembership).filter(TenantMembership.id == membership_id).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    
    success = MembershipService.remove_user_from_tenant(
        db=db,
        tenant_id=membership.tenant_id,
        admin_user_id=membership.admin_user_id
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Membership not found")
    
    return {"message": "User removed from tenant successfully"}


@router.put("/{membership_id}/primary", summary="设置默认租户")
async def set_primary_tenant(
    membership_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """设置用户的默认租户"""
    membership = db.query(TenantMembership).filter(TenantMembership.id == membership_id).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    
    try:
        MembershipService.set_primary_tenant(
            db=db,
            admin_user_id=membership.admin_user_id,
            tenant_id=membership.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"message": "Primary tenant updated successfully"}
