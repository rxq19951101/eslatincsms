#
# 租户中间件
# 负责从请求中提取 tenant_id，验证 membership，设置数据库上下文
#

from fastapi import Request, HTTPException
from typing import Optional
import uuid
from sqlalchemy.orm import Session
from app.database.base import (
    tenant_id_context, 
    is_super_admin_context, 
    use_super_connection_context,
    SessionLocal
)
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")
from app.database.models import TenantMembership, EndUser


def get_tenant_id_from_request(request: Request, current_user=None) -> Optional[uuid.UUID]:
    """
    从请求中提取 tenant_id（优先级顺序）
    
    优先级：
    1. X-Tenant-Id header（运营后台、App）
    2. 子域名 tenant.domain.com（可选）
    3. 用户默认租户（EndUser 只属于一个租户时，或 AdminUser 的 is_primary 租户）
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
    
    # 4. EndUser 场景：从用户所属租户（EndUser 只属于一个租户）
    if current_user and current_user.user_type == "end_user":
        return get_end_user_tenant(current_user.id)
    
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


def get_end_user_tenant(end_user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """获取终端用户所属的租户（EndUser 只属于一个租户）"""
    db = SessionLocal()
    try:
        end_user = db.query(EndUser).filter(EndUser.id == end_user_id).first()
        if end_user:
            return end_user.tenant_id
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


async def tenant_middleware(request: Request, call_next):
    """
    租户中间件 - 在请求处理前验证 tenant_id
    
    功能：
    1. 从请求中提取 tenant_id
    2. 验证用户是否属于该租户（如果不是 super admin）
    3. 设置上下文变量（tenant_id, is_super_admin, use_super_connection）
    4. 在请求结束后清理上下文
    """
    # 跳过非业务路径和认证相关路径（如 /health, /docs, /auth/login, /auth/refresh 等）
    # /me 接口也应该跳过租户检查，因为它用于获取用户自己的信息（包括 tenant_id）
    skip_paths = (
        "/health", "/docs", "/redoc", "/openapi.json",
        "/api/v1/admin/auth/login", "/api/v1/admin/auth/refresh", "/api/v1/admin/auth/me"
    )
    if any(request.url.path.startswith(path) for path in skip_paths):
        return await call_next(request)
    
    # 从 request.state 获取当前用户（由认证中间件设置）
    current_user = getattr(request.state, 'current_user', None)
    
    # 如果不存在，兜底从 Authorization Bearer 解析一次，避免中间件顺序导致的空值
    if current_user is None:
        try:
            from app.core.auth import get_token_from_request
            token_payload = get_token_from_request(request)
            if token_payload:
                class CurrentUser:
                    def __init__(self, payload):
                        self.id = uuid.UUID(payload["user_id"])
                        self.user_type = payload.get("user_type", "admin")
                        self.is_super_admin = payload.get("global_role") == "super_admin" or payload.get("is_super_admin", False)
                current_user = CurrentUser(token_payload)
                request.state.current_user = current_user
        except Exception as e:
            logger.error(f"[DEBUG] tenant_middleware - Fallback parse token failed: {e}", exc_info=True)
    
    # #region agent log
    logger.warning(f"[DEBUG] tenant_middleware ENTRY - path={request.url.path}, has_current_user={current_user is not None}, current_user_id={current_user.id if current_user else None}, current_user_type={current_user.user_type if current_user else None}, is_super_admin={current_user.is_super_admin if current_user else False}")
    # #endregion
    
    # 如果没有当前用户（未认证的请求，如登录接口），跳过租户检查
    if not current_user:
        logger.warning(f"[DEBUG] tenant_middleware - No current_user, skipping tenant check")
        return await call_next(request)
    
    # 提取 tenant_id（简化中间件日志，详细日志在路由层面）
    tenant_id_header = request.headers.get("X-Tenant-Id") or request.headers.get("x-tenant-id")
    
    # #region agent log
    logger.warning(f"[DEBUG] tenant_middleware - X-Tenant-Id header: {tenant_id_header}, all_headers_X-Tenant-Id={request.headers.get('X-Tenant-Id')}, all_headers_x-tenant-id={request.headers.get('x-tenant-id')}")
    # #endregion
    
    try:
        tenant_id = get_tenant_id_from_request(request, current_user)
        logger.warning(f"[DEBUG] tenant_middleware - get_tenant_id_from_request returned: {tenant_id}")
    except Exception as e:
        logger.error(f"[DEBUG] tenant_middleware - Error getting tenant_id from request: {e}", exc_info=True)
        tenant_id = None
    
    # 如果还没有 tenant_id，且用户不是 super_admin，尝试从用户的默认租户获取
    if not tenant_id and current_user and current_user.user_type == "admin" and not current_user.is_super_admin:
        logger.warning(f"[DEBUG] tenant_middleware - No tenant_id found, trying to get default tenant for user {current_user.id}")
        try:
            default_tenant_id = get_user_default_tenant(current_user.id)
            if default_tenant_id:
                tenant_id = default_tenant_id
                logger.warning(f"[DEBUG] tenant_middleware - Auto-resolved tenant_id from user default tenant: {tenant_id} for user {current_user.id}")
            else:
                logger.warning(f"[DEBUG] tenant_middleware - User {current_user.id} has no default tenant")
        except Exception as e:
            logger.error(f"[DEBUG] tenant_middleware - Failed to auto-resolve tenant_id for user {current_user.id}: {e}", exc_info=True)
    
    # #region agent log
    logger.warning(f"[DEBUG] tenant_middleware - Before tenant_id check: tenant_id={tenant_id}, is_super_admin={current_user.is_super_admin if current_user else False}, user_type={current_user.user_type if current_user else None}")
    # #endregion
    
    # 硬规则：管理员请求必须提供 tenant_id（除非是 super admin）
    # super_admin 可以不需要 tenant_id（可以访问所有租户）
    if current_user and current_user.user_type == "admin":
        if not current_user.is_super_admin and not tenant_id:
            logger.error(f"[DEBUG] tenant_middleware - TENANT_REQUIRED ERROR - user_id={current_user.id}, tenant_id_header={tenant_id_header}, tenant_id_resolved={tenant_id}")
            raise HTTPException(
                status_code=403,
                detail="TENANT_REQUIRED: Tenant ID must be set for non-super-admin requests. Please provide X-Tenant-Id header or ensure user has a default tenant."
            )
    
    # 判断是否使用 super 连接
    use_super_connection = should_use_super_connection(current_user, tenant_id_header)
    
    # 验证 membership（如果不是 super admin）
    if tenant_id and current_user and not current_user.is_super_admin:
        # 使用 SuperSessionLocal 来验证 membership（tenant_memberships 表不受 RLS 限制，但为了安全使用 super session）
        from app.database.base import SuperSessionLocal
        db = SuperSessionLocal()
        try:
            if not validate_tenant_membership(current_user.id, tenant_id, False, db):
                raise HTTPException(
                    status_code=403,
                    detail="TENANT_ACCESS_DENIED: User does not belong to the specified tenant"
                )
        finally:
            db.close()
    
    # 设置上下文变量
    # #region agent log
    logger.warning(f"[DEBUG] tenant_middleware - Setting context: tenant_id={tenant_id}, is_super_admin={current_user.is_super_admin if current_user else False}, use_super_connection={use_super_connection}")
    # #endregion
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
                metadata={
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
