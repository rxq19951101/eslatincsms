#
# 认证和授权核心模块
# 提供多租户和权限验证的依赖注入函数
#

from typing import Optional, List
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.database.base import get_db
from app.database.models import AdminUser, Role, Permission, RolePermission, AdminUserRole, ResourcePermission, Tenant
from app.core.security import get_current_user, verify_token
from app.core.exceptions import PermissionDenied, TenantAccessDenied


async def get_current_admin_user(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> AdminUser:
    """获取当前管理员用户对象"""
    user_id = current_user.get("sub")  # JWT中的用户ID
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的用户ID"
        )
    
    admin_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )
    
    if admin_user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户账号已被禁用或锁定"
        )
    
    return admin_user


async def get_current_tenant(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Optional[Tenant]:
    """获取当前租户对象"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        return None
    
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant and tenant.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="租户已被暂停或禁用"
        )
    return tenant


def get_user_permissions(admin_user: AdminUser, db: Session) -> List[str]:
    """获取用户的所有权限代码列表"""
    # 如果是超级管理员，返回所有权限
    if admin_user.is_super_admin:
        permissions = db.query(Permission.code).all()
        return [p[0] for p in permissions]
    
    # 查询用户的所有角色
    user_roles = db.query(Role).join(AdminUserRole).filter(
        AdminUserRole.admin_user_id == admin_user.id
    ).all()
    
    if not user_roles:
        return []
    
    role_ids = [role.id for role in user_roles]
    
    # 查询这些角色的所有权限
    permissions = db.query(Permission.code).join(RolePermission).filter(
        RolePermission.role_id.in_(role_ids)
    ).distinct().all()
    
    return [p[0] for p in permissions]


def check_permission(required_permission: str, user_permissions: List[str]) -> bool:
    """检查用户是否拥有指定权限"""
    # 支持通配符权限，如 "chargers:*" 匹配 "chargers:view", "chargers:edit" 等
    if "*" in required_permission:
        prefix = required_permission.replace("*", "")
        return any(p.startswith(prefix) for p in user_permissions)
    
    return required_permission in user_permissions


def require_permission(permission: str):
    """权限验证装饰器（依赖注入）"""
    async def permission_checker(
        current_user: dict = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        admin_user = await get_current_admin_user(current_user, db)
        
        # 超级管理员拥有所有权限
        if admin_user.is_super_admin:
            return admin_user
        
        # 获取用户权限
        user_permissions = get_user_permissions(admin_user, db)
        
        # 检查权限
        if not check_permission(permission, user_permissions):
            raise PermissionDenied(f"缺少权限: {permission}")
        
        return admin_user
    
    return permission_checker


def require_permissions(permissions: List[str], require_all: bool = False):
    """多权限验证装饰器（依赖注入）
    
    Args:
        permissions: 需要的权限列表
        require_all: 是否需要所有权限（True）还是任一权限（False）
    """
    async def permission_checker(
        current_user: dict = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        admin_user = await get_current_admin_user(current_user, db)
        
        # 超级管理员拥有所有权限
        if admin_user.is_super_admin:
            return admin_user
        
        # 获取用户权限
        user_permissions = get_user_permissions(admin_user, db)
        
        # 检查权限
        has_permissions = [check_permission(p, user_permissions) for p in permissions]
        
        if require_all:
            if not all(has_permissions):
                missing = [p for p, has in zip(permissions, has_permissions) if not has]
                raise PermissionDenied(f"缺少权限: {', '.join(missing)}")
        else:
            if not any(has_permissions):
                raise PermissionDenied(f"缺少以下任一权限: {', '.join(permissions)}")
        
        return admin_user
    
    return permission_checker


def get_tenant_filter(admin_user: AdminUser, model_class, db: Session):
    """获取租户数据过滤条件（用于自动数据隔离）"""
    # 超级管理员可以访问所有租户数据（需要特殊权限）
    if admin_user.is_super_admin:
        # 检查是否有跨租户访问权限
        user_permissions = get_user_permissions(admin_user, db)
        if "super_admin:cross_tenant" in user_permissions:
            return None  # 不过滤
    
    # 普通用户只能访问自己租户的数据
    if hasattr(model_class, 'tenant_id'):
        return model_class.tenant_id == admin_user.tenant_id
    
    return None


async def get_tenant_context(
    request: Request,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """获取租户上下文（用于中间件）"""
    tenant_id = current_user.get("tenant_id")
    return {
        "tenant_id": tenant_id,
        "user_id": current_user.get("sub"),
        "is_super_admin": current_user.get("is_super_admin", False)
    }
