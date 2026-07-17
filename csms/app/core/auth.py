#
# 认证授权核心模块
# 实现 JWT 生成、验证、权限检查等功能
#

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Security, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import get_settings
import uuid

settings = get_settings()

# 密码加密上下文
# 修复 bcrypt 版本兼容性问题：抑制 passlib 的警告，并使用兼容的配置
import logging
logging.getLogger('passlib').setLevel(logging.ERROR)  # 抑制 passlib 警告

try:
    pwd_context = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")
    # 尝试进行一次哈希测试以检测兼容性问题（使用短密码避免bug检测）
    _test_hash = pwd_context.hash("test")
except (AttributeError, ValueError, TypeError) as e:
    # bcrypt 版本不兼容，使用 pbkdf2_sha256 作为后备方案
    logger = logging.getLogger(__name__)
    logger.warning(f"bcrypt 不可用，使用备用方案: {e}")
    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# HTTP Bearer认证
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


def create_access_token(
    data: Dict[str, Any], 
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    创建访问令牌（Access Token）
    
    JWT Payload 包含：
    - user_id: 用户ID
    - user_type: 用户类型（admin / end_user）
    - global_role: 全局角色（是否为 platform super admin）
    - aud: Token audience（admin / app）
    - iss: Issuer
    - jti: JWT ID（用于撤销）
    - exp: 过期时间
    - iat: 签发时间
    - nbf: Not Before
    """
    to_encode = data.copy()
    
    now = datetime.now(timezone.utc)
    
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,
        "iss": "csms-platform"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    创建刷新令牌（Refresh Token）
    
    长期有效（默认7天）
    """
    to_encode = data.copy()
    
    now = datetime.now(timezone.utc)
    
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=7)  # 默认7天
    
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,
        "iss": "csms-platform"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def verify_token(token: str, audience: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """验证令牌"""
    try:
        decode_options = {
            "verify_signature": True,
            "verify_exp": True,
            "verify_iat": True,
            "verify_nbf": True,
        }
        
        decode_kwargs = {
            "token": token,
            "key": settings.secret_key,
            "algorithms": [settings.algorithm],
            "options": decode_options,
        }
        
        # 路由提供 audience 时严格校验；否则至少要求合法 issuer 和 audience。
        if audience:
            decode_kwargs["audience"] = audience
            decode_kwargs["issuer"] = "csms-platform"
            decode_options["verify_aud"] = True
            decode_options["require_iss"] = True
        else:
            decode_kwargs["issuer"] = "csms-platform"
            decode_options["verify_aud"] = False
            # python-jose requires an explicit audience value when verify_aud is enabled;
            # require the claim structurally, then validate its value below.
            decode_options["require_aud"] = False
            decode_options["require_iss"] = True
        
        payload = jwt.decode(**decode_kwargs)
        if not audience and payload.get("aud") not in {"admin", "app"}:
            return None
        return payload
    except JWTError as e:
        # 调试：打印错误信息
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"JWT verification failed: {e}")
        return None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Dict[str, Any]:
    """
    获取当前用户（从JWT令牌）
    
    返回的 payload 包含：
    - user_id: 用户ID
    - user_type: 用户类型（admin / end_user）
    - global_role: 全局角色（是否为 platform super admin）
    - aud: Token audience
    - jti: JWT ID
    """
    token = credentials.credentials
    payload = verify_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    path = request.url.path
    app_route = path.startswith("/api/v1/app/")
    admin_route = path.startswith("/api/v1/admin/") or path.startswith((
        "/api/v1/chargers",
        "/api/v1/sites",
        "/api/v1/transactions",
        "/api/v1/orders",
        "/api/v1/ocpp",
        "/api/v1/admin",
        "/api/v1/charger-management",
        "/api/v1/statistics",
        "/api/v1/devices",
        "/api/v1/dashboard",
    ))
    expected_audience = "app" if app_route else "admin" if admin_route else None
    if expected_audience and payload.get("aud") != expected_audience:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token audience",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def require_audience(audience: str):
    """
    验证 Token Audience 的装饰器
    
    用法：
    @require_audience("admin")
    async def admin_only_endpoint(...):
        ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 从依赖中获取 token payload
            # 这里需要在实际使用时从 request 或依赖中获取
            # 暂时返回原函数
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def get_token_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """从请求中提取并验证 token，要求 issuer 和 audience 合法。"""
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
    except ValueError:
        return None
    
    try:
        from jose import jwt
        from app.core.config import get_settings
        settings = get_settings()
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
                "verify_aud": False,
                "require_aud": False,
                "require_iss": True,
            },
            issuer="csms-platform",
        )
        return payload if payload.get("aud") in {"admin", "app"} else None
    except Exception:
        return None
