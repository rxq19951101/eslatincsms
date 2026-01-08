#
# 运营后台用户管理API
# 提供管理员用户的CRUD、角色分配、登录历史等功能
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from datetime import datetime, timezone, timedelta

from app.database.base import get_db
from app.database.models import AdminUser, LoginHistory, AuditLog, Tenant, AdminUserRole, Role
from app.core.auth import (
    get_current_admin_user, require_permission,
    get_user_permissions
)
from app.core.security import get_password_hash, verify_password
from app.core.exceptions import PermissionDenied

router = APIRouter(prefix="/admin-users", tags=["运营后台用户管理"])


# ==================== 请求/响应模型 ====================

class AdminUserResponse(BaseModel):
    """管理员用户响应"""
    id: str
    username: str
    email: str
    phone: Optional[str]
    tenant_id: Optional[str]
    tenant_name: Optional[str]
    status: str
    is_super_admin: bool
    last_login_at: Optional[datetime]
    last_login_ip: Optional[str]
    roles: List[dict] = []
    created_at: datetime
    created_by: Optional[str]
    
    class Config:
        from_attributes = True


class AdminUserCreateRequest(BaseModel):
    """创建管理员用户请求"""
    username: str
    email: EmailStr
    password: str
    phone: Optional[str] = None
    tenant_id: Optional[str] = None
    role_ids: List[int] = []


class AdminUserUpdateRequest(BaseModel):
    """更新管理员用户请求"""
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    status: Optional[str] = None
    role_ids: Optional[List[int]] = None


class LoginHistoryResponse(BaseModel):
    """登录历史响应"""
    id: int
    login_ip: Optional[str]
    user_agent: Optional[str]
    login_at: datetime
    logout_at: Optional[datetime]
    session_duration: Optional[int]
    
    class Config:
        from_attributes = True


# ==================== 用户管理端点 ====================

@router.get("", response_model=List[AdminUserResponse], summary="获取管理员用户列表")
async def get_admin_users(
    tenant_id: Optional[str] = Query(None, description="按租户筛选"),
    status_filter: Optional[str] = Query(None, description="按状态筛选"),
    current_user: AdminUser = Depends(require_permission("rbac:users:view")),
    db: Session = Depends(get_db)
):
    """
    获取管理员用户列表
    
    - 普通用户只能看到自己租户的用户
    - 超级管理员可以看到所有用户
    """
    query = db.query(AdminUser)
    
    # 非超级管理员只能看到自己租户的用户
    if not current_user.is_super_admin:
        query = query.filter(AdminUser.tenant_id == current_user.tenant_id)
    elif tenant_id:
        query = query.filter(AdminUser.tenant_id == tenant_id)
    
    if status_filter:
        query = query.filter(AdminUser.status == status_filter)
    
    users = query.order_by(desc(AdminUser.created_at)).all()
    
    # 构建响应
    result = []
    for user in users:
        # 获取租户信息
        tenant = None
        if user.tenant_id:
            tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        
        # 获取角色
        roles = db.query(Role).join(AdminUserRole).filter(
            AdminUserRole.admin_user_id == user.id
        ).all()
        
        result.append(AdminUserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            phone=user.phone,
            tenant_id=user.tenant_id,
            tenant_name=tenant.name if tenant else None,
            status=user.status,
            is_super_admin=user.is_super_admin,
            last_login_at=user.last_login_at,
            last_login_ip=user.last_login_ip,
            roles=[{"id": r.id, "code": r.code, "name": r.name} for r in roles],
            created_at=user.created_at,
            created_by=user.created_by
        ))
    
    return result


