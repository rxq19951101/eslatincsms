#
# 租户中间件
# 负责从请求中提取 tenant_id，验证 membership，设置数据库上下文
#

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
import uuid
from types import SimpleNamespace
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database.base import (
    tenant_id_context, 
    is_super_admin_context, 
    use_super_connection_context,
    SessionLocal
)
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")
from app.database.models import TenantMembership, AppUser


def get_tenant_id_from_request(request: Request, current_user=None) -> Optional[uuid.UUID]:
    """
    从请求中提取 tenant_id（优先级顺序）
    
    优先级：
    1. X-Tenant-Id header（运营后台、App）
    2. 子域名 tenant.domain.com（可选）
    3. 管理员默认租户（AppUser 不绑定单一租户，必须显式提供租户上下文）
    """
    # 1. 从 X-Tenant-Id header（优先级最高）
    # FastAPI/Starlette 的 headers.get 是大小写不敏感的，但为了明确性，先尝试精确匹配，再尝试小写
    tenant_id_header = request.headers.get("X-Tenant-Id") or request.headers.get("x-tenant-id")
    
    if tenant_id_header:
        try:
            parsed_uuid = uuid.UUID(tenant_id_header)
            return parsed_uuid
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail="Invalid X-Tenant-Id format"
            )
    
    # 2. 从子域名（可选实现）
    # host = request.headers.get("host", "")
    # tenant_domain = extract_tenant_from_subdomain(host)
    # if tenant_domain:
    #     return get_tenant_id_by_domain(tenant_domain)
    
    # 3. 从用户默认租户（仅限管理员，且必须存在 membership）
    if current_user and current_user.user_type == "admin":
        try:
            default_tenant_id = get_user_default_tenant(current_user.id)
            if default_tenant_id:
                logger.debug(f"Resolved tenant_id from user default tenant: {default_tenant_id} for user {current_user.id}")
                return default_tenant_id
        except Exception as e:
            logger.warning(f"Failed to get user default tenant for {current_user.id}: {e}", exc_info=True)
    
    # 未找到租户
    return None


