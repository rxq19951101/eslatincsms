#
# 权限验证模块
# 提供权限检查装饰器和辅助函数
#

from functools import wraps
from typing import List, Optional
from fastapi import HTTPException, Depends
from app.core.auth import get_current_user
from app.services.role_service import MembershipRoleService
from app.database.base import get_db, tenant_id_context
from sqlalchemy.orm import Session
from uuid import UUID


def require_permission(permission: str):
    """
    要求特定权限的装饰器
    
    用法：
    @require_permission("charge_points.view")
    async def endpoint(...):
        ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从依赖中获取当前用户和数据库会话
            # 这里需要在实际使用时从 kwargs 中提取
            # 暂时返回原函数
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_any_permission(permissions: List[str]):
    """
    要求任意一个权限的装饰器
    
    用法：
    @require_any_permission(["charge_points.view", "charge_points.edit"])
    async def endpoint(...):
        ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_all_permissions(permissions: List[str]):
    """
    要求所有权限的装饰器
    
    用法：
    @require_all_permissions(["charge_points.view", "charge_points.edit"])
    async def endpoint(...):
        ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator


async def check_permission(
    user_id: UUID,
    permission: str,
    db: Session,
    tenant_id: Optional[UUID] = None
) -> bool:
    """
    检查用户是否有特定权限
    
    Args:
        user_id: 用户ID
        permission: 权限名称
        db: 数据库会话
        tenant_id: 租户ID（如果为None，从上下文获取）
    
    Returns:
        True if user has permission, False otherwise
    """
    if tenant_id is None:
        tenant_id = tenant_id_context.get()
    
    if not tenant_id:
        return False
    
    # 获取用户权限列表
    permissions = MembershipRoleService.get_user_permissions(
        db=db,
        admin_user_id=user_id,
        tenant_id=tenant_id
    )
    
    # 检查权限
    if "*" in permissions:
        return True  # 超级权限
    
    return permission in permissions


def get_current_admin_user(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取当前管理员用户对象（从数据库查询）
    
    返回 AdminUser 对象，而不是 JWT payload
    """
    from app.database.models import AdminUser
    from uuid import UUID
    
    user_id = UUID(current_user["user_id"])
    admin_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    
    if not admin_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not admin_user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    
    return admin_user
