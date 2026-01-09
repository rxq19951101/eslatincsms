"""
Pytest 配置和共享fixtures
"""
import pytest
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# 设置测试环境变量
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# 在Docker容器内使用redis服务名，本地测试使用localhost
import socket
try:
    # 尝试连接redis服务（Docker环境）
    socket.gethostbyname("redis")
    os.environ["REDIS_URL"] = "redis://redis:6379/0"
except socket.gaierror:
    # 本地环境使用localhost
    os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["ENABLE_MQTT_TRANSPORT"] = "false"  # 禁用MQTT传输以避免连接错误
os.environ["ENABLE_HTTP_TRANSPORT"] = "false"  # 禁用HTTP传输
os.environ["ENABLE_WEBSOCKET_TRANSPORT"] = "false"  # 禁用WebSocket传输

# Mock Redis 客户端以避免连接错误
import redis
from unittest.mock import MagicMock, patch

# 创建一个 mock Redis 客户端
_mock_redis = MagicMock()
_mock_redis.hgetall.return_value = {}
_mock_redis.hset.return_value = None
_mock_redis.get.return_value = None
_mock_redis.set.return_value = None
_mock_redis.delete.return_value = None
_mock_redis.exists.return_value = False
_mock_redis.ping.return_value = True
_mock_redis.config_set.return_value = True
_mock_redis.pubsub.return_value = MagicMock()

# 在导入 app.main 之前mock Redis
import sys
if 'app.main' not in sys.modules:
    # 延迟导入，在 app.main 导入后替换
    pass

from app.database.base import Base
from app.database import get_db
# 导入所有模型以确保它们被注册到Base.metadata
from app.database.models import (
    Site, ChargePoint, EVSE, EVSEStatus, Device,
    ChargingSession, DeviceEvent, DeviceConfig, ChargePointConfig,
    Order, Invoice, Payment, Tariff, MeterValue, PricingSnapshot, SupportMessage,
    Tenant, AdminUser, EndUser, TenantMembership, Role, TenantMembershipRole,
    RefreshToken, Alert, AlertRule, SystemConfig, AuditLog
)

# Mock Redis客户端在导入app.main之前
import redis
from unittest.mock import MagicMock, patch

# 创建mock Redis客户端
_mock_redis_instance = MagicMock()
_mock_redis_instance.hgetall.return_value = {}
_mock_redis_instance.hset.return_value = None
_mock_redis_instance.get.return_value = None
_mock_redis_instance.set.return_value = None
_mock_redis_instance.delete.return_value = None
_mock_redis_instance.exists.return_value = False
_mock_redis_instance.ping.return_value = True
_mock_redis_instance.config_set.return_value = True
_mock_redis_instance.pubsub.return_value = MagicMock()

# Mock redis.from_url
_original_from_url = redis.from_url
def _mock_from_url(*args, **kwargs):
    return _mock_redis_instance

# 延迟导入app，避免在设置环境变量之前初始化
def get_app():
    # 在导入app.main之前mock Redis
    with patch('redis.from_url', side_effect=_mock_from_url):
        from app.main import app
        # 替换app.main中的redis_client
        if hasattr(app, 'redis_client'):
            app.redis_client = _mock_redis_instance
        return app

# 保存原始的SessionLocal
import app.database.base
_original_session_local = app.database.base.SessionLocal