def get_user_default_tenant(admin_user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """获取用户的默认租户（is_primary = TRUE）"""
    # 使用 SuperSessionLocal 绕过 RLS（因为这是查询用户-租户关系，不涉及业务数据）
    from app.database.base import SuperSessionLocal
    db = SuperSessionLocal()
    try:
        membership = db.query(TenantMembership).filter(
            TenantMembership.admin_user_id == admin_user_id,
            TenantMembership.is_primary == True,
            TenantMembership.status == "active"
        ).first()

        if membership:
            return membership.tenant_id
        return None
    finally:
        db.close()


def validate_tenant_membership(user_id: uuid.UUID, tenant_id: uuid.UUID, is_super_admin: bool, db: Session) -> bool:
    """验证用户是否属于该租户"""
    if is_super_admin:
        return True  # 超级管理员可以访问任何租户
    
    # 查询 tenant_memberships 表
    membership = db.query(TenantMembership).filter(
        TenantMembership.admin_user_id == user_id,
        TenantMembership.tenant_id == tenant_id,
        TenantMembership.status == "active"
    ).first()
    
    return membership is not None


def should_use_super_connection(current_user, tenant_id_header) -> bool:
    """
    判断是否应该使用 super 连接
    
    条件：
    - 必须是 super admin
    
    说明：
    - 超级管理员可以选择携带或不携带 X-Tenant-Id
    - 携带 X-Tenant-Id：查询指定租户的数据
    - 不携带 X-Tenant-Id：查询所有租户的数据（聚合）
    """
    # 必须是 super admin
    if not current_user or not getattr(current_user, 'is_super_admin', False):
        return False
    
    # 超级管理员始终使用 super 连接（绕过 RLS）
    # 无论是否携带 X-Tenant-Id
    return True


def load_authenticated_user(token_payload):
    """从数据库确认 token 对应用户，禁止 JWT claims 直接授予平台权限。"""
    try:
        user_id = uuid.UUID(str(token_payload["user_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authenticated user") from exc

    user_type = token_payload.get("user_type")
    audience = token_payload.get("aud")
    if user_type == "admin" and audience != "admin":
        raise HTTPException(status_code=401, detail="Invalid admin token audience")
    if user_type == "app_user" and audience != "app":
        raise HTTPException(status_code=401, detail="Invalid app token audience")

    if user_type == "admin":
        from app.database.models import AdminUser
        from app.database.base import SuperSessionLocal
        db = SuperSessionLocal()
        try:
            user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="User account is inactive or not found")
            return SimpleNamespace(
                id=user.id,
                user_type="admin",
                is_super_admin=bool(user.is_super_admin),
            )
        finally:
            db.close()

    if user_type == "app_user":
        from app.database.base import SessionLocal
        db = SessionLocal()
        try:
            user = db.query(AppUser).filter(AppUser.id == user_id).first()
            if not user or user.status != "active":
                raise HTTPException(status_code=401, detail="User account is inactive or not found")
            return SimpleNamespace(
                id=user.id,
                user_type="app_user",
                is_super_admin=False,
            )
        finally:
            db.close()

    raise HTTPException(status_code=401, detail="Unsupported token user type")


def expected_audience_for_path(path: str) -> Optional[str]:
    if path.startswith("/api/v1/admin/"):
        return "admin"
    if path.startswith("/api/v1/app/"):
        return "app"
    return None


def is_public_auth_path(path: str) -> bool:
    """公开认证接口白名单；其余 /api/v1 请求必须先通过身份认证。"""
    public_paths = (
        "/api/v1/admin/auth/login",
        "/api/v1/admin/auth/refresh",
        "/api/v1/app/auth/refresh",
        "/api/v1/app/auth/register-email",
        "/api/v1/app/auth/login-email",
        "/api/v1/app/auth/resend-verification",
        "/api/v1/app/auth/verify-email",
        "/api/v1/app/auth/reset-password",
        "/api/v1/app/auth/confirm-reset-password",
    )
    return path.startswith(public_paths)


async def tenant_middleware(request: Request, call_next):
    """
    租户中间件 - 在请求处理前验证 tenant_id
    
    功能：
    1. 从请求中提取 tenant_id
    2. 验证用户是否属于该租户（如果不是 super admin）
    3. 设置上下文变量（tenant_id, is_super_admin, use_super_connection）
    4. 在请求结束后清理上下文
    """
    # 健康检查和文档公开；认证接口由 is_public_auth_path 明确白名单。
    skip_paths = ("/health", "/docs", "/redoc", "/openapi.json")
    if any(request.url.path.startswith(path) for path in skip_paths):
        return await call_next(request)
    
    # 从 request.state 获取当前用户（由认证中间件设置）
    current_user = getattr(request.state, 'current_user', None)
    
    # 如果不存在，兜底从 Authorization Bearer 解析一次，避免中间件顺序导致的空值。
    if current_user is None:
        try:
            from app.core.auth import get_token_from_request
            token_payload = get_token_from_request(request)
            if token_payload:
                expected_audience = expected_audience_for_path(request.url.path)
                if expected_audience and token_payload.get("aud") != expected_audience:
                    raise HTTPException(status_code=401, detail="Invalid token audience")
                current_user = load_authenticated_user(token_payload)
                request.state.current_user = current_user
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"success": False, "error": {"code": "AUTHENTICATION_ERROR", "message": exc.detail, "details": [], "status_code": exc.status_code}},
                headers=exc.headers,
            )
        except Exception:
            if request.headers.get("Authorization"):
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "error": {"code": "AUTHENTICATION_ERROR", "message": "Invalid authentication token", "details": [], "status_code": 401}},
                )
            logger.debug("No authenticated user in tenant middleware")
    
    # 所有 API v1 路由默认要求认证，只有显式白名单的认证接口公开。
    if not current_user:
        if request.url.path.startswith("/api/v1") and not is_public_auth_path(request.url.path):
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": {"code": "AUTHENTICATION_ERROR", "message": "Authentication required", "details": [], "status_code": 401}},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)
    
    # 提取 tenant_id（简化中间件日志，详细日志在路由层面）
    tenant_id_header = request.headers.get("X-Tenant-Id") or request.headers.get("x-tenant-id")
    
    try:
        tenant_id = get_tenant_id_from_request(request, current_user)
    except Exception as e:
        logger.error("Unable to resolve tenant context", exc_info=True)
        tenant_id = None
    
    # 如果还没有 tenant_id，且用户不是 super_admin，尝试从用户的默认租户获取
    if not tenant_id and current_user and current_user.user_type == "admin" and not current_user.is_super_admin:
        try:
            default_tenant_id = get_user_default_tenant(current_user.id)
            if default_tenant_id:
                tenant_id = default_tenant_id
        except Exception as e:
            logger.error("Failed to resolve user's default tenant", exc_info=True)
    
    # 硬规则：任何非 super admin 的已认证业务请求都必须解析出 tenant_id。
    if current_user and not current_user.is_super_admin and not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="TENANT_REQUIRED: Tenant context could not be resolved for this request."
        )
    
    # 判断是否使用 super 连接
    use_super_connection = should_use_super_connection(current_user, tenant_id_header)
    
    # 验证租户归属（如果不是 super admin）
    if tenant_id and current_user and not current_user.is_super_admin:
        # 说明：
        # - admin：校验 tenant_memberships（使用 super session，避免 RLS 影响）
        # - app_user：平台级账户不绑定单一租户，租户上下文由请求明确指定。
        user_type = getattr(current_user, "user_type", "admin")

        if user_type == "admin":
            from app.database.base import SuperSessionLocal
            db = SuperSessionLocal()
            try:
                # 清理可能复用到的异常事务状态（避免 InFailedSqlTransaction）
                try:
                    db.rollback()
                except Exception:
                    pass

                if not validate_tenant_membership(current_user.id, tenant_id, False, db):
                    raise HTTPException(
                        status_code=403,
                        detail="TENANT_ACCESS_DENIED: User does not belong to the specified tenant"
                    )
            except SQLAlchemyError:
                try:
                    db.rollback()
                except Exception:
                    pass
                raise
            finally:
                db.close()


        else:
            raise HTTPException(
                status_code=403,
                detail="TENANT_ACCESS_DENIED: Unsupported user type"
            )
    
    # 设置上下文变量
    tenant_id_context.set(tenant_id)
    is_super_admin_context.set(
        current_user.is_super_admin if current_user else False
    )
    use_super_connection_context.set(use_super_connection)
    
    # 如果使用 super 连接，记录审计日志（强制）
    if use_super_connection and current_user:
        # 记录审计日志（强制）
        try:
            from app.database.models import AuditLog
            audit_log = AuditLog(
                tenant_id=tenant_id,
                actor_id=current_user.id,
                actor_type="admin",
                action="super_admin_cross_tenant_access",
                resource_type="tenant",
                resource_id=str(tenant_id) if tenant_id else None,
                audit_metadata={
                    "used_super_connection": True,
                    "request_path": str(request.url),
                    "request_method": request.method
                },
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent")
            )
            db = SessionLocal()
            try:
                db.add(audit_log)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to log super admin access: {e}", exc_info=True)
    
    try:
        response = await call_next(request)
        return response
    finally:
        # 清理上下文（确保不会泄漏到下一个请求）
        tenant_id_context.set(None)
        is_super_admin_context.set(False)
        use_super_connection_context.set(False)
