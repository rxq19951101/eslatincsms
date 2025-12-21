#
# 充电桩服务层
# 处理充电桩相关的业务逻辑，使用新的表结构
#

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database.models import (
    Site, ChargePoint, EVSE, EVSEStatus, Device,
    ChargingSession, DeviceEvent
)
from app.core.id_generator import generate_site_id, generate_charge_point_id

logger = logging.getLogger("ocpp_csms")


class ChargePointService:
    """充电桩服务"""
    
    @staticmethod
    def get_or_create_charge_point(
        db: Session,
        charge_point_id: str,
        device_serial_number: Optional[str] = None,
        vendor: Optional[str] = None,
        model: Optional[str] = None,
        serial_number: Optional[str] = None,
        firmware_version: Optional[str] = None
    ) -> ChargePoint:
        """获取或创建充电桩"""
        charge_point = db.query(ChargePoint).filter(
            ChargePoint.id == charge_point_id
        ).first()
        
        if not charge_point:
            # 创建默认站点（如果不存在）
            default_site = db.query(Site).filter(Site.id == "default_site").first()
            if not default_site:
                default_site = Site(
                    id="default_site",
                    name="默认站点",
                    address="未设置",
                    latitude=0.0,
                    longitude=0.0
                )
                db.add(default_site)
                db.flush()
            
            # 如果charge_point_id未提供，生成新的唯一ID
            if not charge_point_id:
                charge_point_id = generate_charge_point_id(serial_number=serial_number, vendor=vendor)
            # 如果charge_point_id已存在，生成新的唯一ID
            elif db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first():
                charge_point_id = generate_charge_point_id(serial_number=serial_number, vendor=vendor)
            
            # 创建充电桩
            charge_point = ChargePoint(
                id=charge_point_id,
                site_id=default_site.id,
                vendor=vendor,
                model=model,
                serial_number=serial_number,
                firmware_version=firmware_version,
                device_serial_number=device_serial_number
            )
            db.add(charge_point)
            db.flush()
            
            # 创建默认EVSE（如果不存在）
            evse = db.query(EVSE).filter(
                EVSE.charge_point_id == charge_point_id,
                EVSE.evse_id == 1
            ).first()
            
            if not evse:
                evse = EVSE(
                    charge_point_id=charge_point_id,
                    evse_id=1
                )
                db.add(evse)
                db.flush()
                
                # 创建EVSE状态
                evse_status = EVSEStatus(
                    evse_id=evse.id,
                    charge_point_id=charge_point_id,
                    status="Unknown",
                    last_seen=datetime.now(timezone.utc)
                )
                db.add(evse_status)
            
            logger.info(f"创建新充电桩: {charge_point_id}")
        else:
            # 更新信息
            if vendor:
                charge_point.vendor = vendor
            if model:
                charge_point.model = model
            if serial_number:
                charge_point.serial_number = serial_number
            if firmware_version:
                charge_point.firmware_version = firmware_version
            if device_serial_number:
                charge_point.device_serial_number = device_serial_number
        
        db.commit()
        return charge_point
    
    @staticmethod
    def update_charge_point_info(
        db: Session,
        charge_point_id: str,
        vendor: Optional[str] = None,
        model: Optional[str] = None,
        firmware_version: Optional[str] = None
    ) -> Optional[ChargePoint]:
        """更新充电桩信息"""
        charge_point = db.query(ChargePoint).filter(
            ChargePoint.id == charge_point_id
        ).first()
        
        if charge_point:
            if vendor:
                charge_point.vendor = vendor
            if model:
                charge_point.model = model
            if firmware_version:
                charge_point.firmware_version = firmware_version
            charge_point.updated_at = datetime.now(timezone.utc)
            db.commit()
        
        return charge_point
    
    @staticmethod
    def get_evse_status(
        db: Session,
        charge_point_id: str,
        evse_id: int = 1
    ) -> Optional[EVSEStatus]:
        """获取EVSE状态"""
        evse = db.query(EVSE).filter(
            EVSE.charge_point_id == charge_point_id,
            EVSE.evse_id == evse_id
        ).first()
        
        if evse and evse.evse_status:
            return evse.evse_status
        
        return None
    
    @staticmethod
    def update_evse_status(
        db: Session,
        charge_point_id: str,
        evse_id: int,
        status: str,
        previous_status: Optional[str] = None
    ) -> EVSEStatus:
        """更新EVSE状态"""
        evse = db.query(EVSE).filter(
            EVSE.charge_point_id == charge_point_id,
            EVSE.evse_id == evse_id
        ).first()
        
        if not evse:
            # 创建EVSE
            evse = EVSE(
                charge_point_id=charge_point_id,
                evse_id=evse_id
            )
            db.add(evse)
            db.flush()
        
        # 获取或创建状态
        evse_status = db.query(EVSEStatus).filter(
            EVSEStatus.evse_id == evse.id
        ).first()
        
        if not evse_status:
            evse_status = EVSEStatus(
                evse_id=evse.id,
                charge_point_id=charge_point_id,
                status=status,
                last_seen=datetime.now(timezone.utc)
            )
            db.add(evse_status)
        else:
            if previous_status is None:
                previous_status = evse_status.status
            evse_status.status = status
            evse_status.last_seen = datetime.now(timezone.utc)
            evse_status.updated_at = datetime.now(timezone.utc)
        
        # 记录状态变化事件
        if previous_status and previous_status != status:
            event = DeviceEvent(
                charge_point_id=charge_point_id,
                evse_id=evse.id,
                event_type="status_change",
                status=status,
                previous_status=previous_status,
                timestamp=datetime.now(timezone.utc)
            )
            db.add(event)
        
        db.commit()
        return evse_status
    
    @staticmethod
    def record_heartbeat(
        db: Session,
        charge_point_id: str,
        device_serial_number: Optional[str] = None
    ) -> None:
        """记录心跳事件"""
        event = DeviceEvent(
            device_serial_number=device_serial_number,
            charge_point_id=charge_point_id,
            event_type="heartbeat",
            timestamp=datetime.now(timezone.utc)
        )
        db.add(event)
        
        # 更新EVSE状态的最后在线时间
        evse_statuses = db.query(EVSEStatus).filter(
            EVSEStatus.charge_point_id == charge_point_id
        ).all()
        
        for evse_status in evse_statuses:
            evse_status.last_seen = datetime.now(timezone.utc)
        
        db.commit()
    
    @staticmethod
    def get_charge_point_by_device_serial(
        db: Session,
        device_serial_number: str
    ) -> Optional[ChargePoint]:
        """根据设备SN号获取充电桩"""
        return db.query(ChargePoint).filter(
            ChargePoint.device_serial_number == device_serial_number
        ).first()
