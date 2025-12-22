"""
数据库查询测试
验证数据库查询使用正确的列名
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database.models import (
    ChargePoint, ChargingSession, MeterValue, DeviceEvent, EVSE, Site
)


class TestDatabaseQueries:
    """数据库查询测试"""
    
    def test_meter_values_column_name(self, db_session: Session, sample_charge_point, sample_evse):
        """验证meter_values表使用正确的列名session_id"""
        # 先创建一个会话和计量值，然后通过ORM验证列名
        from app.database.models import ChargingSession, MeterValue
        from datetime import datetime, timezone
        
        session = ChargingSession(
            charge_point_id=sample_charge_point.id,
            evse_id=sample_evse.id,
            transaction_id=9999,
            id_tag="TEST",
            start_time=datetime.now(timezone.utc)
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        
        # 创建计量值，使用session_id（正确的列名）
        meter = MeterValue(
            session_id=session.id,  # 使用正确的列名
            value=100,
            timestamp=datetime.now(timezone.utc)
        )
        db_session.add(meter)
        db_session.commit()
        
        # 验证可以通过session_id查询
        found = db_session.query(MeterValue).filter(
            MeterValue.session_id == session.id
        ).first()
        
        assert found is not None
        assert found.session_id == session.id
        # 验证charging_session_id不存在（如果使用会报错）
        # 通过ORM访问，如果列名错误会直接报错
    
    def test_meter_values_foreign_key(self, db_session: Session, sample_charge_point, sample_evse):
        """验证meter_values的外键关系"""
        from app.database.models import ChargingSession, MeterValue
        from datetime import datetime, timezone
        
        # 创建会话
        session = ChargingSession(
            charge_point_id=sample_charge_point.id,
            evse_id=sample_evse.id,
            transaction_id=8888,
            id_tag="FK_TEST",
            start_time=datetime.now(timezone.utc)
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        
        # 创建计量值
        meter = MeterValue(
            session_id=session.id,  # 外键指向charging_sessions.id
            value=200,
            timestamp=datetime.now(timezone.utc)
        )
        db_session.add(meter)
        db_session.commit()
        
        # 验证外键关系：可以通过关系访问
        db_session.refresh(session)
        assert len(session.meter_values) == 1
        assert session.meter_values[0].session_id == session.id
        
        # 验证外键约束：删除会话时，计量值应该被级联删除（如果设置了cascade）
        # 或者验证通过session_id可以访问session
        assert meter.session.id == session.id
    
    def test_query_meter_values_by_session_id(
        self,
        db_session: Session,
        sample_charge_point: ChargePoint,
        sample_evse: EVSE
    ):
        """测试使用session_id查询计量值"""
        # 创建充电会话
        session = ChargingSession(
            charge_point_id=sample_charge_point.id,
            evse_id=sample_evse.id,
            transaction_id=3001,
            id_tag="QUERY_TEST",
            meter_start=0,
            start_time=datetime.now(timezone.utc)
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        session_id = session.id
        
        # 添加计量值
        from app.services.session_service import SessionService
        for value in [10, 20, 30]:
            SessionService.add_meter_value(
                db=db_session,
                session_id=session_id,  # 使用正确的列名
                value=value,
                connector_id=1
            )
        
        # 使用正确的列名查询
        meters = db_session.query(MeterValue).filter(
            MeterValue.session_id == session_id  # 正确的列名
        ).all()
        
        assert len(meters) == 3
        
        # 验证每个计量值都有正确的session_id
        for meter in meters:
            assert meter.session_id == session_id
            assert meter.session.id == session_id  # 通过关系访问
    
    def test_query_meter_values_by_transaction_id(
        self,
        db_session: Session,
        sample_charge_point: ChargePoint,
        sample_evse: EVSE
    ):
        """测试通过transaction_id查询计量值"""
        transaction_id = 4001
        
        # 创建充电会话
        session = ChargingSession(
            charge_point_id=sample_charge_point.id,
            evse_id=sample_evse.id,
            transaction_id=transaction_id,
            id_tag="TRANSACTION_TEST",
            meter_start=0,
            start_time=datetime.now(timezone.utc)
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        
        # 添加计量值
        from app.services.session_service import SessionService
        for value in [50, 100, 150]:
            SessionService.add_meter_value(
                db=db_session,
                session_id=session.id,  # 使用正确的列名
                value=value,
                connector_id=1
            )
        
        # 通过transaction_id查询计量值（使用JOIN）
        meters = db_session.query(MeterValue).join(ChargingSession).filter(
            ChargingSession.transaction_id == transaction_id
        ).all()
        
        assert len(meters) == 3
        
        # 验证所有计量值都关联到正确的会话
        for meter in meters:
            assert meter.session_id == session.id
            assert meter.session.transaction_id == transaction_id
    
    def test_meter_values_relationship(self, db_session: Session):
        """测试MeterValue和ChargingSession的关系"""
        # 创建充电会话
        from app.database.models import Site, EVSE, ChargePoint
        
        site = Site(
            id="test_site_query",
            name="Test Site",
            address="Test Address",
            latitude=0.0,
            longitude=0.0
        )
        db_session.add(site)
        
        cp = ChargePoint(
            id="CP-QUERY-001",
            site_id=site.id,
            vendor="Test",
            model="Test",
            is_active=True
        )
        db_session.add(cp)
        
        evse = EVSE(
            charge_point_id=cp.id,
            evse_id=1,
            connector_type="Type2"
        )
        db_session.add(evse)
        db_session.commit()
        db_session.refresh(evse)
        
        session = ChargingSession(
            charge_point_id=cp.id,
            evse_id=evse.id,
            transaction_id=5001,
            id_tag="RELATIONSHIP_TEST",
            meter_start=0,
            start_time=datetime.now(timezone.utc)
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        
        # 添加计量值
        from app.services.session_service import SessionService
        SessionService.add_meter_value(
            db=db_session,
            session_id=session.id,  # 使用正确的列名
            value=100,
            connector_id=1
        )
        
        # 通过关系访问计量值
        db_session.refresh(session)
        assert len(session.meter_values) == 1
        assert session.meter_values[0].value == 100
        assert session.meter_values[0].session_id == session.id  # 正确的列名

