#
# 角色权限管理API
# 提供角色的CRUD操作和用户角色分配
#

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.database.base import get_db
from app.database.models import Role, TenantMembershipRole
from app.core.auth import get_current_user
from app.core.permissions import get_current_admin_user
from app.services.role_service import RoleService, MembershipRoleService
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class CreateRoleRequest(BaseModel):
    name: str
    permissions: List[str]
    description: Optional[str] = None
    scope: str = "tenant"


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = None
    permissions: Optional[List[str]] = None
    description: Optional[str] = None


class RoleResponse(BaseModel):
    id: str
    tenant_id: Optional[str]
    name: str
    permissions: List[str]
    description: Optional[str]
    scope: str
    created_at: str
    updated_at: str


class AssignRoleRequest(BaseModel):
    role_id: UUID


# ==================== 角色端点 ====================

@router.get("", response_model=List[RoleResponse], summary="获取角色列表")
async def list_roles(
    scope: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取角色列表（系统角色 + 租户角色）"""
    # 从请求中获取 tenant_id
    from app.database.base import tenant_id_context
    tenant_id = tenant_id_context.get()
    
    roles = RoleService.list_roles(
        db=db,
        tenant_id=tenant_id,
        scope=scope
    )
    
    return [
        RoleResponse(
            id=str(r.id),
            tenant_id=str(r.tenant_id) if r.tenant_id else None,
            name=r.name,
            permissions=r.permissions if isinstance(r.permissions, list) else [],
            description=r.description,
            scope=r.scope,
            created_at=r.created_at.isoformat() if r.created_at else "",
            updated_at=r.updated_at.isoformat() if r.updated_at else ""
        )
        for r in roles
    ]


@router.post("", response_model=RoleResponse, summary="创建角色")
async def create_role(
    request_data: CreateRoleRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建角色（租户自定义）"""
    # 从请求中获取 tenant_id
    from app.database.base import tenant_id_context
    tenant_id = tenant_id_context.get()
    
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required for tenant-scoped roles")
    
    try:
        role = RoleService.create_role(
            db=db,
            name=request_data.name,
            permissions=request_data.permissions,
            tenant_id=tenant_id,
            description=request_data.description,
            scope=request_data.scope
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return RoleResponse(
        id=str(role.id),
        tenant_id=str(role.tenant_id) if role.tenant_id else None,
        name=role.name,
        permissions=role.permissions if isinstance(role.permissions, list) else [],
        description=role.description,
        scope=role.scope,
        created_at=role.created_at.isoformat() if role.created_at else "",
        updated_at=role.updated_at.isoformat() if role.updated_at else ""
    )


@router.get("/{role_id}", response_model=RoleResponse, summary="获取角色详情")
async def get_role(
    role_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取角色详情"""
    role = RoleService.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return RoleResponse(
        id=str(role.id),
        tenant_id=str(role.tenant_id) if role.tenant_id else None,
        name=role.name,
        permissions=role.permissions if isinstance(role.permissions, list) else [],
        description=role.description,
        scope=role.scope,
        created_at=role.created_at.isoformat() if role.created_at else "",
        updated_at=role.updated_at.isoformat() if role.updated_at else ""
    )


@router.put("/{role_id}", response_model=RoleResponse, summary="更新角色")
async def update_role(
    role_id: UUID,
    request_data: UpdateRoleRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新角色"""
    try:
        role = RoleService.update_role(
            db=db,
            role_id=role_id,
            name=request_data.name,
            permissions=request_data.permissions,
            description=request_data.description
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return RoleResponse(
        id=str(role.id),
        tenant_id=str(role.tenant_id) if role.tenant_id else None,
        name=role.name,
        permissions=role.permissions if isinstance(role.permissions, list) else [],
        description=role.description,
        scope=role.scope,
        created_at=role.created_at.isoformat() if role.created_at else "",
        updated_at=role.updated_at.isoformat() if role.updated_at else ""
    )


@router.delete("/{role_id}", summary="删除角色")
async def delete_role(
    role_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除角色"""
    success = RoleService.delete_role(db, role_id)
    if not success:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return {"message": "Role deleted successfully"}


@router.get("/{role_id}/permissions", summary="获取角色权限")
async def get_role_permissions(
    role_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取角色权限列表"""
    role = RoleService.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return {
        "role_id": str(role_id),
        "permissions": role.permissions if isinstance(role.permissions, list) else []
    }


@router.put("/memberships/{membership_id}/roles", summary="为用户分配角色")
async def assign_role_to_membership(
    membership_id: UUID,
    request_data: AssignRoleRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """为用户分配角色"""
    try:
        membership_role = MembershipRoleService.assign_role_to_membership(
            db=db,
            membership_id=membership_id,
            role_id=request_data.role_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"message": "Role assigned successfully"}


@router.delete("/memberships/{membership_id}/roles/{role_id}", summary="移除用户角色")
async def remove_role_from_membership(
    membership_id: UUID,
    role_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """从用户中移除角色"""
    success = MembershipRoleService.remove_role_from_membership(
        db=db,
        membership_id=membership_id,
        role_id=role_id
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    
    return {"message": "Role removed successfully"}