@router.get("/{user_id}", response_model=AdminUserResponse, summary="获取管理员用户详情")
async def get_admin_user(
    user_id: str,
    current_user: AdminUser = Depends(require_permission("rbac:users:view")),
    db: Session = Depends(get_db)
):
    """获取管理员用户详情"""
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if user.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权查看其他租户的用户")
    
    # 获取租户信息
    tenant = None
    if user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    
    # 获取角色
    roles = db.query(Role).join(AdminUserRole).filter(
        AdminUserRole.admin_user_id == user.id
    ).all()
    
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        phone=user.phone,
        tenant_id=user.tenant_id,
        tenant_name=tenant.name if tenant else None,
        status=user.status,
        is_super_admin=user.is_super_admin,
        last_login_at=user.last_login_at,
        last_login_ip=user.last_login_ip,
        roles=[{"id": r.id, "code": r.code, "name": r.name} for r in roles],
        created_at=user.created_at,
        created_by=user.created_by
    )


@router.post("", response_model=AdminUserResponse, summary="创建管理员用户")
async def create_admin_user(
    user_data: AdminUserCreateRequest,
    current_user: AdminUser = Depends(require_permission("rbac:users:create")),
    db: Session = Depends(get_db)
):
    """
    创建管理员用户
    
    - 普通用户只能为自己租户创建用户
    - 需要 rbac:users:create 权限
    """
    # 检查邮箱是否已存在
    existing_user = db.query(AdminUser).filter(AdminUser.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被使用"
        )
    
    # 确定租户ID
    tenant_id = user_data.tenant_id or current_user.tenant_id
    
    # 检查权限（非超级管理员只能为自己租户创建用户）
    if not current_user.is_super_admin:
        if tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权为其他租户创建用户")
    
    # 验证租户是否存在
    if tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="租户不存在"
            )
    
    # 生成用户ID
    from app.core.id_generator import generate_order_id
    user_id = f"admin_{generate_order_id()}"
    
    # 创建用户
    admin_user = AdminUser(
        id=user_id,
        tenant_id=tenant_id,
        username=user_data.username,
        email=user_data.email,
        phone=user_data.phone,
        password_hash=get_password_hash(user_data.password),
        status="active",
        is_super_admin=False,
        created_by=current_user.id
    )
    db.add(admin_user)
    db.flush()
    
    # 分配角色
    if user_data.role_ids:
        roles = db.query(Role).filter(Role.id.in_(user_data.role_ids)).all()
        
        # 验证角色权限
        if not current_user.is_super_admin:
            for role in roles:
                if role.tenant_id != current_user.tenant_id and role.role_type != "system":
                    raise PermissionDenied(f"无权分配角色 {role.name}")
        
        for role in roles:
            user_role = AdminUserRole(
                admin_user_id=admin_user.id,
                role_id=role.id
            )
            db.add(user_role)
    
    db.commit()
    db.refresh(admin_user)
    
    # 获取租户和角色信息
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first() if tenant_id else None
    roles = db.query(Role).join(AdminUserRole).filter(
        AdminUserRole.admin_user_id == admin_user.id
    ).all()
    
    return AdminUserResponse(
        id=admin_user.id,
        username=admin_user.username,
        email=admin_user.email,
        phone=admin_user.phone,
        tenant_id=admin_user.tenant_id,
        tenant_name=tenant.name if tenant else None,
        status=admin_user.status,
        is_super_admin=admin_user.is_super_admin,
        last_login_at=admin_user.last_login_at,
        last_login_ip=admin_user.last_login_ip,
        roles=[{"id": r.id, "code": r.code, "name": r.name} for r in roles],
        created_at=admin_user.created_at,
        created_by=admin_user.created_by
    )