@pytest.fixture(scope="function")
def db_session():
    """创建测试数据库会话"""
    # 使用内存SQLite数据库
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    # 验证表已创建
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if 'devices' not in tables:
        # 如果表不存在，重新创建
        Base.metadata.create_all(bind=engine)
    
    # Mock SessionLocal以使用测试引擎
    # 直接替换为TestingSessionLocal，这样所有调用都会返回绑定到测试引擎的会话
    app.database.base.SessionLocal = TestingSessionLocal
    
    # 创建初始会话用于测试
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        # 恢复原始SessionLocal（每个测试结束后恢复，避免影响其他测试）
        app.database.base.SessionLocal = _original_session_local
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session: Session):
    """创建测试客户端"""
    import logging
    import sys
    from app.database.base import get_db
    from fastapi.testclient import TestClient
    
    # 立即输出，确保能看到
    print("\n" + "=" * 60, flush=True)
    print("✓ [FIXTURE] client fixture 开始执行", flush=True)
    print("=" * 60, flush=True)
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    logger.info("=" * 60)
    logger.info("开始创建测试客户端 (client fixture)")
    logger.info("=" * 60)
    
    print("✓ [FIXTURE] Logger已获取", flush=True)
    
    try:
        logger.info("步骤1: 导入app.main")
        import sys
        logger.info(f"  - Python路径: {sys.path[:3]}")
        from app.main import app
        logger.info("  - app.main导入成功")
        logger.info(f"  - app对象: {app}")
    except Exception as e:
        logger.error(f"步骤1失败: 导入app.main失败: {e}", exc_info=True)
        raise
    
    try:
        print("✓ [FIXTURE] 步骤2: 导入redis和mock模块", file=sys.stderr, flush=True)
        logger.info("步骤2: 导入redis和mock模块")
        import redis
        from unittest.mock import MagicMock, patch
        print("✓ [FIXTURE] 模块导入成功", file=sys.stderr, flush=True)
        logger.info("  - 模块导入成功")
    except Exception as e:
        print(f"✗ [FIXTURE] 步骤2失败: 导入模块失败: {e}", file=sys.stderr, flush=True)
        logger.error(f"步骤2失败: 导入模块失败: {e}", exc_info=True)
        raise
    
    try:
        print("✓ [FIXTURE] 步骤3: 创建Mock Redis客户端", file=sys.stderr, flush=True)
        logger.info("步骤3: 创建Mock Redis客户端")
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.hset.return_value = None
        mock_redis.get.return_value = None
        mock_redis.set.return_value = None
        mock_redis.delete.return_value = None
        mock_redis.exists.return_value = False
        mock_redis.ping.return_value = True
        mock_redis.config_set.return_value = True
        mock_redis.pubsub.return_value = MagicMock()
        print("✓ [FIXTURE] Mock Redis客户端创建成功", file=sys.stderr, flush=True)
        logger.info("  - Mock Redis客户端创建成功")
    except Exception as e:
        print(f"✗ [FIXTURE] 步骤3失败: 创建Mock Redis失败: {e}", file=sys.stderr, flush=True)
        logger.error(f"步骤3失败: 创建Mock Redis失败: {e}", exc_info=True)
        raise
    
    try:
        print("✓ [FIXTURE] 步骤4: 设置数据库依赖覆盖", file=sys.stderr, flush=True)
        logger.info("步骤4: 设置数据库依赖覆盖")
        def override_get_db():
            try:
                logger.info("    - get_db被调用，返回db_session")
                yield db_session
            finally:
                logger.info("    - get_db清理完成")
                pass
        
        app.dependency_overrides[get_db] = override_get_db
        print("✓ [FIXTURE] 数据库依赖覆盖设置成功", file=sys.stderr, flush=True)
        logger.info("  - 数据库依赖覆盖设置成功")
        logger.info(f"  - dependency_overrides: {list(app.dependency_overrides.keys())}")
        print(f"  - dependency_overrides: {list(app.dependency_overrides.keys())}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"✗ [FIXTURE] 步骤4失败: 设置数据库依赖覆盖失败: {e}", file=sys.stderr, flush=True)
        logger.error(f"步骤4失败: 设置数据库依赖覆盖失败: {e}", exc_info=True)
        raise
    
    original_redis_client = None
    try:
        print("✓ [FIXTURE] 步骤5: Mock Redis客户端并创建TestClient", file=sys.stderr, flush=True)
        logger.info("步骤5: Mock Redis客户端并创建TestClient")
        original_redis_client = getattr(app, 'redis_client', None)
        logger.info(f"  - 原始redis_client: {original_redis_client}")
        
        # 替换redis_client
        if hasattr(app, 'redis_client'):
            app.redis_client = mock_redis
            logger.info("  - app.redis_client已替换为mock_redis")
        else:
            logger.info("  - app没有redis_client属性，将创建")
        
        # 也mock redis.from_url以防其他地方使用
        logger.info("  - 开始patch redis.from_url...")
        with patch('redis.from_url', return_value=mock_redis):
            logger.info("  - redis.from_url已patch")
            logger.info("  - 开始patch app.main.redis_client...")
            with patch('app.main.redis_client', mock_redis, create=True):
                logger.info("  - app.main.redis_client已patch")
                print("✓ [FIXTURE] 开始创建TestClient（这可能需要一些时间）...", file=sys.stderr, flush=True)
                logger.info("  - 开始创建TestClient（这可能需要一些时间）...")
                import time
                start_time = time.time()
                print(f"  - 开始时间: {start_time}", file=sys.stderr, flush=True)
                
                test_client = TestClient(app)
                elapsed = time.time() - start_time
                print(f"✓ [FIXTURE] TestClient创建成功！耗时: {elapsed:.2f}秒", file=sys.stderr, flush=True)
                logger.info(f"  - TestClient创建成功！耗时: {elapsed:.2f}秒")
                logger.info(f"  - TestClient对象: {test_client}")
                print(f"  - TestClient对象类型: {type(test_client)}", file=sys.stderr, flush=True)
                
                with test_client:
                    print("✓ [FIXTURE] TestClient上下文管理器已进入", file=sys.stderr, flush=True)
                    logger.info("  - TestClient上下文管理器已进入")
                    yield test_client
                    print("✓ [FIXTURE] TestClient使用完毕，准备退出上下文", file=sys.stderr, flush=True)
                    logger.info("  - TestClient使用完毕，准备退出上下文")
                print("✓ [FIXTURE] TestClient上下文管理器已退出", file=sys.stderr, flush=True)
                logger.info("  - TestClient上下文管理器已退出")
    except Exception as e:
        logger.error(f"步骤5失败: 创建TestClient失败: {e}", exc_info=True)
        import traceback
        logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
        raise
    finally:
        logger.info("步骤6: 清理和恢复")
        # 恢复原始redis_client
        if original_redis_client is not None:
            app.redis_client = original_redis_client
            logger.info("  - 已恢复原始redis_client")
        app.dependency_overrides.clear()
        logger.info("  - 已清理dependency_overrides")
        logger.info("  - client fixture清理完成")


@pytest.fixture
def sample_site(db_session: Session):
    """创建示例站点"""
    site = Site(
        id="test_site_1",
        name="测试站点",
        address="测试地址",
        latitude=39.9042,
        longitude=116.4074
    )
    db_session.add(site)
    db_session.commit()
    db_session.refresh(site)
    return site


@pytest.fixture
def sample_device(db_session: Session):
    """创建示例设备（每个设备独立存储master_secret）"""
    # 使用真实的加密逻辑创建master_secret
    try:
        from app.core.crypto import encrypt_master_secret
        import secrets
        master_secret = f"test_secret_{secrets.token_urlsafe(16)}"
        encrypted_secret = encrypt_master_secret(master_secret)
    except ImportError:
        # 如果加密模块不可用，使用简单哈希（仅用于测试）
        import hashlib
        import secrets
        master_secret = f"test_secret_{secrets.token_urlsafe(16)}"
        encrypted_secret = hashlib.sha256(master_secret.encode()).hexdigest()
    
    device = Device(
        serial_number="123456789012345",
        type_code="zcf",
        mqtt_client_id="zcf&123456789012345",
        mqtt_username="123456789012345",
        master_secret_encrypted=encrypted_secret,
        encryption_algorithm="AES-256-GCM",
        is_active=True
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


@pytest.fixture
def sample_charge_point(db_session: Session, sample_site: Site, sample_device: Device):
    """创建示例充电桩"""
    charge_point = ChargePoint(
        id="CP-TEST-001",
        site_id=sample_site.id,
        vendor="测试厂商",
        model="测试型号",
        device_serial_number=sample_device.serial_number,
        is_active=True
    )
    db_session.add(charge_point)
    db_session.commit()
    db_session.refresh(charge_point)
    return charge_point


@pytest.fixture
def sample_evse(db_session: Session, sample_charge_point: ChargePoint):
    """创建示例EVSE"""
    evse = EVSE(
        charge_point_id=sample_charge_point.id,
        evse_id=1,
        connector_type="Type2",
        max_power_kw=7.0
    )
    db_session.add(evse)
    db_session.commit()
    db_session.refresh(evse)
    return evse


@pytest.fixture
def sample_evse_status(db_session: Session, sample_evse: EVSE, sample_charge_point: ChargePoint):
    """创建示例EVSE状态"""
    evse_status = EVSEStatus(
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        status="Available",
        last_seen=None
    )
    db_session.add(evse_status)
    db_session.commit()
    db_session.refresh(evse_status)
    return evse_status

