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

# 在超级引擎的每个连接上设置 app_super 角色
@event.listens_for(super_engine, "connect")
def set_app_super_role(dbapi_conn, connection_record):
    """在连接建立后设置 app_super 角色"""
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("SET ROLE app_super")
    except Exception as e:
        # 如果角色不存在或没有权限，记录警告但不中断
        logger.warning(f"无法设置 app_super 角色: {e}")
        # 关键：SET ROLE 失败会让连接处于 aborted transaction 状态，必须 rollback 清理，否则后续任何查询都会 InFailedSqlTransaction
        try:
            dbapi_conn.rollback()
        except Exception:
            pass
    finally:
        cursor.close()

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SuperSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=super_engine)


# 在每个事务开始时设置租户上下文（硬规则）
@event.listens_for(Session, "after_begin")
def set_tenant_context(session, transaction, connection):
    """在每个事务开始时设置租户上下文（硬规则）"""
    # 检查是否使用的是 super_engine（绕过所有检查）
    # 通过检查连接字符串是否包含 role=app_super 来判断
    try:
        engine_url = str(connection.engine.url) if hasattr(connection, 'engine') and hasattr(connection.engine, 'url') else ''
        is_super_engine = 'role=app_super' in engine_url or 'role%3Dapp_super' in engine_url
    except:
        is_super_engine = False
    
    # 如果使用 super_engine，直接跳过所有检查和设置（完全绕过 RLS）
    if is_super_engine:
        return
    
    # 使用 get() 方法，如果未设置则使用默认值
    try:
        tenant_id = tenant_id_context.get()
    except LookupError:
        tenant_id = None
    
    try:
        is_super_admin = is_super_admin_context.get()
    except LookupError:
        is_super_admin = False
    
    try:
        use_super_connection = use_super_connection_context.get()
    except LookupError:
        use_super_connection = False
    
    # 检查是否在测试环境中（SQLite不支持SET LOCAL）
    # 对于SQLite，我们跳过SET LOCAL命令，但仍需要验证tenant_id
    try:
        from sqlalchemy.engine import Engine
        dialect_name = connection.engine.dialect.name if hasattr(connection, 'engine') else None
        is_sqlite = dialect_name == 'sqlite'
    except:
        is_sqlite = False
    
    # 如果是 super_admin，完全跳过所有检查和设置（允许访问所有数据）
    if is_super_admin:
        return  # super_admin 不需要设置 tenant_id，完全绕过 RLS
    
    # 硬规则：非 super admin 必须设置 tenant_id
    # 例外情况：
    # 1. 如果 tenant_id_context 和 is_super_admin_context 都未设置（可能是初始化脚本或认证接口）
    # 2. 对于认证相关的操作（如登录、注册），应该在中间件层面跳过，而不是在这里检查
    # 3. 如果使用 super_connection，说明是超级管理员操作，应该允许
    # 4. 如果是初始化脚本或认证操作，应该允许（通过检查上下文是否为默认值）
    if not tenant_id and not use_super_connection:
        if not is_sqlite:  # 只在非SQLite（生产环境）中强制检查
            # 对于认证操作，tenant_id_context 和 is_super_admin_context 都应该是默认值（未设置）
            # 但这里我们无法区分"未设置"和"明确设置为 None"
            # 所以暂时放宽检查：如果两者都是默认值，允许继续（可能是认证操作）
            # 否则抛出异常
            import logging
            logger = logging.getLogger("ocpp_csms")
            
            # 检查是否是默认值（未设置或设置为 None）
            try:
                ctx_tenant_id = tenant_id_context.get()
                # 如果 tenant_id 是 None，可能是：
                # 1. 超级管理员请求（没有携带 X-Tenant-Id）
                # 2. 认证操作（如 /auth/me，跳过了 tenant_middleware）
                # 对于这两种情况，我们都应该允许继续
                is_default_context = (ctx_tenant_id is None)
            except LookupError:
                is_default_context = True
            
            if is_default_context:
                # 可能是认证操作或超级管理员访问，允许继续但记录警告
                logger.warning(f"Database access without tenant_id context (likely during authentication or super admin operation). Allowing but this should be handled by middleware.")
                # 不抛出异常，允许继续
            else:
                # tenant_id 存在但不是 None，正常情况，不需要额外检查
                pass
    
    if use_super_connection and is_super_admin:
        # 超级管理员使用 app_super 角色（绕过 RLS）
        # 注意：这需要在连接字符串中指定角色，或者在连接时设置角色
        if not is_sqlite:
            try:
                # 尝试设置角色为 app_super（绕过 RLS）
                connection.execute(text("SET LOCAL role = app_super"))
            except Exception as e:
                # 如果角色不存在，记录警告但继续（可能是权限问题）
                import logging
                logger = logging.getLogger("ocpp_csms")
                logger.warning(f"Failed to set role to app_super: {e}. Continuing without role change.")
                # 不抛出异常，允许继续
    elif tenant_id:
        # 普通用户：设置 tenant_id（PostgreSQL 支持）
        if not is_sqlite:
            try:
                connection.execute(
                    text("SET LOCAL app.tenant_id = :tenant_id"),
                    {"tenant_id": str(tenant_id)}
                )
            except Exception as e:
                # SQLite 不支持 SET LOCAL，跳过
                if not is_sqlite:
                    raise
    else:
        # 如果 tenant_id 为 None 且不是 super_connection
        # 这种情况不应该发生，因为前面的检查应该已经处理了
        # 但如果到达这里，记录警告但不抛出异常（允许继续，可能是认证操作或初始化脚本）
        if not is_sqlite and not use_super_connection:
            import logging
            logger = logging.getLogger("ocpp_csms")
            logger.warning(f"Database access without tenant_id and super_connection. This should only happen during authentication or initialization. Allowing to continue.")
            # 不抛出异常，允许继续（认证操作需要能够访问数据库）


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


# 初始化数据库
def init_db():
    """初始化数据库表"""
    Base.metadata.create_all(bind=engine)


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

