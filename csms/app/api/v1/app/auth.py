#
# App 用户认证 API
# 提供注册、登录、登出、刷新token等功能
#

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from app.database.base import get_db
from app.database.models import AppUser, ChargingSession, AppUserPaymentMethod
from app.core.auth import get_current_user, verify_password
from app.services.token_service import (
    create_token_pair,
    save_refresh_token,
    refresh_token_pair,
    revoke_refresh_token,
    revoke_all_user_tokens,
)
from app.services.email_verification_service import (
    can_resend,
    issue_email_verification,
    verify_by_code,
    verify_by_token,
)
from app.services.password_reset_service import (
    can_request_password_reset,
    consume_password_reset_token,
    issue_password_reset,
)
from datetime import datetime, timezone
import secrets
from app.core.logging_config import get_logger
from app.core.api_logging import log_api_request, log_api_response, log_api_error, log_business_operation

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

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


class DeleteAccountRequest(BaseModel):
    confirm: bool = Field(..., description="Must be true to permanently delete the account")


class ResendVerificationRequest(BaseModel):
    email: str


class VerifyEmailCodeRequest(BaseModel):
    email: str
    code: str = Field(..., min_length=4, max_length=8)


class PasswordResetRequest(BaseModel):
    email: str


class ConfirmPasswordResetRequest(BaseModel):
    token: str = Field(..., min_length=16)
    new_password: str = Field(..., min_length=8, max_length=128)


async def _login_response_for_user(app_user: AppUser, request: Request, db: Session) -> LoginResponse:
    """验证通过后签发 token（与 login-email 一致）。"""
    access_token, refresh_token = await create_token_pair(
        user_id=app_user.id,
        user_type="app_user",
        audience="app",
        is_super_admin=False,
        request=request,
    )
    from jose import jwt
    from app.core.config import get_settings

    settings = get_settings()
    unverified_payload = jwt.decode(
        refresh_token,
        settings.secret_key,
        algorithms=[settings.algorithm],
        options={"verify_signature": False, "verify_aud": False},
    )
    await save_refresh_token(
        jti=unverified_payload.get("jti"),
        user_id=app_user.id,
        user_type="app_user",
        refresh_token=refresh_token,
        expires_at=datetime.fromtimestamp(unverified_payload.get("exp"), tz=timezone.utc),
        db=db,
        request=request,
    )
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": str(app_user.id),
            "phone": app_user.phone,
            "email": app_user.email,
            "full_name": app_user.full_name,
            "balance": float(app_user.balance or 0),
            "email_verified": True,
            "status": app_user.status,
        },
    )


# ==================== 认证端点 ====================

@router.post("/refresh", response_model=RefreshTokenResponse, summary="刷新token")
async def refresh(
    request_data: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """刷新 access token 和 refresh token"""
    try:
        log_api_request(
            method="POST",
            path="/api/v1/app/auth/refresh",
            operation="refresh_token",
            request=request,
            params={"refresh_token": f"{request_data.refresh_token[:10]}..."}
        )
        
        new_access_token, new_refresh_token = await refresh_token_pair(
            refresh_token=request_data.refresh_token,
            request=request,
            db=db
        )
        
        log_api_response(
            method="POST",
            path="/api/v1/app/auth/refresh",
            operation="refresh_token",
            result="success",
            request=request
        )
        
        return RefreshTokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token
        )
    except Exception as e:
        log_api_error(
            method="POST",
            path="/api/v1/app/auth/refresh",
            operation="refresh_token",
            error=e,
            request=request,
            params={"refresh_token": f"{request_data.refresh_token[:10]}..."}
        )
        raise