@router.put("/{user_id}", response_model=AdminUserResponse, summary="更新管理员用户")
async def update_admin_user(
    user_id: str,
    user_data: AdminUserUpdateRequest,
    current_user: AdminUser = Depends(require_permission("rbac:users:edit")),
    db: Session = Depends(get_db)
):
    """更新管理员用户"""
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if user.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权修改其他租户的用户")
        if user.is_super_admin:
            raise PermissionDenied("无权修改超级管理员")
    
    # 更新基本信息
    if user_data.username is not None:
        user.username = user_data.username
    if user_data.email is not None:
        # 检查邮箱是否已被其他用户使用
        existing = db.query(AdminUser).filter(
            and_(AdminUser.email == user_data.email, AdminUser.id != user_id)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已被使用"
            )
        user.email = user_data.email
    if user_data.phone is not None:
        user.phone = user_data.phone
    if user_data.status is not None:
        user.status = user_data.status
    
    # 更新角色
    if user_data.role_ids is not None:
        # 删除旧角色
        db.query(AdminUserRole).filter(AdminUserRole.admin_user_id == user_id).delete()
        
        # 添加新角色
        if user_data.role_ids:
            roles = db.query(Role).filter(Role.id.in_(user_data.role_ids)).all()
            
            # 验证角色权限
            if not current_user.is_super_admin:
                for role in roles:
                    if role.tenant_id != current_user.tenant_id and role.role_type != "system":
                        raise PermissionDenied(f"无权分配角色 {role.name}")
            
            for role in roles:
                user_role = AdminUserRole(
                    admin_user_id=user.id,
                    role_id=role.id
                )
                db.add(user_role)
    
    db.commit()
    db.refresh(user)
    
    # 获取租户和角色信息
    tenant = None
    if user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    roles = db.query(Role).join(AdminUserRole).filter(
        AdminUserRole.admin_user_id == user.id
    ).all()
    
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        phone=user.phone,
        tenant_id=user.tenant_id,
        tenant_name=tenant.name if tenant else None,
        status=user.status,
        is_super_admin=user.is_super_admin,
        last_login_at=user.last_login_at,
        last_login_ip=user.last_login_ip,
        roles=[{"id": r.id, "code": r.code, "name": r.name} for r in roles],
        created_at=user.created_at,
        created_by=user.created_by
    )


@router.delete("/{user_id}", summary="删除管理员用户")
async def delete_admin_user(
    user_id: str,
    current_user: AdminUser = Depends(require_permission("rbac:users:delete")),
    db: Session = Depends(get_db)
):
    """删除管理员用户"""
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if user.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权删除其他租户的用户")
        if user.is_super_admin:
            raise PermissionDenied("无权删除超级管理员")
    
    # 不能删除自己
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己"
        )
    
    db.delete(user)
    db.commit()
    
    return {"message": "用户已删除"}


@router.put("/{user_id}/status", summary="更新用户状态")
async def update_user_status(
    user_id: str,
    status: str = Query(..., description="新状态: active, disabled, locked"),
    current_user: AdminUser = Depends(require_permission("rbac:users:edit")),
    db: Session = Depends(get_db)
):
    """更新用户状态（启用/禁用/锁定）"""
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if user.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权操作其他租户的用户")
        if user.is_super_admin:
            raise PermissionDenied("无权操作超级管理员")
    
    if status not in ["active", "disabled", "locked"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的状态值"
        )
    
    user.status = status
    if status == "locked":
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
    else:
        user.locked_until = None
        user.login_failed_count = 0
    
    db.commit()
    
    return {"message": f"用户状态已更新为 {status}"}


@router.post("/{user_id}/reset-password", summary="重置用户密码")
async def reset_user_password(
    user_id: str,
    new_password: str = Query(..., description="新密码"),
    current_user: AdminUser = Depends(require_permission("rbac:users:edit")),
    db: Session = Depends(get_db)
):
    """重置用户密码"""
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if user.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权操作其他租户的用户")
    
    user.password_hash = get_password_hash(new_password)
    user.login_failed_count = 0
    user.locked_until = None
    
    db.commit()
    
    return {"message": "密码已重置"}


# ==================== 登录历史端点 ====================

@router.get("/{user_id}/login-history", response_model=List[LoginHistoryResponse], summary="获取用户登录历史")
async def get_user_login_history(
    user_id: str,
    limit: int = Query(30, description="返回记录数"),
    current_user: AdminUser = Depends(require_permission("rbac:users:view")),
    db: Session = Depends(get_db)
):
    """获取用户登录历史"""
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查权限
    if not current_user.is_super_admin:
        if user.tenant_id != current_user.tenant_id:
            raise PermissionDenied("无权查看其他租户的用户")
    
    history = db.query(LoginHistory).filter(
        LoginHistory.admin_user_id == user_id
    ).order_by(desc(LoginHistory.login_at)).limit(limit).all()
    
    return history
