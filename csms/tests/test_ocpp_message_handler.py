"""
OCPP消息处理器单元测试
"""
import pytest
from datetime import datetime, timezone
from app.services.ocpp_message_handler import OCPPMessageHandler
from app.database.models import ChargePoint, Device, DeviceEvent


class TestOCPPMessageHandler:
    """OCPP消息处理器测试类"""
    
    @pytest.fixture
    def handler(self):
        """创建消息处理器实例"""
        return OCPPMessageHandler()
    
    @pytest.mark.asyncio
    async def test_handle_boot_notification_new(self, handler: OCPPMessageHandler, db_session, sample_site, sample_device):
        """测试处理BootNotification（新设备）"""
        payload = {
            "chargePointVendor": "测试厂商",
            "chargePointModel": "测试型号",
            "firmwareVersion": "1.0.0",
            "chargePointSerialNumber": sample_device.serial_number
        }
        
        response = await handler.handle_boot_notification(
            charge_point_id="CP-BOOT-001",
            payload=payload,
            device_serial_number=sample_device.serial_number,
            db=db_session
        )
        
        assert response["status"] == "Accepted"
        assert "currentTime" in response
        assert "interval" in response
        
        # 检查是否创建了ChargePoint
        charge_point = db_session.query(ChargePoint).filter(
            ChargePoint.id == "CP-BOOT-001"
        ).first()
        assert charge_point is not None
        assert charge_point.vendor == "测试厂商"
    
    @pytest.mark.asyncio
    async def test_handle_boot_notification_existing(self, handler: OCPPMessageHandler, db_session, sample_charge_point):
        """测试处理BootNotification（已存在设备）"""
        payload = {
            "chargePointVendor": "更新厂商",
            "chargePointModel": "更新型号",
            "firmwareVersion": "2.0.0"
        }
        
        response = await handler.handle_boot_notification(
            charge_point_id=sample_charge_point.id,
            payload=payload,
            db=db_session
        )
        
        assert response["status"] == "Accepted"
        
        # 检查ChargePoint是否更新
        db_session.refresh(sample_charge_point)
        assert sample_charge_point.vendor == "更新厂商"
        assert sample_charge_point.model == "更新型号"
    
    @pytest.mark.asyncio
    async def test_handle_heartbeat(self, handler: OCPPMessageHandler, db_session, sample_charge_point, sample_device):
        """测试处理Heartbeat"""
        response = await handler.handle_heartbeat(
            charge_point_id=sample_charge_point.id,
            payload={},
            device_serial_number=sample_device.serial_number,
            db=db_session
        )
        
        assert "currentTime" in response
        
        # 检查是否创建了DeviceEvent
        event = db_session.query(DeviceEvent).filter(
            DeviceEvent.charge_point_id == sample_charge_point.id,
            DeviceEvent.event_type == "heartbeat"
        ).first()
        assert event is not None
    
    @pytest.mark.asyncio
    async def test_handle_status_notification_new(self, handler: OCPPMessageHandler, db_session, sample_charge_point):
        """测试处理StatusNotification（新建EVSE状态）"""
        payload = {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": "Available"
        }
        
        response = await handler.handle_status_notification(
            charge_point_id=sample_charge_point.id,
            payload=payload,
            evse_id=1,
            db=db_session
        )
        
        # StatusNotification通常不返回响应
        assert response == {}
        
        # 检查是否创建了EVSEStatus
        from app.database.models import EVSEStatus
        evse_status = db_session.query(EVSEStatus).filter(
            EVSEStatus.charge_point_id == sample_charge_point.id,
            EVSEStatus.evse_id == 1
        ).first()
        assert evse_status is not None
        assert evse_status.status == "Available"
    
    @pytest.mark.asyncio
    async def test_handle_status_notification_invalid_charge_point(self, handler: OCPPMessageHandler, db_session):
        """测试处理StatusNotification（无效充电桩）"""
        payload = {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": "Available"
        }
        
        # 应该返回空响应，不抛出异常
        response = await handler.handle_status_notification(
            charge_point_id="CP-INVALID",
            payload=payload,
            evse_id=1,
            db=db_session
        )
        
        assert response == {}
    
    @pytest.mark.asyncio
    async def test_handle_start_transaction(self, handler: OCPPMessageHandler, db_session, sample_charge_point, sample_evse):
        """测试处理StartTransaction"""
        payload = {
            "connectorId": 1,
            "idTag": "TEST_USER_001",
            "meterStart": 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        response = await handler.handle_start_transaction(
            charge_point_id=sample_charge_point.id,
            payload=payload,
            evse_id=1,
            db=db_session
        )
        
        assert "transactionId" in response
        assert response["idTagInfo"]["status"] in ["Accepted", "Blocked", "Invalid"]
        
        # 检查是否创建了ChargingSession
        from app.database.models import ChargingSession
        session = db_session.query(ChargingSession).filter(
            ChargingSession.charge_point_id == sample_charge_point.id,
            ChargingSession.transaction_id == response["transactionId"]
        ).first()
        assert session is not None
    
    @pytest.mark.asyncio
    async def test_handle_stop_transaction(self, handler: OCPPMessageHandler, db_session, sample_charge_point):
        """测试处理StopTransaction"""
        # 先创建一个会话
        from app.database.models import ChargingSession, EVSE
        evse = db_session.query(EVSE).filter(
            EVSE.charge_point_id == sample_charge_point.id
        ).first()
        
        if not evse:
            evse = EVSE(
                charge_point_id=sample_charge_point.id,
                evse_id=1
            )
            db_session.add(evse)
            db_session.commit()
        
        session = ChargingSession(
            charge_point_id=sample_charge_point.id,
            evse_id=evse.id,
            transaction_id=12345,
            id_tag="TEST_USER_001",
            start_time=datetime.now(timezone.utc),
            status="ongoing"
        )
        db_session.add(session)
        db_session.commit()
        
        payload = {
            "transactionId": 12345,
            "meterStop": 1000,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": "Local"
        }
        
        response = await handler.handle_stop_transaction(
            charge_point_id=sample_charge_point.id,
            payload=payload,
            db=db_session
        )
        
        assert "idTagInfo" in response
        
        # 检查会话是否更新
        db_session.refresh(session)
        assert session.status == "completed"
        assert session.end_time is not None

