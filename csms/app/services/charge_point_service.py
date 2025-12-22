#
# 充电桩服务层
# 处理充电桩相关的业务逻辑，使用新的表结构
#

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database.models import (
    Site, ChargePoint, EVSE, EVSEStatus, Device, DeviceType,
    ChargingSession, DeviceEvent, DeviceConfig, ChargePointConfig
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
            # 如果提供了device_serial_number，验证设备是否存在
            # 注意：不再自动创建设备，设备必须先通过认证才能使用
            if device_serial_number:
                device = db.query(Device).filter(
                    Device.serial_number == device_serial_number
                ).first()
                if not device:
                    logger.warning(
                        f"设备 {device_serial_number} 不存在，"
                        f"充电桩将不关联设备（charge_point_id={charge_point_id}）。"
                        f"设备必须先通过认证。"
                    )
                    device_serial_number = None
                elif not device.is_active:
                    logger.warning(
                        f"设备 {device_serial_number} 未激活，"
                        f"充电桩将不关联设备（charge_point_id={charge_point_id}）"
                    )
                    device_serial_number = None
            
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
            
            # 创建默认充电桩配置
            ChargePointService.get_or_create_charge_point_config(db, charge_point_id)
            
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
        # 如果提供了device_serial_number，检查设备是否存在
        # 如果不存在，设为None以避免外键约束错误
        if device_serial_number:
            device = db.query(Device).filter(
                Device.serial_number == device_serial_number
            ).first()
            if not device:
                logger.warning(
                    f"设备 {device_serial_number} 不存在于devices表中，"
                    f"heartbeat事件将不关联设备（charge_point_id={charge_point_id}）"
                )
                device_serial_number = None
        
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
    
    @staticmethod
    def get_or_create_device_type(
        db: Session,
        vendor: Optional[str] = None
    ) -> DeviceType:
        """获取或创建设备类型
        根据vendor推断type_code，如果不存在则创建默认类型
        """
        # 根据vendor推断type_code（简单映射，可以根据实际情况扩展）
        type_code_map = {
            "zcf": "zcf",
            "中车": "zcf",
            "tesla": "tesla",
            "abb": "abb",
            "schneider": "schneider",
        }
        
        # 尝试从vendor推断type_code
        type_code = None
        if vendor:
            vendor_lower = vendor.lower().strip()
            for key, code in type_code_map.items():
                if key in vendor_lower:
                    type_code = code
                    break
        
        # 如果没有匹配到，使用默认类型
        if not type_code:
            type_code = "default"
        
        # 查找或创建设备类型
        device_type = db.query(DeviceType).filter(
            DeviceType.type_code == type_code
        ).first()
        
        if not device_type:
            # 创建默认设备类型（使用测试密钥，生产环境应该使用强随机密钥）
            try:
                from app.core.crypto import encrypt_master_secret
                default_master_secret = "default_master_secret_12345678901234567890"
                encrypted_secret = encrypt_master_secret(default_master_secret)
            except ImportError:
                # 如果加密模块不可用，使用简单的哈希（仅用于开发环境）
                import hashlib
                default_master_secret = "default_master_secret_12345678901234567890"
                encrypted_secret = hashlib.sha256(default_master_secret.encode()).hexdigest()
                logger.warning("加密模块不可用，使用简单哈希（仅用于开发环境）")
            
            device_type = DeviceType(
                type_code=type_code,
                type_name=vendor or "默认设备类型",
                master_secret_encrypted=encrypted_secret,
                encryption_algorithm="AES-256-GCM"
            )
            db.add(device_type)
            db.flush()
            logger.info(f"创建新设备类型: {type_code}")
        
        return device_type
    
    @staticmethod
    def get_or_create_device(
        db: Session,
        device_serial_number: str,
        vendor: Optional[str] = None
    ) -> Optional[Device]:
        """获取或创建设备
        如果device_serial_number无效（长度不是15位），返回None
        """
        if not device_serial_number or len(device_serial_number) != 15:
            logger.warning(f"设备序列号无效: {device_serial_number}（必须是15位）")
            return None
        
        # 查找设备
        device = db.query(Device).filter(
            Device.serial_number == device_serial_number
        ).first()
        
        if not device:
            # 获取或创建设备类型
            device_type = ChargePointService.get_or_create_device_type(db, vendor)
            
            # 生成MQTT信息
            mqtt_client_id = f"{device_type.type_code}&{device_serial_number}"
            mqtt_username = device_serial_number
            
            # 创建设备
            device = Device(
                serial_number=device_serial_number,
                device_type_id=device_type.id,
                mqtt_client_id=mqtt_client_id,
                mqtt_username=mqtt_username,
                is_active=True,
                last_connected=datetime.now(timezone.utc)
            )
            db.add(device)
            db.flush()
            
            # 创建默认设备配置
            default_configs = [
                ("heartbeat_interval", "30", "int"),
                ("ocpp_version", "1.6J", "string"),
                ("connection_timeout", "60", "int"),
            ]
            
            for config_key, config_value, value_type in default_configs:
                config = DeviceConfig(
                    device_serial_number=device_serial_number,
                    config_key=config_key,
                    config_value=config_value,
                    value_type=value_type
                )
                db.add(config)
            
            db.flush()
            logger.info(f"创建新设备: {device_serial_number} (type: {device_type.type_code})")
        
        return device
    
    @staticmethod
    def get_or_create_charge_point_config(
        db: Session,
        charge_point_id: str
    ) -> None:
        """获取或创建充电桩默认配置"""
        # 检查是否已有配置
        existing_config = db.query(ChargePointConfig).filter(
            ChargePointConfig.charge_point_id == charge_point_id
        ).first()
        
        if existing_config:
            return
        
        # 创建默认配置
        default_configs = [
            ("max_power_kw", "22", "float"),
            ("is_public", "true", "bool"),
            ("requires_auth", "true", "bool"),
        ]
        
        for config_key, config_value, value_type in default_configs:
            config = ChargePointConfig(
                charge_point_id=charge_point_id,
                config_key=config_key,
                config_value=config_value,
                value_type=value_type
            )
            db.add(config)
        
        db.flush()
        logger.debug(f"创建充电桩默认配置: {charge_point_id}")

