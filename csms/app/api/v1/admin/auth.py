#
# 管理员认证API
# 提供登录、登出、刷新token、获取当前用户信息等功能
#

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from app.database.base import get_db, SuperSessionLocal, is_super_admin_context, use_super_connection_context
from app.database.models import AdminUser, TenantMembership, Tenant
from app.core.auth import (
    get_current_user,
    verify_password,
    get_password_hash,
    verify_token
)
from app.core.permissions import get_current_admin_user
from app.services.role_service import MembershipRoleService
from app.services.token_service import (
    create_token_pair,
    save_refresh_token,
    refresh_token_pair,
    revoke_refresh_token
)
from app.services.user_service import AdminUserService
from app.services.membership_service import MembershipService
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SetDefaultTenantRequest(BaseModel):
    tenant_id: UUID


class UserInfoResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str]
    is_super_admin: bool
    default_tenant_id: Optional[str]
    tenant_list: list


class PermissionsResponse(BaseModel):
    permissions: list


# ==================== 认证端点 ====================

@router.post("/login", response_model=LoginResponse, summary="管理员登录")
async def login(
    request_data: LoginRequest,
    request: Request
):
    """管理员登录"""
    # 登录接口需要绕过 RLS 检查（因为还没有认证，无法获取 tenant_id）
    # 使用 SuperSessionLocal 来绕过 RLS
    db: Session = SuperSessionLocal()
    
    try:
        # 设置超级管理员上下文（临时，用于登录操作）
        is_super_admin_context.set(True)
        use_super_connection_context.set(True)
        
        # 验证用户名和密码
        admin_user = AdminUserService.get_admin_user_by_username(db, request_data.username)
        
        if not admin_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        
        if not admin_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive"
            )
        
        if not verify_password(request_data.password, admin_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        
        # 更新最后登录时间
        admin_user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        
        # 生成 token pair
        access_token, refresh_token = await create_token_pair(
            user_id=admin_user.id,
            user_type="admin",
            audience="admin",
            is_super_admin=admin_user.is_super_admin,
            request=request
        )
        
        # 保存 refresh token（从刚创建的token中提取信息，使用base64解码，不经过jwt验证）
        # 因为create_refresh_token已经包含了exp信息，我们需要提取jti和exp
        try:
            import base64
            import json
            
            # JWT格式：header.payload.signature
            parts = refresh_token.split('.')
            if len(parts) >= 2:
                # 解码payload（base64url）
                payload_encoded = parts[1]
                # 添加填充（base64url解码）
                padding = 4 - len(payload_encoded) % 4
                if padding != 4:
                    payload_encoded += '=' * padding
                payload_bytes = base64.urlsafe_b64decode(payload_encoded)
                payload_dict = json.loads(payload_bytes.decode('utf-8'))
                
                refresh_jti = payload_dict.get("jti")
                exp = payload_dict.get("exp")
                refresh_expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else datetime.now(timezone.utc) + timedelta(days=7)
                
                logger.info(f"从refresh token提取信息成功: jti={refresh_jti}, exp={exp}")
            else:
                raise ValueError("Invalid JWT format")
        except Exception as e:
            logger.error(f"解析refresh token失败: {e}", exc_info=True)
            # 如果解析失败，使用默认值（不应该发生，但为了容错）
            import secrets
            refresh_jti = secrets.token_urlsafe(32)
            refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            logger.warning(f"使用默认值保存refresh token: jti={refresh_jti}")
        
        await save_refresh_token(
            jti=refresh_jti,
            user_id=admin_user.id,
            user_type="admin",
            refresh_token=refresh_token,
            expires_at=refresh_expires_at,
            db=db,
            request=request
        )
        
        logger.info(f"Refresh token已保存: jti={refresh_jti}, user_id={admin_user.id}")
        
        # 获取用户的默认租户信息（用于登录响应）
        from app.services.membership_service import MembershipService
        memberships = MembershipService.get_user_tenants(db, admin_user.id)
        default_tenant = next((m for m in memberships if m.is_primary), None)
        
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user={
                "id": str(admin_user.id),
                "username": admin_user.username,
                "email": admin_user.email,
                "full_name": admin_user.full_name,
                "is_super_admin": admin_user.is_super_admin,
                # 登录响应中包含默认租户 ID，方便前端使用
                "default_tenant_id": str(default_tenant.tenant_id) if default_tenant else None
            }
        )
    finally:
        # 清理上下文
        is_super_admin_context.set(False)
        use_super_connection_context.set(False)
        db.close()


@router.post("/refresh", response_model=RefreshTokenResponse, summary="刷新token")
async def refresh(
    request_data: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """刷新 access token 和 refresh token"""
    new_access_token, new_refresh_token = await refresh_token_pair(
        refresh_token=request_data.refresh_token,
        request=request,
        db=db
    )
    
    return RefreshTokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token
    )


