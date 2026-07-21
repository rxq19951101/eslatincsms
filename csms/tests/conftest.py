"""Pytest 配置和共享 fixtures。"""

import os
import socket
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# 设置测试环境变量
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["RATE_LIMIT_ENABLED"] = "false"
try:
    socket.gethostbyname("redis")
    os.environ["REDIS_URL"] = "redis://redis:6379/0"
except socket.gaierror:
    os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["ENABLE_MQTT_TRANSPORT"] = "false"
os.environ["ENABLE_HTTP_TRANSPORT"] = "false"
os.environ["ENABLE_WEBSOCKET_TRANSPORT"] = "false"

from app.database.base import Base
from app.database import get_db
# 导入所有模型以确保它们被注册到Base.metadata
from app.database.models import (
    Site, ChargePoint, EVSE, EVSEStatus, Device,
    ChargingSession, DeviceEvent, DeviceConfig, ChargePointConfig,
    Order, Invoice, Payment, Tariff, MeterValue, PricingSnapshot, SupportMessage,
    Tenant, AdminUser, TenantMembership, Role, TenantMembershipRole,
    RefreshToken, Alert, AlertRule, SystemConfig, AuditLog
)

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

def _mock_from_url(*args, **kwargs):
    return _mock_redis_instance

# 保存原始的SessionLocal
import app.database.base
_original_session_local = app.database.base.SessionLocal
_original_super_session_local = app.database.base.SuperSessionLocal


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
    
    # 统一替换所有已导入的会话工厂。
    # 业务模块中既有动态从 app.database.base 导入，也有模块级别别名；
    # 只替换 base.SessionLocal 会让后者继续访问真实的内存引擎。
    app.database.base.SessionLocal = TestingSessionLocal
    app.database.base.SuperSessionLocal = TestingSessionLocal
    patched_factories = []
    for module in list(sys.modules.values()):
        if module is None:
            continue
        module_dict = getattr(module, "__dict__", {})
        for name, original in (
            ("SessionLocal", _original_session_local),
            ("SuperSessionLocal", _original_super_session_local),
        ):
            if module_dict.get(name) is original:
                patched_factories.append((module, name, original))
                module_dict[name] = TestingSessionLocal
    
    # 创建初始会话用于测试
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        for module, name, original in patched_factories:
            setattr(module, name, original)
        app.database.base.SessionLocal = _original_session_local
        app.database.base.SuperSessionLocal = _original_super_session_local
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session: Session):
    """创建使用隔离数据库与 Redis mock 的测试客户端。"""
    from app.database.base import get_db

    with patch("redis.from_url", side_effect=_mock_from_url):
        from app.main import app

    Base.metadata.create_all(bind=db_session.get_bind())
    import app.core.tenant_middleware as tenant_middleware_module
    import app.database.base as database_base

    tenant_middleware_module.SessionLocal = database_base.SessionLocal
    late_patched_factories = []
    for module in list(sys.modules.values()):
        if module is None or not getattr(module, "__name__", "").startswith("app."):
            continue
        module_dict = getattr(module, "__dict__", {})
        for name in ("SessionLocal", "SuperSessionLocal"):
            current = module_dict.get(name)
            target = getattr(database_base, name)
            if current is not None and current is not target:
                late_patched_factories.append((module, name, current))
                module_dict[name] = target

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    original_redis_client = getattr(app, "redis_client", None)
    app.redis_client = _mock_redis_instance
    try:
        with patch("redis.from_url", return_value=_mock_redis_instance), patch(
            "app.main.redis_client", _mock_redis_instance, create=True
        ):
            with TestClient(app) as test_client:
                yield test_client
    finally:
        if original_redis_client is not None:
            app.redis_client = original_redis_client
        app.dependency_overrides.clear()
        for module, name, original in late_patched_factories:
            setattr(module, name, original)


@pytest.fixture
def admin_client(client, db_session: Session):
    """带真实 admin audience JWT 的管理端测试客户端。"""
    from app.core.auth import create_access_token, get_password_hash

    tenant = db_session.query(Tenant).first()
    if tenant is None:
        tenant = Tenant(id=uuid.uuid4(), name="管理端测试租户", status="active")
        db_session.add(tenant)
        db_session.flush()

    admin = AdminUser(
        id=uuid.uuid4(),
        username="test-admin",
        email="test-admin@example.com",
        password_hash=get_password_hash("test-password"),
        is_active=True,
        is_super_admin=True,
    )
    db_session.add(admin)
    db_session.commit()

    token = create_access_token({
        "user_id": str(admin.id),
        "user_type": "admin",
        "aud": "admin",
    })
    client.headers.update({"Authorization": f"Bearer {token}"})
    client.headers.update({"X-Tenant-Id": str(tenant.id)})
    return client


@pytest.fixture
def sample_tenant(db_session: Session):
    """创建供共享测试数据使用的租户。"""
    tenant = db_session.query(Tenant).first()
    if tenant is None:
        tenant = Tenant(id=uuid.uuid4(), name="测试租户", status="active")
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)
    return tenant


@pytest.fixture
def sample_site(db_session: Session, sample_tenant: Tenant):
    """创建示例站点"""
    site = Site(
        id="test_site_1",
        tenant_id=sample_tenant.id,
        name="测试站点",
        address="测试站点地址",
        latitude=39.9042,
        longitude=116.4074
    )
    db_session.add(site)
    db_session.commit()
    db_session.refresh(site)
    return site


@pytest.fixture
def sample_device(db_session: Session, sample_tenant: Tenant):
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
        tenant_id=sample_tenant.id,
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
        tenant_id=sample_site.tenant_id,
        site_id=sample_site.id,
        display_code="A01",
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
        tenant_id=sample_charge_point.tenant_id,
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
        tenant_id=sample_charge_point.tenant_id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        status="Available",
        last_seen=None
    )
    db_session.add(evse_status)
    db_session.commit()
    db_session.refresh(evse_status)
    return evse_status
