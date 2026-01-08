#
# RBAC权限管理API
# 提供角色、权限、资源权限的管理功能
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database.base import get_db
from app.database.models import (
    Role, Permission, RolePermission, AdminUserRole, 
    ResourcePermission, AdminUser, Tenant
)
from app.core.auth import (
    get_current_admin_user, require_permission, 
    get_user_permissions, get_tenant_filter
)
from app.core.exceptions import PermissionDenied

router = APIRouter(prefix="/rbac", tags=["权限管理"])


# ==================== 请求/响应模型 ====================

class PermissionResponse(BaseModel):
    """权限响应"""
    id: int
    code: str
    name: str
    description: Optional[str]
    module: Optional[str]
    permission_type: str
    
    class Config:
        from_attributes = True


class RoleResponse(BaseModel):
    """角色响应"""
    id: int
    tenant_id: Optional[str]
    name: str
    code: str
    description: Optional[str]
    role_type: str
    status: str
    permissions: List[PermissionResponse]
    user_count: int = 0
    
    class Config:
        from_attributes = True


class RoleCreateRequest(BaseModel):
    """创建角色请求"""
    name: str
    code: str
    description: Optional[str] = None
    permission_ids: List[int] = []


class RoleUpdateRequest(BaseModel):
    """更新角色请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[List[int]] = None
    status: Optional[str] = None


class AssignRoleRequest(BaseModel):
    """分配角色请求"""
    role_ids: List[int]


class ResourcePermissionRequest(BaseModel):
    """资源权限请求"""
    resource_type: str  # site, charge_point
    resource_id: str
    permission_type: str = "read"  # read, write, admin


# ==================== 权限管理端点 ====================

@router.get("/permissions", response_model=List[PermissionResponse], summary="获取所有权限")
async def get_permissions(
    module: Optional[str] = Query(None, description="按模块筛选"),
    current_user: AdminUser = Depends(require_permission("rbac:permissions:view")),
    db: Session = Depends(get_db)
):
    """
    获取所有权限列表
    
    - 支持按模块筛选
    - 需要 rbac:permissions:view 权限
    """
    query = db.query(Permission)
    
    if module:
        query = query.filter(Permission.module == module)
    
    permissions = query.order_by(Permission.module, Permission.code).all()
    return permissions


@router.get("/permissions/{permission_id}", response_model=PermissionResponse, summary="获取权限详情")
async def get_permission(
    permission_id: int,
    current_user: AdminUser = Depends(require_permission("rbac:permissions:view")),
    db: Session = Depends(get_db)
):
    """获取权限详情"""
    permission = db.query(Permission).filter(Permission.id == permission_id).first()
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="权限不存在"
        )
    return permission


# ==================== 角色管理端点 ====================

@router.get("/roles", response_model=List[RoleResponse], summary="获取角色列表")
async def get_roles(
    current_user: AdminUser = Depends(require_permission("rbac:roles:view")),
    db: Session = Depends(get_db)
):
    """
    获取角色列表
    
    - 普通用户只能看到自己租户的角色
    - 超级管理员可以看到所有角色
    """
    query = db.query(Role)
    
    # 非超级管理员只能看到自己租户的角色
    if not current_user.is_super_admin:
        query = query.filter(
            or_(
                Role.tenant_id == current_user.tenant_id,
                Role.role_type == "system"  # 系统角色所有租户可见
            )
        )
    
    roles = query.order_by(Role.role_type, Role.name).all()
    
    # 构建响应
    result = []
    for role in roles:
        # 获取权限
        permissions = db.query(Permission).join(RolePermission).filter(
            RolePermission.role_id == role.id
        ).all()
        
        # 获取用户数量
        user_count = db.query(AdminUserRole).filter(
            AdminUserRole.role_id == role.id
        ).count()
        
        result.append(RoleResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            code=role.code,
            description=role.description,
            role_type=role.role_type,
            status=role.status,
            permissions=[PermissionResponse.model_validate(p) for p in permissions],
            user_count=user_count
        ))
    
    return result


@router.get("/roles/{role_id}", response_model=RoleResponse, summary="获取角色详情")
async def get_role(
    role_id: int,
    current_user: AdminUser = Depends(require_permission("rbac:roles:view")),
    db: Session = Depends(get_db)
):
    """获取角色详情"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
    
    # 检查权限（非超级管理员只能查看自己租户的角色）
    if not current_user.is_super_admin:
        if role.tenant_id != current_user.tenant_id and role.role_type != "system":
            raise PermissionDenied("无权访问此角色")
    
    # 获取权限
    permissions = db.query(Permission).join(RolePermission).filter(
        RolePermission.role_id == role.id
    ).all()
    
    # 获取用户数量
    user_count = db.query(AdminUserRole).filter(
        AdminUserRole.role_id == role.id
    ).count()
    
    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        code=role.code,
        description=role.description,
        role_type=role.role_type,
        status=role.status,
        permissions=[PermissionResponse.from_orm(p) for p in permissions],
        user_count=user_count
    )


