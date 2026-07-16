#
# 权限验证 — FastAPI 依赖
#

from typing import List, Optional, Callable
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from fnmatch import fnmatchcase

from app.core.auth import get_current_user
from app.database.base import get_db, tenant_id_context
from app.database.models import AdminUser
from app.services.role_service import MembershipRoleService


def has_permission(permissions: List[str], required: str) -> bool:
    if not permissions:
        return False
    if "*" in permissions or "tenant.*" in permissions:
        return True
    for p in permissions:
        if p == required:
            return True
        if "*" in p and fnmatchcase(required, p):
            return True
    return False


def check_permission(
    user_id: UUID,
    permission: str,
    db: Session,
    tenant_id: Optional[UUID] = None,
) -> bool:
    if tenant_id is None:
        try:
            tenant_id = tenant_id_context.get()
        except LookupError:
            tenant_id = None
    if not tenant_id:
        return False
    permissions = MembershipRoleService.get_user_permissions(
        db=db, admin_user_id=user_id, tenant_id=tenant_id
    )
    return has_permission(permissions=permissions, required=permission)


def get_current_admin_user(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminUser:
    user_id = UUID(current_user["user_id"])
    admin_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not admin_user:
        raise HTTPException(status_code=404, detail="User not found")
    if not admin_user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    return admin_user


def require_permission(permission: str) -> Callable:
    """FastAPI 依赖：要求特定权限。"""

    async def _checker(
        admin_user: AdminUser = Depends(get_current_admin_user),
        db: Session = Depends(get_db),
    ) -> AdminUser:
        if admin_user.is_super_admin:
            return admin_user
        try:
            tenant_id = tenant_id_context.get()
        except LookupError:
            raise HTTPException(status_code=403, detail="Tenant context required")
        if not check_permission(admin_user.id, permission, db, tenant_id):
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return admin_user

    return _checker


def require_any_permission(permissions: List[str]) -> Callable:
    async def _checker(
        admin_user: AdminUser = Depends(get_current_admin_user),
        db: Session = Depends(get_db),
    ) -> AdminUser:
        if admin_user.is_super_admin:
            return admin_user
        try:
            tenant_id = tenant_id_context.get()
        except LookupError:
            raise HTTPException(status_code=403, detail="Tenant context required")
        for perm in permissions:
            if check_permission(admin_user.id, perm, db, tenant_id):
                return admin_user
        raise HTTPException(status_code=403, detail="Permission denied")

    return _checker
