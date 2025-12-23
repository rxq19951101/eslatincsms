"""
充电桩服务单元测试
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.services.charge_point_service import ChargePointService
from app.database.models import ChargePoint, Device, Site, EVSE, EVSEStatus


class TestChargePointService:
    """充电桩服务测试类"""
    
    def test_get_or_create_charge_point_new(self, db_session: Session, sample_site: Site):
        """测试创建新充电桩"""
        charge_point = ChargePointService.get_or_create_charge_point(
            db=db_session,
            charge_point_id="CP-NEW-001",
            vendor="测试厂商",
            model="测试型号"
        )
        
        assert charge_point is not None
        assert charge_point.id == "CP-NEW-001"
        assert charge_point.vendor == "测试厂商"
        assert charge_point.model == "测试型号"
        # get_or_create_charge_point会创建默认站点，site_id可能是：
        # - default_site（向后兼容）
        # - test_site_1（如果sample_site存在）
        # - 生成的站点ID（格式：site_默认站点_xxx）
        assert charge_point.site_id is not None
        # 验证站点ID格式：可能是固定ID或生成的ID（以site_开头）
        assert (charge_point.site_id in [sample_site.id, "default_site"] or 
                charge_point.site_id.startswith("site_")), \
            f"站点ID {charge_point.site_id} 不符合预期格式"
    
    def test_get_or_create_charge_point_existing(self, db_session: Session, sample_charge_point: ChargePoint):
        """测试获取已存在的充电桩"""
        charge_point = ChargePointService.get_or_create_charge_point(
            db=db_session,
            charge_point_id=sample_charge_point.id
        )
        
        assert charge_point.id == sample_charge_point.id
        assert charge_point.vendor == sample_charge_point.vendor
    
    def test_get_or_create_charge_point_with_device(self, db_session: Session, sample_site: Site, sample_device: Device):
        """测试创建带设备的充电桩"""
        charge_point = ChargePointService.get_or_create_charge_point(
            db=db_session,
            charge_point_id="CP-DEVICE-001",
            device_serial_number=sample_device.serial_number,
            vendor="测试厂商"
        )
        
        assert charge_point.device_serial_number == sample_device.serial_number
    
    def test_get_or_create_charge_point_invalid_device(self, db_session: Session, sample_site: Site):
        """测试使用无效设备序列号创建充电桩"""
        charge_point = ChargePointService.get_or_create_charge_point(
            db=db_session,
            charge_point_id="CP-INVALID-001",
            device_serial_number="999999999999999",  # 不存在的设备
            vendor="测试厂商"
        )
        
        # 应该创建充电桩，但不关联设备
        assert charge_point is not None
        assert charge_point.device_serial_number is None
    
    def test_update_evse_status_new(self, db_session: Session, sample_charge_point: ChargePoint):
        """测试更新EVSE状态（新建）"""
        evse_status = ChargePointService.update_evse_status(
            db=db_session,
            charge_point_id=sample_charge_point.id,
            evse_id=1,
            status="Available"
        )
        
        assert evse_status is not None
        assert evse_status.status == "Available"
        assert evse_status.charge_point_id == sample_charge_point.id
    
    def test_update_evse_status_existing(self, db_session: Session, sample_evse_status: EVSEStatus):
        """测试更新已存在的EVSE状态"""
        # 记录更新前的状态
        previous_status = sample_evse_status.status
        
        evse_status = ChargePointService.update_evse_status(
            db=db_session,
            charge_point_id=sample_evse_status.charge_point_id,
            evse_id=sample_evse_status.evse_id,
            status="Charging"
        )
        
        assert evse_status.status == "Charging"
        # EVSEStatus模型没有previous_status字段，只验证状态已更新
        assert evse_status.status != previous_status
    
    def test_update_evse_status_invalid_charge_point(self, db_session: Session):
        """测试使用无效充电桩ID更新EVSE状态"""
        with pytest.raises(ValueError, match="ChargePoint.*不存在"):
            ChargePointService.update_evse_status(
                db=db_session,
                charge_point_id="CP-INVALID",
                evse_id=1,
                status="Available"
            )
    
    def test_record_heartbeat(self, db_session: Session, sample_charge_point: ChargePoint, sample_device: Device):
        """测试记录心跳"""
        ChargePointService.record_heartbeat(
            db=db_session,
            charge_point_id=sample_charge_point.id,
            device_serial_number=sample_device.serial_number
        )
        
        # 检查是否创建了DeviceEvent
        from app.database.models import DeviceEvent
        event = db_session.query(DeviceEvent).filter(
            DeviceEvent.charge_point_id == sample_charge_point.id,
            DeviceEvent.event_type == "heartbeat"
        ).first()
        
        assert event is not None
        assert event.device_serial_number == sample_device.serial_number
    
    def test_record_heartbeat_invalid_device(self, db_session: Session, sample_charge_point: ChargePoint):
        """测试使用无效设备序列号记录心跳"""
        # 不应该抛出异常，应该记录警告并继续
        ChargePointService.record_heartbeat(
            db=db_session,
            charge_point_id=sample_charge_point.id,
            device_serial_number="999999999999999"  # 不存在的设备
        )
        
        # 检查是否创建了DeviceEvent（但device_serial_number为None）
        from app.database.models import DeviceEvent
        event = db_session.query(DeviceEvent).filter(
            DeviceEvent.charge_point_id == sample_charge_point.id,
            DeviceEvent.event_type == "heartbeat"
        ).first()
        
        assert event is not None
        assert event.device_serial_number is None
    
    def test_get_evse_status(self, db_session: Session, sample_evse_status: EVSEStatus):
        """测试获取EVSE状态"""
        evse_status = ChargePointService.get_evse_status(
            db=db_session,
            charge_point_id=sample_evse_status.charge_point_id,
            evse_id=sample_evse_status.evse_id
        )
        
        assert evse_status is not None
        assert evse_status.status == sample_evse_status.status
    
    def test_get_evse_status_not_found(self, db_session: Session, sample_charge_point: ChargePoint):
        """测试获取不存在的EVSE状态"""
        evse_status = ChargePointService.get_evse_status(
            db=db_session,
            charge_point_id=sample_charge_point.id,
            evse_id=999  # 不存在的EVSE
        )
        
        assert evse_status is None

