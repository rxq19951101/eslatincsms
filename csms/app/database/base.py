#
# 数据库基础配置
# 包含数据库引擎、会话工厂等基础组件
# 支持多租户 RLS（Row-Level Security）
#

import os
import time
import uuid
import logging
from typing import Optional
from contextlib import contextmanager
from contextvars import ContextVar
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import declarative_base
from fastapi import HTTPException
from app.core.config import get_settings

logger = logging.getLogger("ocpp_csms")

settings = get_settings()

# 创建Base（在models中会继承）
Base = declarative_base()

# 请求级别的上下文变量（用于多租户隔离）
tenant_id_context: ContextVar[Optional[uuid.UUID]] = ContextVar('tenant_id', default=None)
is_super_admin_context: ContextVar[bool] = ContextVar('is_super_admin', default=False)
use_super_connection_context: ContextVar[bool] = ContextVar('use_super_connection', default=False)
database_access_scope_context: ContextVar[Optional[str]] = ContextVar(
    'database_access_scope', default=None
)

DATABASE_ACCESS_SCOPES = frozenset({"authentication", "app_platform", "system"})


@contextmanager
def database_access_scope(scope: str):
    """Mark an explicit, non-tenant database path without granting super access."""
    if scope not in DATABASE_ACCESS_SCOPES:
        raise ValueError(f"Unsupported database access scope: {scope}")
    token = database_access_scope_context.set(scope)
    try:
        yield
    finally:
        database_access_scope_context.reset(token)

# 创建数据库引擎（带连接池）
# 注意：普通请求使用 app_user 角色，超级管理员请求使用 app_super 角色
# 这里先创建默认引擎，超级管理员连接在需要时动态创建
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,  # 自动重连
    pool_recycle=settings.db_pool_recycle,   # 1小时后回收连接
    echo=settings.db_echo
)

# 创建超级管理员引擎
# 使用相同的连接字符串，但在连接后通过监听器设置角色
# 这样可以避免角色登录问题（app_super是NOLOGIN角色）
super_database_url = os.getenv("SUPER_DATABASE_URL", settings.database_url)

super_engine = create_engine(
    super_database_url,
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=settings.db_pool_recycle,
    echo=settings.db_echo
)

# 在 PostgreSQL 超级引擎的每个连接上设置 app_super 角色。
# 显式超级会话不得在角色缺失时静默回退到普通连接权限。
if super_engine.dialect.name == "postgresql":
    @event.listens_for(super_engine, "connect")
    def set_app_super_role(dbapi_conn, connection_record):
        """在连接建立后设置 app_super 角色。"""
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("SET ROLE app_super")
        except Exception:
            try:
                dbapi_conn.rollback()
            except Exception:
                pass
            logger.error("Unable to activate required app_super database role", exc_info=True)
            raise
        finally:
            cursor.close()

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SuperSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=super_engine)


# 在每个事务开始时设置租户上下文（硬规则）
@event.listens_for(Session, "after_begin")
def set_tenant_context(session, transaction, connection):
    """在每个普通事务开始时设置租户上下文。"""
    # SuperSessionLocal 是代码中的显式特权边界。两个引擎可以使用相同 URL，
    # 因此必须按引擎实例识别，不能从 URL 文本猜测。
    if connection.engine is super_engine:
        return

    if connection.engine.dialect.name == "sqlite":
        return

    tenant_id = tenant_id_context.get()
    access_scope = database_access_scope_context.get()

    if tenant_id:
        connection.execute(
            text("SET LOCAL app.tenant_id = :tenant_id"),
            {"tenant_id": str(tenant_id)},
        )
        return

    if access_scope in DATABASE_ACCESS_SCOPES:
        logger.debug(
            "Database access without tenant context under explicit scope=%s",
            access_scope,
        )
        return

    if is_super_admin_context.get() or use_super_connection_context.get():
        logger.warning(
            "Privileged request context used a regular database session; "
            "SuperSessionLocal is required"
        )
        return

    # 未标注的无租户普通会话仍是风险信号，不全局降级或静默忽略。
    logger.warning(
        "Database access without tenant_id or an explicit authentication, "
        "app_platform, or system scope"
    )


# 数据库依赖注入
def get_db() -> Session:
    """获取数据库会话（根据上下文选择普通或超级管理员连接）"""
    use_super_connection = use_super_connection_context.get()
    is_super_admin = is_super_admin_context.get()
    
    # 如果是 super_admin，使用 SuperSessionLocal（绕过 RLS）
    # 或者明确设置了 use_super_connection
    if use_super_connection or is_super_admin:
        db = SuperSessionLocal()
    else:
        db = SessionLocal()
    
    try:
        yield db
    finally:
        db.close()


# 数据库健康检查
def check_db_health(max_retries: int = 3, retry_delay: float = 2.0) -> bool:
    """
    检查数据库连接健康状态
    
    Args:
        max_retries: 最大重试次数（用于启动时等待数据库就绪）
        retry_delay: 重试延迟（秒）
    """
    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            # 最后一次尝试失败，记录错误但不抛出异常
            import logging
            logger = logging.getLogger("ocpp_csms")
            logger.debug(f"数据库连接检查失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            return False
    return False