@router.post("/roles", response_model=RoleResponse, summary="创建角色")
async def create_role(
    role_data: RoleCreateRequest,
    current_user: AdminUser = Depends(require_permission("rbac:roles:create")),
    db: Session = Depends(get_db)
):
    """
    创建角色
    
    - 普通用户只能为自己租户创建角色
    - 需要 rbac:roles:create 权限
    """
    # 检查角色代码是否已存在
    existing_role = db.query(Role).filter(
        and_(
            Role.code == role_data.code,
            Role.tenant_id == current_user.tenant_id
        )
    ).first()
    
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"角色代码 {role_data.code} 已存在"
        )
    
    # 创建角色
    role = Role(
        tenant_id=current_user.tenant_id,
        name=role_data.name,
        code=role_data.code,
        description=role_data.description,
        role_type="custom"
    )
    db.add(role)
    db.flush()  # 获取role.id
    
    # 分配权限
    if role_data.permission_ids:
        permissions = db.query(Permission).filter(
            Permission.id.in_(role_data.permission_ids)
        ).all()
        
        for permission in permissions:
            role_permission = RolePermission(
                role_id=role.id,
                permission_id=permission.id
            )
            db.add(role_permission)
    
    db.commit()
    db.refresh(role)
    
    # 获取权限列表
    permissions = db.query(Permission).join(RolePermission).filter(
        RolePermission.role_id == role.id
    ).all()
    
    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        code=role.code,
        description=role.description,
        role_type=role.role_type,
        status=role.status,
        permissions=[PermissionResponse.from_orm(p) for p in permissions],
        user_count=0
    )


@router.put("/roles/{role_id}", response_model=RoleResponse, summary="更新角色")
async def update_role(
    role_id: int,
    role_data: RoleUpdateRequest,
    current_user: AdminUser = Depends(require_permission("rbac:roles:edit")),
    db: Session = Depends(get_db)
):
    """更新角色"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if role.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权修改此角色")
        if role.role_type == "system":
            raise PermissionDenied("无法修改系统角色")
    
    # 更新基本信息
    if role_data.name is not None:
        role.name = role_data.name
    if role_data.description is not None:
        role.description = role_data.description
    if role_data.status is not None:
        role.status = role_data.status
    
    # 更新权限
    if role_data.permission_ids is not None:
        # 删除旧权限
        db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
        
        # 添加新权限
        if role_data.permission_ids:
            permissions = db.query(Permission).filter(
                Permission.id.in_(role_data.permission_ids)
            ).all()
            
            for permission in permissions:
                role_permission = RolePermission(
                    role_id=role.id,
                    permission_id=permission.id
                )
                db.add(role_permission)
    
    db.commit()
    db.refresh(role)
    
    # 获取权限列表
    permissions = db.query(Permission).join(RolePermission).filter(
        RolePermission.role_id == role.id
    ).all()
    
    # 获取用户数量
    user_count = db.query(AdminUserRole).filter(
        AdminUserRole.role_id == role.id
    ).count()
    
    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        code=role.code,
        description=role.description,
        role_type=role.role_type,
        status=role.status,
        permissions=[PermissionResponse.from_orm(p) for p in permissions],
        user_count=user_count
    )


@router.delete("/roles/{role_id}", summary="删除角色")
async def delete_role(
    role_id: int,
    current_user: AdminUser = Depends(require_permission("rbac:roles:delete")),
    db: Session = Depends(get_db)
):
    """删除角色"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if role.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权删除此角色")
        if role.role_type == "system":
            raise PermissionDenied("无法删除系统角色")
    
    # 检查是否有用户使用此角色
    user_count = db.query(AdminUserRole).filter(
        AdminUserRole.role_id == role_id
    ).count()
    
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法删除角色：仍有 {user_count} 个用户使用此角色"
        )
    
    db.delete(role)
    db.commit()
    
    return {"message": "角色已删除"}


