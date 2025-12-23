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
    Order, Invoice, Payment, Tariff, MeterValue, PricingSnapshot, SupportMessage
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
    from app.main import app
    import redis
    from unittest.mock import MagicMock, patch
    
    # Mock Redis客户端以避免连接错误
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
    
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Mock Redis客户端 - 替换app.main中的redis_client
    original_redis_client = getattr(app, 'redis_client', None)
    try:
        # 替换redis_client
        if hasattr(app, 'redis_client'):
            app.redis_client = mock_redis
        # 也mock redis.from_url以防其他地方使用
        with patch('redis.from_url', return_value=mock_redis):
            with patch('app.main.redis_client', mock_redis, create=True):
                with TestClient(app) as test_client:
                    yield test_client
    finally:
        # 恢复原始redis_client
        if original_redis_client is not None:
            app.redis_client = original_redis_client
        app.dependency_overrides.clear()


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

