#
# 充电会话服务层
# 处理充电会话相关的业务逻辑
#

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database.models import (
    ChargingSession, EVSE, EVSEStatus, Order, Invoice, PricingSnapshot
)

logger = logging.getLogger("ocpp_csms")


class SessionService:
    """充电会话服务"""
    
    @staticmethod
    def start_session(
        db: Session,
        charge_point_id: str,
        evse_id: int,
        transaction_id: int,
        id_tag: str,
        user_id: Optional[str] = None,
        meter_start: int = 0
    ) -> ChargingSession:
        """开始充电会话"""
        # 获取EVSE
        evse = db.query(EVSE).filter(
            EVSE.charge_point_id == charge_point_id,
            EVSE.evse_id == evse_id
        ).first()
        
        if not evse:
            raise ValueError(f"EVSE not found: charge_point_id={charge_point_id}, evse_id={evse_id}")
        
        # 创建会话
        session = ChargingSession(
            evse_id=evse.id,
            charge_point_id=charge_point_id,
            transaction_id=transaction_id,
            id_tag=id_tag,
            user_id=user_id,
            start_time=datetime.now(timezone.utc),
            meter_start=meter_start,
            status="ongoing"
        )
        db.add(session)
        db.flush()
        
        # 更新EVSE状态
        evse_status = db.query(EVSEStatus).filter(
            EVSEStatus.evse_id == evse.id
        ).first()
        
        if evse_status:
            evse_status.status = "Charging"
            evse_status.current_session_id = session.id
            evse_status.last_seen = datetime.now(timezone.utc)
        
        db.commit()
        logger.info(f"充电会话开始: session_id={session.id}, transaction_id={transaction_id}")
        return session
    
    @staticmethod
    def stop_session(
        db: Session,
        charge_point_id: str,
        transaction_id: int,
        meter_stop: Optional[int] = None
    ) -> Optional[ChargingSession]:
        """停止充电会话"""
        session = db.query(ChargingSession).filter(
            ChargingSession.charge_point_id == charge_point_id,
            ChargingSession.transaction_id == transaction_id,
            ChargingSession.status == "ongoing"
        ).first()
        
        if not session:
            logger.warning(f"未找到进行中的会话: charge_point_id={charge_point_id}, transaction_id={transaction_id}")
            return None
        
        # 更新会话
        session.end_time = datetime.now(timezone.utc)
        session.meter_stop = meter_stop
        session.status = "completed"
        session.updated_at = datetime.now(timezone.utc)
        
        # 更新EVSE状态
        evse_status = db.query(EVSEStatus).filter(
            EVSEStatus.current_session_id == session.id
        ).first()
        
        if evse_status:
            evse_status.status = "Available"
            evse_status.current_session_id = None
            evse_status.last_seen = datetime.now(timezone.utc)
        
        db.commit()
        logger.info(f"充电会话结束: session_id={session.id}, transaction_id={transaction_id}")
        return session
    
    @staticmethod
    def get_active_session(
        db: Session,
        charge_point_id: str,
        evse_id: Optional[int] = None
    ) -> Optional[ChargingSession]:
        """获取当前活跃的会话"""
        if evse_id:
            evse = db.query(EVSE).filter(
                EVSE.charge_point_id == charge_point_id,
                EVSE.evse_id == evse_id
            ).first()
            
            if evse and evse.evse_status and evse.evse_status.current_session_id:
                return db.query(ChargingSession).filter(
                    ChargingSession.id == evse.evse_status.current_session_id
                ).first()
        
        # 如果没有指定evse_id，查找该充电桩的任意活跃会话
        return db.query(ChargingSession).filter(
            ChargingSession.charge_point_id == charge_point_id,
            ChargingSession.status == "ongoing"
        ).first()
    
    @staticmethod
    def add_meter_value(
        db: Session,
        session_id: int,
        value: int,
        connector_id: Optional[int] = None,
        sampled_value: Optional[Dict[str, Any]] = None
    ) -> None:
        """添加计量值"""
        from app.database.models import MeterValue
        
        meter_value = MeterValue(
            session_id=session_id,
            connector_id=connector_id,
            timestamp=datetime.now(timezone.utc),
            value=value,
            sampled_value=sampled_value
        )
        db.add(meter_value)
        db.commit()