# ==================== 用户角色分配端点 ====================

@router.put("/users/{user_id}/roles", summary="为用户分配角色")
async def assign_roles_to_user(
    user_id: str,
    role_data: AssignRoleRequest,
    current_user: AdminUser = Depends(require_permission("rbac:users:edit")),
    db: Session = Depends(get_db)
):
    """
    为用户分配角色
    
    - 需要 rbac:users:edit 权限
    - 只能为自己租户的用户分配角色
    """
    # 获取目标用户
    target_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查权限（只能操作自己租户的用户）
    if not current_user.is_super_admin:
        if target_user.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权操作其他租户的用户")
    
    # 验证角色是否存在且属于同一租户
    roles = db.query(Role).filter(Role.id.in_(role_data.role_ids)).all()
    if len(roles) != len(role_data.role_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="部分角色不存在"
        )
    
    # 检查角色租户权限
    if not current_user.is_super_admin:
        for role in roles:
            if role.tenant_id != current_user.tenant_id and role.role_type != "system":
                raise PermissionDenied(f"无权分配角色 {role.name}")
    
    # 删除旧的角色分配
    db.query(AdminUserRole).filter(AdminUserRole.admin_user_id == user_id).delete()
    
    # 添加新的角色分配
    for role in roles:
        user_role = AdminUserRole(
            admin_user_id=user_id,
            role_id=role.id
        )
        db.add(user_role)
    
    db.commit()
    
    return {"message": "角色分配成功"}


@router.get("/users/{user_id}/roles", response_model=List[RoleResponse], summary="获取用户的角色列表")
async def get_user_roles(
    user_id: str,
    current_user: AdminUser = Depends(require_permission("rbac:users:view")),
    db: Session = Depends(get_db)
):
    """获取用户的角色列表"""
    target_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if target_user.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权查看其他租户的用户")
    
    # 获取用户角色
    roles = db.query(Role).join(AdminUserRole).filter(
        AdminUserRole.admin_user_id == user_id
    ).all()
    
    result = []
    for role in roles:
        permissions = db.query(Permission).join(RolePermission).filter(
            RolePermission.role_id == role.id
        ).all()
        
        result.append(RoleResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            code=role.code,
            description=role.description,
            role_type=role.role_type,
            status=role.status,
            permissions=[PermissionResponse.model_validate(p) for p in permissions],
            user_count=0
        ))
    
    return result


# ==================== 资源权限端点 ====================

@router.post("/users/{user_id}/resource-permissions", summary="为用户分配资源权限")
async def assign_resource_permission(
    user_id: str,
    resource_data: ResourcePermissionRequest,
    current_user: AdminUser = Depends(require_permission("rbac:users:edit")),
    db: Session = Depends(get_db)
):
    """为用户分配资源权限（站点/充电桩范围权限）"""
    target_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if target_user.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权操作其他租户的用户")
    
    # 检查资源权限是否已存在
    existing = db.query(ResourcePermission).filter(
        and_(
            ResourcePermission.admin_user_id == user_id,
            ResourcePermission.resource_type == resource_data.resource_type,
            ResourcePermission.resource_id == resource_data.resource_id
        )
    ).first()
    
    if existing:
        existing.permission_type = resource_data.permission_type
    else:
        resource_permission = ResourcePermission(
            admin_user_id=user_id,
            resource_type=resource_data.resource_type,
            resource_id=resource_data.resource_id,
            permission_type=resource_data.permission_type
        )
        db.add(resource_permission)
    
    db.commit()
    
    return {"message": "资源权限分配成功"}


@router.delete("/users/{user_id}/resource-permissions", summary="删除用户资源权限")
async def remove_resource_permission(
    user_id: str,
    resource_type: str = Query(..., description="资源类型"),
    resource_id: str = Query(..., description="资源ID"),
    current_user: AdminUser = Depends(require_permission("rbac:users:edit")),
    db: Session = Depends(get_db)
):
    """删除用户资源权限"""
    target_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if target_user.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权操作其他租户的用户")
    
    db.query(ResourcePermission).filter(
        and_(
            ResourcePermission.admin_user_id == user_id,
            ResourcePermission.resource_type == resource_type,
            ResourcePermission.resource_id == resource_id
        )
    ).delete()
    
    db.commit()
    
    return {"message": "资源权限已删除"}
