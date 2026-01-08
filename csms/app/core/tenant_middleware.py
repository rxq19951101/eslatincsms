#
# 多租户数据隔离中间件
# 自动为所有数据库查询添加租户ID过滤条件
#

from typing import Callable, Optional
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy.orm import Session
from app.database.base import SessionLocal
from app.core.security import verify_token
import logging

logger = logging.getLogger("ocpp_csms")


class TenantMiddleware(BaseHTTPMiddleware):
    """多租户数据隔离中间件
    
    功能：
    1. 从JWT Token中提取tenant_id
    2. 将tenant_id注入到请求状态中
    3. 为后续的数据访问提供租户上下文
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求"""
        # 初始化租户上下文
        tenant_id = None
        user_id = None
        is_super_admin = False
        
        # 从Authorization头中提取Token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            payload = verify_token(token)
            if payload:
                tenant_id = payload.get("tenant_id")
                user_id = payload.get("sub")
                is_super_admin = payload.get("is_super_admin", False)
        
        # 将租户信息注入到请求状态中
        request.state.tenant_id = tenant_id
        request.state.user_id = user_id
        request.state.is_super_admin = is_super_admin
        
        # 继续处理请求
        response = await call_next(request)
        return response


def get_tenant_id(request: Request) -> Optional[str]:
    """从请求状态中获取租户ID"""
    return getattr(request.state, "tenant_id", None)


def get_user_id(request: Request) -> Optional[str]:
    """从请求状态中获取用户ID"""
    return getattr(request.state, "user_id", None)


def is_super_admin(request: Request) -> bool:
    """检查是否为超级管理员"""
    return getattr(request.state, "is_super_admin", False)


def apply_tenant_filter(query, model_class, tenant_id: Optional[str], is_super_admin: bool = False):
    """为查询添加租户过滤条件
    
    Args:
        query: SQLAlchemy查询对象
        model_class: 模型类
        tenant_id: 租户ID
        is_super_admin: 是否为超级管理员
    
    Returns:
        过滤后的查询对象
    """
    # 超级管理员且拥有跨租户权限时，不过滤
    if is_super_admin:
        # 这里可以进一步检查是否有跨租户权限
        # 暂时允许超级管理员访问所有数据
        return query
    
    # 如果模型有tenant_id字段，添加过滤条件
    if hasattr(model_class, 'tenant_id'):
        if tenant_id:
            return query.filter(model_class.tenant_id == tenant_id)
        else:
            # 如果没有tenant_id，返回空查询（防止数据泄露）
            return query.filter(False)
    
    return query
