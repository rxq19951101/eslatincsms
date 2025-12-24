"""
数据库模型单元测试
"""
import pytest
from datetime import datetime, timezone
from app.database.models import (
    Site, ChargePoint, EVSE, EVSEStatus, Device,
    ChargingSession, DeviceEvent, Order, Invoice, Payment, Tariff
)


class TestDatabaseModels:
    """数据库模型测试类"""
    
    def test_site_creation(self, db_session):
        """测试创建站点"""
        site = Site(
            id="test_site_1",
            name="测试站点",
            address="测试地址",
            latitude=39.9042,
            longitude=116.4074
        )
        db_session.add(site)
        db_session.commit()
        
        assert site.id == "test_site_1"
        assert site.name == "测试站点"
        assert site.latitude == 39.9042
    
    def test_charge_point_creation(self, db_session, sample_site):
        """测试创建充电桩"""
        charge_point = ChargePoint(
            id="CP-TEST-001",
            site_id=sample_site.id,
            vendor="测试厂商",
            model="测试型号"
        )
        db_session.add(charge_point)
        db_session.commit()
        
        assert charge_point.id == "CP-TEST-001"
        assert charge_point.site_id == sample_site.id
    
    def test_device_creation(self, db_session):
        """测试创建设备（每个设备独立存储master_secret）"""
        try:
            from app.core.crypto import encrypt_master_secret
            import secrets
            master_secret = f"test_secret_{secrets.token_urlsafe(16)}"
            encrypted_secret = encrypt_master_secret(master_secret)
        except ImportError:
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
            encryption_algorithm="AES-256-GCM"
        )
        db_session.add(device)
        db_session.commit()
        
        assert device.serial_number == "123456789012345"
        assert device.type_code == "zcf"
        assert device.master_secret_encrypted is not None
    
    def test_evse_creation(self, db_session, sample_charge_point):
        """测试创建EVSE"""
        evse = EVSE(
            charge_point_id=sample_charge_point.id,
            evse_id=1,
            connector_type="Type2",
            max_power_kw=7.0
        )
        db_session.add(evse)
        db_session.commit()
        
        assert evse.charge_point_id == sample_charge_point.id
        assert evse.evse_id == 1
        assert evse.connector_type == "Type2"  # connector_type 现在在 EVSE 表中
    
    def test_evse_connector_type_default(self, db_session, sample_charge_point):
        """测试EVSE connector_type 默认值"""
        evse = EVSE(
            charge_point_id=sample_charge_point.id,
            evse_id=2
            # 不指定 connector_type，应该使用默认值
        )
        db_session.add(evse)
        db_session.commit()
        
        assert evse.connector_type == "Type2"  # 默认值
    
    def test_charging_session_creation(self, db_session, sample_charge_point, sample_evse):
        """测试创建充电会话"""
        session = ChargingSession(
            charge_point_id=sample_charge_point.id,
            evse_id=sample_evse.id,
            transaction_id=12345,
            id_tag="TEST_USER_001",
            start_time=datetime.now(timezone.utc),
            status="ongoing"
        )
        db_session.add(session)
        db_session.commit()
        
        assert session.transaction_id == 12345
    
    def test_charging_session_transaction_unique_constraint(self, db_session, sample_charge_point):
        """测试 transaction_id 组合唯一约束 (charge_point_id, evse_id, transaction_id)"""
        # 创建两个不同的 EVSE
        evse1 = EVSE(
            charge_point_id=sample_charge_point.id,
            evse_id=1,
            connector_type="Type2"
        )
        evse2 = EVSE(
            charge_point_id=sample_charge_point.id,
            evse_id=2,
            connector_type="CCS2"
        )
        db_session.add_all([evse1, evse2])
        db_session.flush()
        
        # 在同一个充电桩的不同 EVSE 可以使用相同的 transaction_id
        session1 = ChargingSession(
            charge_point_id=sample_charge_point.id,
            evse_id=evse1.id,
            transaction_id=99999,
            id_tag="USER1",
            start_time=datetime.now(timezone.utc),
            status="ongoing"
        )
        session2 = ChargingSession(
            charge_point_id=sample_charge_point.id,
            evse_id=evse2.id,
            transaction_id=99999,  # 相同的 transaction_id，但不同的 evse_id
            id_tag="USER2",
            start_time=datetime.now(timezone.utc),
            status="ongoing"
        )
        db_session.add_all([session1, session2])
        db_session.commit()
        
        # 应该可以成功创建（因为 evse_id 不同）
        assert session1.transaction_id == 99999
        assert session2.transaction_id == 99999
        assert session1.evse_id != session2.evse_id
        
        # 尝试在同一个 (charge_point_id, evse_id) 创建相同的 transaction_id 应该失败
        from sqlalchemy.exc import IntegrityError
        session3 = ChargingSession(
            charge_point_id=sample_charge_point.id,
            evse_id=evse1.id,  # 相同的 evse_id
            transaction_id=99999,  # 相同的 transaction_id
            id_tag="USER3",
            start_time=datetime.now(timezone.utc),
            status="ongoing"
        )
        db_session.add(session3)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    def test_device_event_creation(self, db_session, sample_charge_point, sample_device):
        """测试创建设备事件"""
        event = DeviceEvent(
            charge_point_id=sample_charge_point.id,
            device_serial_number=sample_device.serial_number,
            event_type="heartbeat",
            timestamp=datetime.now(timezone.utc)
        )
        db_session.add(event)
        db_session.commit()
        
        assert event.event_type == "heartbeat"
        assert event.device_serial_number == sample_device.serial_number
    
    def test_order_creation(self, db_session, sample_charge_point):
        """测试创建订单"""
        order = Order(
            id="ORDER-TEST-001",  # Order.id是主键，必须提供
            charge_point_id=sample_charge_point.id,
            user_id="TEST_USER_001",
            id_tag="TAG_001",  # id_tag是必填字段
            status="ongoing"
        )
        db_session.add(order)
        db_session.commit()
        
        assert order.id == "ORDER-TEST-001"
        assert order.user_id == "TEST_USER_001"
        assert order.status == "ongoing"
    
    def test_tariff_creation(self, db_session, sample_site):
        """测试创建定价规则"""
        tariff = Tariff(
            site_id=sample_site.id,
            name="测试定价",
            base_price_per_kwh=1.5,
            service_fee=0.1,
            valid_from=datetime.now(timezone.utc),  # valid_from是NOT NULL字段
            is_active=True
        )
        db_session.add(tariff)
        db_session.commit()
        
        assert tariff.base_price_per_kwh == 1.5
        assert tariff.is_active is True