@router.post("/logout", summary="登出")
async def logout(
    request_data: RefreshTokenRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """登出（撤销 refresh token）"""
    from app.services.token_service import revoke_refresh_token
    
    # 撤销refresh_token
    await revoke_refresh_token(request_data.refresh_token, request, db)
    
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserInfoResponse, summary="获取当前用户信息")
async def get_current_user_info(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """获取当前管理员信息（包含默认租户）"""
    # #region agent log
    all_headers = dict(request.headers)
    x_tenant_id_header = request.headers.get("X-Tenant-Id") or request.headers.get("x-tenant-id")
    logger.info(f"[DEBUG] /me ENTRY - method={request.method}, path={request.url.path}, X-Tenant-Id={x_tenant_id_header}, current_user_from_depends={current_user}")
    # #endregion
    
    # #region agent log
    from app.database.base import tenant_id_context
    try:
        tenant_id_from_context = tenant_id_context.get()
        logger.info(f"[DEBUG] /me - tenant_id_from_context: {tenant_id_from_context}")
    except LookupError:
        logger.info(f"[DEBUG] /me - tenant_id_from_context: None (LookupError)")
    # #endregion
    
    from uuid import UUID
    user_id = UUID(current_user["user_id"])
    is_super_admin = current_user.get("global_role") == "super_admin" or current_user.get("is_super_admin", False)
    
    # /me 接口用于获取用户自己的信息，应该允许在没有 tenant_id header 的情况下访问
    # 使用 SuperSessionLocal 绕过 RLS 检查（因为这是查询用户自己的信息）
    db: Session = SuperSessionLocal()
    
    try:
        # #region agent log
        logger.info(f"[DEBUG] /me - Querying user info with SuperSessionLocal, user_id={user_id}, is_super_admin={is_super_admin}")
        # #endregion
        
        # 获取用户信息
        admin_user = AdminUserService.get_admin_user_by_id(db, user_id)
        if not admin_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # #region agent log
        logger.info(f"[DEBUG] /me - Admin user found: username={admin_user.username}, is_super_admin={admin_user.is_super_admin}")
        # #endregion
        
        # 获取用户所属的所有租户
        memberships = MembershipService.get_user_tenants(db, user_id)
        
        # #region agent log
        logger.info(f"[DEBUG] /me - User memberships retrieved: count={len(memberships)}, memberships={[{'tenant_id': str(m.tenant_id), 'is_primary': m.is_primary} for m in memberships]}")
        # #endregion
        
        # 找到默认租户
        default_tenant = next((m for m in memberships if m.is_primary), None)
        
        # 构建租户列表
        tenant_list = []
        for m in memberships:
            tenant = db.query(Tenant).filter(Tenant.id == m.tenant_id).first()
            if tenant:
                tenant_list.append({
                    "id": str(tenant.id),
                    "name": tenant.name,
                    "is_primary": m.is_primary
                })
        
        # #region agent log
        logger.info(f"[DEBUG] /me - Building response: default_tenant_id={str(default_tenant.tenant_id) if default_tenant else None}, tenant_list_count={len(tenant_list)}")
        # #endregion
        
        result = UserInfoResponse(
            id=str(admin_user.id),
            username=admin_user.username,
            email=admin_user.email,
            full_name=admin_user.full_name,
            is_super_admin=admin_user.is_super_admin,
            default_tenant_id=str(default_tenant.tenant_id) if default_tenant else None,
            tenant_list=tenant_list
        )
        
        # #region agent log
        logger.info(f"[DEBUG] /me - SUCCESS: default_tenant_id={result.default_tenant_id}, tenant_list_size={len(result.tenant_list)}")
        # #endregion
        
        return result
    finally:
        db.close()


@router.get("/me/permissions", response_model=PermissionsResponse, summary="获取当前用户在当前租户下的权限列表")
async def get_my_permissions(
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    返回当前管理员在“当前租户”（tenant_middleware 解析的 tenant_id_context）下的合并权限列表。

    - super_admin：返回 ["*"]
    - 普通管理员：必须存在 tenant_id_context，否则 403
    """
    if getattr(current_user_obj, "is_super_admin", False):
        return PermissionsResponse(permissions=["*"])

    from app.database.base import tenant_id_context

    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")

    perms = MembershipRoleService.get_user_permissions(
        db=db, admin_user_id=current_user_obj.id, tenant_id=tenant_id
    )
    return PermissionsResponse(permissions=perms)


@router.put("/me/default-tenant", summary="设置默认租户")
async def set_default_tenant(
    request_data: SetDefaultTenantRequest,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """设置用户的默认租户"""
    user_id = current_user_obj.id
    
    MembershipService.set_primary_tenant(
        db=db,
        admin_user_id=user_id,
        tenant_id=request_data.tenant_id
    )
    
    return {"message": "Default tenant updated"}
