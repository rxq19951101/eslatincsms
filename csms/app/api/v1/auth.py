#
# 认证API
# 提供登录、登出、Token刷新等功能
#

from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database.base import get_db
from app.database.models import AdminUser, LoginHistory, Tenant
from app.core.security import (
    verify_password, get_password_hash, 
    create_access_token, create_refresh_token, verify_token
)
from app.core.config import get_settings
from app.core.auth import get_current_admin_user
from app.core.exceptions import PermissionDenied

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["认证"])

security = HTTPBearer()


# ==================== 请求/响应模型 ====================

class LoginRequest(BaseModel):
    """登录请求"""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshTokenRequest(BaseModel):
    """刷新Token请求"""
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    """刷新Token响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str


class UserInfoResponse(BaseModel):
    """用户信息响应"""
    id: str
    username: str
    email: str
    tenant_id: Optional[str]
    tenant_name: Optional[str]
    is_super_admin: bool
    roles: list
    permissions: list


# ==================== 认证端点 ====================

@router.post("/login", response_model=LoginResponse, summary="管理员登录")
async def login(
    login_data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    管理员用户登录
    
    - 验证邮箱和密码
    - 检查账号状态
    - 生成JWT Token（包含tenant_id和权限信息）
    - 记录登录历史
    """
    # 查询用户
    admin_user = db.query(AdminUser).filter(AdminUser.email == login_data.email).first()
    
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误"
        )
    
    # 验证密码
    if not verify_password(login_data.password, admin_user.password_hash):
        # 增加失败计数
        admin_user.login_failed_count += 1
        
        # 检查是否需要锁定账号
        max_failures = 5
        if admin_user.login_failed_count >= max_failures:
            admin_user.status = "locked"
            admin_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"账号已被锁定，请30分钟后重试"
            )
        
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误"
        )
    
    # 检查账号状态
    if admin_user.status != "active":
        if admin_user.status == "locked":
            if admin_user.locked_until and admin_user.locked_until > datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"账号已被锁定，请稍后重试"
                )
            else:
                # 锁定时间已过，解锁账号
                admin_user.status = "active"
                admin_user.login_failed_count = 0
                admin_user.locked_until = None
        
        if admin_user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已被禁用"
            )
    
    # 检查租户状态
    tenant = None
    if admin_user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == admin_user.tenant_id).first()
        if tenant and tenant.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="租户已被暂停或禁用"
            )
    
    # 重置失败计数
    admin_user.login_failed_count = 0
    admin_user.last_login_at = datetime.now(timezone.utc)
    admin_user.last_login_ip = request.client.host if request.client else None
    
    # 获取用户权限
    from app.core.auth import get_user_permissions
    permissions = get_user_permissions(admin_user, db)
    
    # 获取用户角色
    roles = [role.role.code for role in admin_user.roles]
    
    # 生成Token
    token_data = {
        "sub": admin_user.id,
        "email": admin_user.email,
        "tenant_id": admin_user.tenant_id,
        "is_super_admin": admin_user.is_super_admin,
        "roles": roles,
        "permissions": permissions
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    # 记录登录历史
    login_history = LoginHistory(
        admin_user_id=admin_user.id,
        login_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    db.add(login_history)
    db.commit()
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        user={
            "id": admin_user.id,
            "username": admin_user.username,
            "email": admin_user.email,
            "tenant_id": admin_user.tenant_id,
            "tenant_name": tenant.name if tenant else None,
            "is_super_admin": admin_user.is_super_admin,
            "roles": roles
        }
    )


@router.post("/refresh", response_model=RefreshTokenResponse, summary="刷新Token")
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    刷新访问令牌
    
    - 验证Refresh Token
    - 生成新的Access Token和Refresh Token
    """
    payload = verify_token(refresh_data.refresh_token)
    
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌"
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌数据"
        )
    
    # 验证用户是否存在且活跃
    admin_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not admin_user or admin_user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用"
        )
    
    # 检查租户状态
    if admin_user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == admin_user.tenant_id).first()
        if tenant and tenant.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="租户已被暂停或禁用"
            )
    
    # 重新获取权限（可能已更新）
    from app.core.auth import get_user_permissions
    permissions = get_user_permissions(admin_user, db)
    roles = [role.role.code for role in admin_user.roles]
    
    # 生成新Token
    token_data = {
        "sub": admin_user.id,
        "email": admin_user.email,
        "tenant_id": admin_user.tenant_id,
        "is_super_admin": admin_user.is_super_admin,
        "roles": roles,
        "permissions": permissions
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    return RefreshTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60
    )


@router.post("/logout", summary="登出")
async def logout(
    current_user: AdminUser = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    用户登出
    
    - 记录登出时间（更新登录历史）
    - 可选：将Token加入黑名单（需要Redis支持）
    """
    # 更新最近的登录历史记录
    login_history = db.query(LoginHistory).filter(
        LoginHistory.admin_user_id == current_user.id
    ).order_by(LoginHistory.login_at.desc()).first()
    
    if login_history:
        login_history.logout_at = datetime.now(timezone.utc)
        if login_history.login_at:
            duration = (login_history.logout_at - login_history.login_at).total_seconds()
            login_history.session_duration = int(duration)
        db.commit()
    
    return {"message": "登出成功"}


@router.get("/me", response_model=UserInfoResponse, summary="获取当前用户信息")
async def get_current_user_info(
    current_user: AdminUser = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取当前登录用户的信息
    
    - 用户基本信息
    - 所属租户信息
    - 角色和权限列表
    """
    # 获取租户信息
    tenant = None
    if current_user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    
    # 获取角色和权限
    from app.core.auth import get_user_permissions
    permissions = get_user_permissions(current_user, db)
    roles = [{"id": role.role.id, "code": role.role.code, "name": role.role.name} for role in current_user.roles]
    
    return UserInfoResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        tenant_id=current_user.tenant_id,
        tenant_name=tenant.name if tenant else None,
        is_super_admin=current_user.is_super_admin,
        roles=roles,
        permissions=permissions
    )


@router.post("/change-password", summary="修改密码")
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: AdminUser = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    修改当前用户密码
    
    - 验证旧密码
    - 更新为新密码
    """
    # 验证旧密码
    if not verify_password(password_data.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误"
        )
    
    # 更新密码
    current_user.password_hash = get_password_hash(password_data.new_password)
    db.commit()
    
    return {"message": "密码修改成功"}
