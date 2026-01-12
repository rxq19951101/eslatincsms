#
# 终端用户认证API
# 提供注册、登录、登出、刷新token等功能
#

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from app.database.base import get_db
from app.database.models import EndUser
from app.core.auth import get_current_user, verify_password
from app.services.token_service import (
    create_token_pair,
    save_refresh_token,
    refresh_token_pair,
    revoke_refresh_token
)
from app.services.user_service import EndUserService
from datetime import datetime, timezone
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class RegisterRequest(BaseModel):
    phone: str
    id_tag: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    tenant_id: UUID  # 注册时需要指定租户


class LoginRequest(BaseModel):
    phone: str
    tenant_id: UUID


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


# 邮箱注册/登录请求模型
class EmailRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    tenant_id: UUID


class EmailLoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: UUID
    remember_me: bool = False


# ==================== 认证端点 ====================

@router.post("/register", summary="终端用户注册")
async def register(
    request_data: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """终端用户注册"""
    # 创建终端用户
    end_user = EndUserService.create_end_user(
        db=db,
        tenant_id=request_data.tenant_id,
        phone=request_data.phone,
        id_tag=request_data.id_tag,
        email=request_data.email,
        full_name=request_data.full_name
    )
    
    return {
        "message": "User registered successfully",
        "user_id": str(end_user.id)
    }


@router.post("/login", response_model=LoginResponse, summary="终端用户登录")
async def login(
    request_data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """终端用户登录（基于手机号和租户）"""
    # 查找用户
    end_user = EndUserService.get_end_user_by_phone(
        db=db,
        tenant_id=request_data.tenant_id,
        phone=request_data.phone
    )
    
    if not end_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone or tenant"
        )
    
    if end_user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )
    
    # 更新最后登录时间
    end_user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    
    # 生成 token pair
    access_token, refresh_token = await create_token_pair(
        user_id=end_user.id,
        user_type="end_user",
        audience="app",
        is_super_admin=False,
        request=request
    )
    
    # 保存 refresh token（需要从token中提取audience）
    from app.core.auth import verify_token
    from jose import jwt
    from app.core.config import get_settings
    settings = get_settings()
    try:
        unverified_payload = jwt.decode(
            refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_signature": False}
        )
        token_audience = unverified_payload.get("aud")
        refresh_payload = verify_token(refresh_token, audience=token_audience)
    except Exception:
        refresh_payload = None
    
    if not refresh_payload:
        raise HTTPException(status_code=500, detail="Failed to verify refresh token")
    
    refresh_jti = refresh_payload.get("jti")
    from datetime import timedelta
    refresh_expires_at = datetime.fromtimestamp(refresh_payload.get("exp"), tz=timezone.utc)
    
    await save_refresh_token(
        jti=refresh_jti,
        user_id=end_user.id,
        user_type="end_user",
        refresh_token=refresh_token,
        expires_at=refresh_expires_at,
        db=db,
        request=request
    )
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": str(end_user.id),
            "phone": end_user.phone,
            "email": end_user.email,
            "full_name": end_user.full_name,
            "tenant_id": str(end_user.tenant_id)
        }
    )


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


@router.get("/me", summary="获取当前用户信息")
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前终端用户信息"""
    user_id = UUID(current_user["user_id"])
    
    end_user = EndUserService.get_end_user_by_id(db, user_id)
    if not end_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": str(end_user.id),
        "phone": end_user.phone,
        "email": end_user.email,
        "full_name": end_user.full_name,
        "id_tag": end_user.id_tag,
        "balance": float(end_user.balance),
        "tenant_id": str(end_user.tenant_id),
        "status": end_user.status,
        "email_verified": end_user.email_verified if hasattr(end_user, 'email_verified') else False
    }


# ==================== 邮箱认证端点 ====================

@router.post("/register-email", summary="邮箱注册")
async def register_with_email(
    request_data: EmailRegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """使用邮箱和密码注册"""
    from app.core.auth import get_password_hash
    
    # 检查邮箱是否已被注册
    existing_user = db.query(EndUser).filter(
        EndUser.tenant_id == request_data.tenant_id,
        EndUser.email == request_data.email
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # 创建新用户
    new_user = EndUser()
    new_user.tenant_id = request_data.tenant_id
    new_user.email = request_data.email
    new_user.full_name = request_data.full_name
    new_user.password_hash = get_password_hash(request_data.password)
    new_user.email_verified = False
    new_user.status = "active"
    new_user.balance = 0
    new_user.created_at = datetime.now(timezone.utc)
    new_user.updated_at = datetime.now(timezone.utc)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "success": True,
        "message": "User registered successfully",
        "user_id": str(new_user.id)
    }


@router.post("/login-email", response_model=LoginResponse, summary="邮箱登录")
async def login_with_email(
    request_data: EmailLoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """使用邮箱和密码登录"""
    logger.info(f"Login attempt for email: {request_data.email}, tenant: {request_data.tenant_id}")
    
    # 查找用户
    end_user = db.query(EndUser).filter(
        EndUser.tenant_id == request_data.tenant_id,
        EndUser.email == request_data.email
    ).first()
    
    if not end_user:
        logger.warning(f"User not found: {request_data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    logger.info(f"User found: {end_user.email}, password_hash exists: {bool(end_user.password_hash)}")
    
    # 验证密码
    if not end_user.password_hash:
        logger.warning("Password hash is empty")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    password_valid = verify_password(request_data.password, end_user.password_hash)
    logger.info(f"Password verification result: {password_valid}")
    
    if not password_valid:
        logger.warning("Password verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if end_user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )
    
    # 更新最后登录时间
    end_user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    
    # 生成 token pair
    access_token, refresh_token = await create_token_pair(
        user_id=end_user.id,
        user_type="end_user",
        audience="app",
        is_super_admin=False,
        request=request
    )
    
    # 保存 refresh token
    from jose import jwt
    from app.core.config import get_settings
    settings = get_settings()
    
    unverified_payload = jwt.decode(
        refresh_token,
        settings.secret_key,
        algorithms=[settings.algorithm],
        options={"verify_signature": False, "verify_aud": False}
    )
    
    refresh_jti = unverified_payload.get("jti")
    refresh_expires_at = datetime.fromtimestamp(unverified_payload.get("exp"), tz=timezone.utc)
    
    await save_refresh_token(
        jti=refresh_jti,
        user_id=end_user.id,
        user_type="end_user",
        refresh_token=refresh_token,
        expires_at=refresh_expires_at,
        db=db,
        request=request
    )
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": str(end_user.id),
            "phone": end_user.phone,
            "email": end_user.email,
            "full_name": end_user.full_name,
            "email_verified": end_user.email_verified if hasattr(end_user, 'email_verified') else False,
            "tenant_id": str(end_user.tenant_id)
        }
    )