@router.post("/logout", summary="登出")
async def logout(
    request_data: RefreshTokenRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """登出（撤销 refresh token）"""
    try:
        from app.services.token_service import revoke_refresh_token
        
        log_api_request(
            method="POST",
            path="/api/v1/app/auth/logout",
            operation="logout",
            current_user=current_user,
            request=request,
            params={"refresh_token": f"{request_data.refresh_token[:10]}..."}
        )
        
        # 撤销refresh_token
        await revoke_refresh_token(request_data.refresh_token, request, db)
        
        user_id = current_user.get("user_id") if current_user else None
        log_business_operation(
            operation="登出",
            entity_type="user",
            entity_id=user_id,
            result="success",
            current_user=current_user,
            request=request
        )
        
        log_api_response(
            method="POST",
            path="/api/v1/app/auth/logout",
            operation="logout",
            result="success",
            current_user=current_user,
            request=request
        )
        
        return {"message": "Logged out successfully"}
    except Exception as e:
        log_api_error(
            method="POST",
            path="/api/v1/app/auth/logout",
            operation="logout",
            error=e,
            current_user=current_user,
            request=request,
            params={"refresh_token": f"{request_data.refresh_token[:10]}..."}
        )
        raise


@router.get("/me", summary="获取当前用户信息")
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前平台终端用户信息（AppUser）"""
    try:
        log_api_request(
            method="GET",
            path="/api/v1/app/auth/me",
            operation="get_current_user_info",
            current_user=current_user
        )
        
        user_id = UUID(current_user["user_id"])

        app_user = db.query(AppUser).filter(AppUser.id == user_id).first()
        if not app_user:
            log_api_error(
                method="GET",
                path="/api/v1/app/auth/me",
                operation="get_current_user_info",
                error=HTTPException(status_code=404, detail="User not found"),
                current_user=current_user
            )
            raise HTTPException(status_code=404, detail="User not found")
        
        log_api_response(
            method="GET",
            path="/api/v1/app/auth/me",
            operation="get_current_user_info",
            result="success",
            current_user=current_user,
            details={"user_id": str(app_user.id), "email": app_user.email}
        )
        
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
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="GET",
            path="/api/v1/app/auth/me",
            operation="get_current_user_info",
            error=e,
            current_user=current_user
        )
        raise


@router.delete("/me", summary="删除当前账户（Apple Guideline 5.1.1(v)）")
async def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """软删除 App 账户：撤销令牌、匿名化 PII。进行中的充电会话须先结束。"""
    if not body.confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="confirm must be true")

    try:
        user_id = UUID(current_user["user_id"])
        log_api_request(
            method="DELETE",
            path="/api/v1/app/auth/me",
            operation="delete_account",
            current_user=current_user,
            request=request,
        )

        app_user = db.query(AppUser).filter(AppUser.id == user_id).first()
        if not app_user:
            raise HTTPException(status_code=404, detail="User not found")
        if app_user.status == "deleted":
            raise HTTPException(status_code=410, detail="Account already deleted")

        ongoing = (
            db.query(ChargingSession)
            .filter(
                ChargingSession.user_id == str(user_id),
                ChargingSession.status == "ongoing",
            )
            .first()
        )
        if ongoing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete account while a charging session is active. Stop charging first.",
            )

        await revoke_all_user_tokens(user_id, "app_user", db)

        db.query(AppUserPaymentMethod).filter(AppUserPaymentMethod.app_user_id == user_id).delete()

        deleted_email = f"deleted_{user_id.hex[:16]}@deleted.eslatin.local"
        app_user.email = deleted_email
        app_user.phone = None
        app_user.full_name = None
        app_user.password_hash = secrets.token_hex(32)
        app_user.status = "deleted"
        app_user.updated_at = datetime.now(timezone.utc)
        db.commit()

        log_business_operation(
            operation="删除账户",
            entity_type="user",
            entity_id=str(user_id),
            result="success",
            current_user=current_user,
            request=request,
        )
        log_api_response(
            method="DELETE",
            path="/api/v1/app/auth/me",
            operation="delete_account",
            result="success",
            current_user=current_user,
            request=request,
        )

        return {"success": True, "message": "Account deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="DELETE",
            path="/api/v1/app/auth/me",
            operation="delete_account",
            error=e,
            current_user=current_user,
            request=request,
        )
        raise


# ==================== 邮箱认证端点 ====================

@router.post("/register-email", summary="邮箱注册")
async def register_with_email(
    request_data: EmailRegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """使用邮箱和密码注册（平台用户 AppUser）"""
    try:
        from app.core.auth import get_password_hash
        
        log_api_request(
            method="POST",
            path="/api/v1/app/auth/register-email",
            operation="register_email",
            request=request,
            params={"email": request_data.email, "phone": request_data.phone, "full_name": request_data.full_name}
        )
        
        email = (request_data.email or "").strip().lower()
        # 检查邮箱是否已被注册
        existing_user = db.query(AppUser).filter(AppUser.email == email).first()
        
        if existing_user:
            logger.warning(f"Email already registered: {email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        if request_data.phone:
            existing_phone = db.query(AppUser).filter(AppUser.phone == request_data.phone).first()
            if existing_phone:
                logger.warning(f"Phone already registered: {request_data.phone}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone already registered")

        # 创建新平台用户
        new_user = AppUser(
            email=email,
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

        # 发送验证码邮件（未配 SMTP 时验证码会写入服务日志）
        issue_email_verification(db, new_user)
        
        log_business_operation(
            operation="邮箱注册",
            entity_type="user",
            entity_id=str(new_user.id),
            result="success",
            request=request,
            details={"email": new_user.email}
        )
        
        log_api_response(
            method="POST",
            path="/api/v1/app/auth/register-email",
            operation="register_email",
            result="success",
            request=request,
            details={"user_id": str(new_user.id), "email": new_user.email}
        )
        
        return {
            "success": True,
            "message": "User registered successfully. Please verify your email.",
            "user_id": str(new_user.id),
            "email_verification_required": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="POST",
            path="/api/v1/app/auth/register-email",
            operation="register_email",
            error=e,
            request=request,
            params={"email": request_data.email}
        )
        raise


@router.post("/login-email", response_model=LoginResponse, summary="邮箱登录")
async def login_with_email(
    request_data: EmailLoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """使用邮箱和密码登录（平台用户 AppUser）"""
    try:
        log_api_request(
            method="POST",
            path="/api/v1/app/auth/login-email",
            operation="login_email",
            request=request,
            params={"email": request_data.email, "remember_me": request_data.remember_me}
        )
        
        email = (request_data.email or "").strip().lower()
        logger.info(f"Login attempt for email: {email}")

        app_user = db.query(AppUser).filter(AppUser.email == email).first()
        if not app_user:
            logger.warning(f"User not found: {email}")
            log_api_error(
                method="POST",
                path="/api/v1/app/auth/login-email",
                operation="login_email",
                error=HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"),
                request=request,
                params={"email": email}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        logger.info("User found: %s, credential hash configured=%s", app_user.email, bool(app_user.password_hash))
        
        # 验证密码
        if not app_user.password_hash:
            logger.warning("Credential hash is empty")
            log_api_error(
                method="POST",
                path="/api/v1/app/auth/login-email",
                operation="login_email",
                error=HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"),
                request=request,
                params={"email": request_data.email}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        credentials_valid = verify_password(request_data.password, app_user.password_hash)
        logger.info("Credential verification result: %s", credentials_valid)
        
        if not credentials_valid:
            logger.warning("Credential verification failed")
            log_api_error(
                method="POST",
                path="/api/v1/app/auth/login-email",
                operation="login_email",
                error=HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"),
                request=request,
                params={"email": request_data.email}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        if app_user.status != "active":
            log_api_error(
                method="POST",
                path="/api/v1/app/auth/login-email",
                operation="login_email",
                error=HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active"),
                request=request,
                params={"email": request_data.email, "user_id": str(app_user.id)}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is not active"
            )

        if not app_user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified"
            )
        
        # 更新最后登录时间
        app_user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        
        # 生成 token pair
        access_token, refresh_token = await create_token_pair(
            user_id=app_user.id,
            user_type="app_user",
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
            user_type="app_user",
            refresh_token=refresh_token,
            expires_at=refresh_expires_at,
            db=db,
            request=request
        )
        
        log_business_operation(
            operation="邮箱登录",
            entity_type="user",
            entity_id=str(app_user.id),
            result="success",
            request=request,
            details={"email": app_user.email}
        )
        
        log_api_response(
            method="POST",
            path="/api/v1/app/auth/login-email",
            operation="login_email",
            result="success",
            request=request,
            details={"user_id": str(app_user.id), "email": app_user.email}
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
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="POST",
            path="/api/v1/app/auth/login-email",
            operation="login_email",
            error=e,
            request=request,
            params={"email": request_data.email}
        )
        raise


@router.post("/resend-verification", summary="重发邮箱验证码")
async def resend_verification(
    request_data: ResendVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = (request_data.email or "").strip().lower()
    log_api_request(
        method="POST",
        path="/api/v1/app/auth/resend-verification",
        operation="resend_verification",
        request=request,
        params={"email": email},
    )
    user = db.query(AppUser).filter(AppUser.email == email).first()
    # 防枚举：无用户时也返回成功文案
    if not user:
        return {"success": True, "message": "If the email exists, a verification code was sent."}
    if user.email_verified:
        return {"success": True, "message": "Email already verified."}

    allowed, wait_s = can_resend(user)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {wait_s} seconds before resending",
        )

    issue_email_verification(db, user)
    return {"success": True, "message": "Verification email sent."}


@router.post("/reset-password", summary="发送密码重置邮件")
async def request_password_reset(
    request_data: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = (request_data.email or "").strip().lower()
    user = db.query(AppUser).filter(AppUser.email == email).first()
    # 无论用户是否存在都返回相同结果，避免邮箱枚举。
    if not user:
        return {"success": True, "message": "If the email exists, a reset link was sent."}

    allowed, wait_s = can_request_password_reset(user)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {wait_s} seconds before requesting another reset link",
        )

    issue_password_reset(db, user)
    return {"success": True, "message": "If the email exists, a reset link was sent."}


@router.post("/confirm-reset-password", summary="确认密码重置")
async def confirm_password_reset(
    request_data: ConfirmPasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    from app.core.auth import get_password_hash

    user = consume_password_reset_token(
        db=db,
        token=request_data.token,
        new_password_hash=get_password_hash(request_data.new_password),
    )
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")

    # 密码变更后撤销旧 refresh token，避免旧登录会话继续有效。
    await revoke_all_user_tokens(user.id, "app_user", db)
    return {"success": True, "message": "Password reset successfully."}


@router.post("/verify-email", response_model=LoginResponse, summary="用验证码验证邮箱并登录")
async def verify_email_with_code(
    request_data: VerifyEmailCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = (request_data.email or "").strip().lower()
    code = (request_data.code or "").strip()
    log_api_request(
        method="POST",
        path="/api/v1/app/auth/verify-email",
        operation="verify_email_code",
        request=request,
        params={"email": email},
    )
    user = verify_by_code(db, email, code)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    resp = await _login_response_for_user(user, request, db)
    log_business_operation(
        operation="邮箱验证码验证",
        entity_type="user",
        entity_id=str(user.id),
        result="success",
        request=request,
        details={"email": user.email},
    )
    return resp


@router.get("/verify-email", summary="邮件链接验证邮箱", response_class=HTMLResponse)
async def verify_email_with_token(
    token: str,
    db: Session = Depends(get_db),
):
    user = verify_by_token(db, token)
    if not user:
        return HTMLResponse(
            status_code=400,
            content="""<!DOCTYPE html><html><head><meta charset="utf-8"><title>EsLatin</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px">
<h1>Link inválido o expirado</h1>
<p>Invalid or expired verification link. Open the app and request a new code.</p>
</body></html>""",
        )
    return HTMLResponse(
        content=f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>EsLatin</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px">
<h1>✓ Correo verificado</h1>
<p>{user.email}</p>
<p>Email verified. You can return to the EsLatin app and sign in.</p>
<p><a href="eslatin://EmailLogin">Open EsLatin</a></p>
</body></html>"""
    )
