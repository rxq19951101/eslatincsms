#
# 终端用户认证API
# 提供注册、登录、登出、刷新token等功能
#

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from app.database.base import get_db
from app.database.models import AppUser
from app.core.auth import get_current_user, verify_password
from app.services.token_service import (
    create_token_pair,
    save_refresh_token,
    refresh_token_pair,
    revoke_refresh_token
)
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
    tenant_id: UUID  # 爆改阶段：不再支持（保留字段仅用于兼容历史调用）


class LoginRequest(BaseModel):
    phone: str
    tenant_id: UUID  # 爆改阶段：不再支持（保留字段仅用于兼容历史调用）


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
    full_name: Optional[str] = None
    phone: Optional[str] = None


class EmailLoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False


# ==================== 认证端点 ====================

@router.post("/register", summary="终端用户注册")
async def register(
    request_data: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """爆改阶段：禁用旧手机号/租户注册入口（强制使用邮箱注册）"""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Deprecated endpoint. Use /api/v1/app/auth/register-email"
    )


@router.post("/login", response_model=LoginResponse, summary="终端用户登录")
async def login(
    request_data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """爆改阶段：禁用旧手机号/租户登录入口（强制使用邮箱登录）"""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Deprecated endpoint. Use /api/v1/app/auth/login-email"
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
    """获取当前平台终端用户信息（AppUser）"""
    user_id = UUID(current_user["user_id"])

    app_user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not app_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": str(app_user.id),
        "phone": app_user.phone,
        "email": app_user.email,
        "full_name": app_user.full_name,
        "balance": float(app_user.balance or 0),
        "status": app_user.status,
        "email_verified": bool(app_user.email_verified),
        "created_at": app_user.created_at.isoformat() if app_user.created_at else None,
        "updated_at": app_user.updated_at.isoformat() if app_user.updated_at else None,
    }


# ==================== 邮箱认证端点 ====================

@router.post("/register-email", summary="邮箱注册")
async def register_with_email(
    request_data: EmailRegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """使用邮箱和密码注册（平台用户 AppUser）"""
    from app.core.auth import get_password_hash
    
    # 检查邮箱是否已被注册
    existing_user = db.query(AppUser).filter(AppUser.email == request_data.email).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    if request_data.phone:
        existing_phone = db.query(AppUser).filter(AppUser.phone == request_data.phone).first()
        if existing_phone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone already registered")

    # 创建新平台用户
    new_user = AppUser(
        email=request_data.email,
        phone=request_data.phone,
        full_name=request_data.full_name,
        password_hash=get_password_hash(request_data.password),
        email_verified=False,
        status="active",
        balance=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
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
    """使用邮箱和密码登录（平台用户 AppUser）"""
    logger.info(f"Login attempt for email: {request_data.email}")

    app_user = db.query(AppUser).filter(AppUser.email == request_data.email).first()
    if not app_user:
        logger.warning(f"User not found: {request_data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    logger.info(f"User found: {app_user.email}, password_hash exists: {bool(app_user.password_hash)}")
    
    # 验证密码
    if not app_user.password_hash:
        logger.warning("Password hash is empty")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    password_valid = verify_password(request_data.password, app_user.password_hash)
    logger.info(f"Password verification result: {password_valid}")
    
    if not password_valid:
        logger.warning("Password verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if app_user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )
    
    # 更新最后登录时间
    app_user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    
    # 生成 token pair
    access_token, refresh_token = await create_token_pair(
        user_id=app_user.id,
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
        user_id=app_user.id,
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
            "id": str(app_user.id),
            "phone": app_user.phone,
            "email": app_user.email,
            "full_name": app_user.full_name,
            "email_verified": bool(app_user.email_verified),
            "created_at": app_user.created_at.isoformat() if app_user.created_at else None,
            "updated_at": app_user.updated_at.isoformat() if app_user.updated_at else None,
        }
    )
