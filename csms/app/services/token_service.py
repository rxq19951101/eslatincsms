#
# Token 服务
# 管理 Refresh Token 的创建、验证、撤销等
#

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import uuid
import hashlib
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from app.database.models import RefreshToken
from app.core.auth import create_access_token, create_refresh_token, verify_token
from app.core.config import get_settings
import secrets
from jose import jwt

settings = get_settings()


def hash_token(token: str) -> str:
    """对 token 进行哈希（用于存储）"""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token_hash(token: str, token_hash: str) -> bool:
    """验证 token 哈希"""
    return hash_token(token) == token_hash


def generate_jti() -> str:
    """生成 JWT ID"""
    return secrets.token_urlsafe(32)


async def create_token_pair(
    user_id: uuid.UUID,
    user_type: str,
    audience: str,
    is_super_admin: bool = False,
    request: Optional[Request] = None
) -> Tuple[str, str]:
    """
    创建 token pair（Access Token + Refresh Token）
    
    Returns:
        (access_token, refresh_token)
    """
    jti = generate_jti()
    
    # 创建 Access Token
    access_token_data = {
        "user_id": str(user_id),
        "user_type": user_type,
        "global_role": "super_admin" if is_super_admin else None,
        "aud": audience,
        "jti": jti
    }
    access_token = create_access_token(access_token_data)
    
    # 创建 Refresh Token
    refresh_jti = generate_jti()
    refresh_token_data = {
        "user_id": str(user_id),
        "user_type": user_type,
        "aud": audience,
        "jti": refresh_jti
    }
    refresh_token = create_refresh_token(refresh_token_data)
    
    return access_token, refresh_token


async def save_refresh_token(
    jti: str,
    user_id: uuid.UUID,
    user_type: str,
    refresh_token: str,
    expires_at: datetime,
    db: Session,
    request: Optional[Request] = None
) -> RefreshToken:
    """保存 Refresh Token 到数据库"""
    token_record = RefreshToken(
        jti=jti,
        user_id=user_id,
        user_type=user_type,
        token_hash=hash_token(refresh_token),
        expires_at=expires_at,
        ip_address=request.client.host if request else None,
        device_info=get_device_info(request) if request else None
    )
    db.add(token_record)
    db.commit()
    db.refresh(token_record)
    return token_record


def get_device_info(request: Request) -> dict:
    """获取设备信息"""
    return {
        "user_agent": request.headers.get("user-agent"),
        "ip_address": request.client.host if request.client else None
    }


async def refresh_token_pair(
    refresh_token: str,
    request: Request,
    db: Session
) -> Tuple[str, str]:
    """
    刷新 token pair（带 rotation 和 reuse detection）
    
    Returns:
        (new_access_token, new_refresh_token)
    """
    # 1. 解析并验证 refresh token（需要 audience）
    # 从 token 中先解析获取 audience，然后验证
    try:
        from app.core.auth import verify_token
        from jose import jwt
        from app.core.config import get_settings
        settings = get_settings()
        
        # 先不验证 audience 来获取 payload 中的 audience
        unverified_payload = jwt.decode(
            refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            # 仅用于读取 payload；不要触发 aud 校验（jose 在 verify_aud=True 时会要求传 audience 参数）
            options={"verify_signature": False, "verify_aud": False}
        )
        token_audience = unverified_payload.get("aud")
        
        # 使用正确的 audience 验证 token
        payload = verify_token(refresh_token, audience=token_audience)
    except Exception:
        payload = None
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    jti = payload.get("jti")
    if not jti:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # 2. 查询数据库
    token_record = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    
    if not token_record:
        # Token 不存在 - 可能是伪造的
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # 3. 检查是否已撤销
    if token_record.revoked_at:
        # 检测到重用！撤销该用户所有 token
        await revoke_all_user_tokens(token_record.user_id, token_record.user_type, db)
        
        # 记录安全事件（需要审计日志服务）
        # await audit_log_service.log(...)
        
        raise HTTPException(
            status_code=401,
            detail="Refresh token has been revoked. Please login again."
        )
    
    # 4. 检查是否过期
    if token_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")
    
    # 5. 验证 token 哈希
    if not verify_token_hash(refresh_token, token_record.token_hash):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # 6. 撤销旧 token（Rotation）
    token_record.revoked_at = datetime.now(timezone.utc)
    db.commit()
    
    # 7. 生成新 token pair
    user_id = token_record.user_id
    user_type = token_record.user_type
    audience = payload.get("aud", "admin")
    
    # 从数据库查询用户信息以获取 is_super_admin
    is_super_admin = False
    if user_type == "admin":
        from app.database.models import AdminUser
        admin_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
        if admin_user:
            is_super_admin = admin_user.is_super_admin
    
    new_access_token, new_refresh_token = await create_token_pair(
        user_id=user_id,
        user_type=user_type,
        audience=audience,
        is_super_admin=is_super_admin,
        request=request
    )
    
    # 8. 存储新 refresh token
    # 从新 token 中获取 audience 来验证
    try:
        from jose import jwt
        from app.core.config import get_settings
        settings = get_settings()
        unverified_payload = jwt.decode(
            new_refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_signature": False, "verify_aud": False}
        )
        new_token_audience = unverified_payload.get("aud")
        new_payload = verify_token(new_refresh_token, audience=new_token_audience)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to verify new refresh token")
    
    if not new_payload:
        raise HTTPException(status_code=500, detail="Failed to parse new refresh token")
    
    new_jti = new_payload.get("jti")
    new_expires_at = datetime.fromtimestamp(new_payload.get("exp"), tz=timezone.utc)
    
    await save_refresh_token(
        jti=new_jti,
        user_id=user_id,
        user_type=user_type,
        refresh_token=new_refresh_token,
        expires_at=new_expires_at,
        db=db,
        request=request
    )
    
    return new_access_token, new_refresh_token


async def revoke_all_user_tokens(
    user_id: uuid.UUID,
    user_type: str,
    db: Session
):
    """撤销用户所有 refresh token（强制重新登录）"""
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.user_type == user_type,
        RefreshToken.revoked_at.is_(None)
    ).update({"revoked_at": datetime.now(timezone.utc)})
    db.commit()


async def revoke_refresh_token(
    refresh_token: str,
    request: Request,
    db: Session
):
    """撤销指定的 refresh token"""
    # 从token中提取jti和audience
    try:
        settings = get_settings()
        unverified_payload = jwt.decode(
            refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_signature": False}
        )
        token_audience = unverified_payload.get("aud")
        payload = verify_token(refresh_token, audience=token_audience)
    except Exception:
        payload = None
    
    if not payload:
        return
    
    jti = payload.get("jti")
    if not jti:
        return
    
    token_record = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if token_record:
        token_record.revoked_at = datetime.now(timezone.utc)
        db.commit()
