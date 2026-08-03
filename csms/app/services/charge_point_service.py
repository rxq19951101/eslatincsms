#
# 充电桩服务层
# 处理充电桩相关的业务逻辑，使用新的表结构
#

import logging
import os
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.database.models import (
    Site, ChargePoint, EVSE, EVSEStatus, Device,
    ChargingSession, DeviceEvent, DeviceConfig, ChargePointConfig, Tenant
)
from app.core.id_generator import generate_site_id, generate_charge_point_id
from app.core.config import get_settings
from app.database.base import tenant_id_context

logger = logging.getLogger("ocpp_csms")


class ChargePointService:
    """充电桩服务"""

    @staticmethod
    def resolve_auto_registration_tenant(db: Session):
        """Resolve the tenant for development-only OCPP auto-registration.

        A new WebSocket has no HTTP tenant context. Auto-registration is therefore
        allowed only with an explicit OCPP_DEFAULT_TENANT_ID or when the local
        database contains exactly one active tenant. Ambiguous multi-tenant
        environments fail closed instead of assigning a charger to the wrong
        tenant.
        """
        tenant_id = tenant_id_context.get()
        if tenant_id:
            return tenant_id

        configured_id = os.getenv("OCPP_DEFAULT_TENANT_ID", "").strip()
        if configured_id:
            tenant = db.query(Tenant).filter(
                Tenant.id == configured_id,
                Tenant.status == "active",
            ).first()
            if not tenant:
                raise ValueError("OCPP_DEFAULT_TENANT_ID does not reference an active tenant")
            return tenant.id

        if os.getenv("OCPP_WS_REQUIRE_PRE_REGISTERED", "true").lower() not in {"true", "1", "yes"}:
            active_tenants = db.query(Tenant).filter(Tenant.status == "active").all()
            if len(active_tenants) == 1:
                return active_tenants[0].id
            if len(active_tenants) > 1:
                raise ValueError(
                    "OCPP auto-registration requires OCPP_DEFAULT_TENANT_ID when multiple active tenants exist"
                )

        raise ValueError(
            "No tenant context for charger registration; pre-register the charger or configure OCPP_DEFAULT_TENANT_ID"
        )
    
    @staticmethod
    def get_or_create_charge_point(
        db: Session,
        charge_point_id: str,
        device_serial_number: Optional[str] = None,
        vendor: Optional[str] = None,
        model: Optional[str] = None,
        serial_number: Optional[str] = None,
        firmware_version: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
    ) -> ChargePoint:
        """Resolve/create by OCPP identity while keeping UUID relations internal."""
        charge_point = db.query(ChargePoint).filter(
            ChargePoint.ocpp_identity == charge_point_id
        ).first()

        if charge_point and tenant_id and charge_point.tenant_id != tenant_id:
            raise ValueError("Charge point belongs to another tenant")

        if not charge_point:
            tenant_id = tenant_id or ChargePointService.resolve_auto_registration_tenant(db)
            device = None
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
                    device = None
                elif device.tenant_id != tenant_id:
                    raise ValueError("Device belongs to another tenant")
            
            # 创建默认站点（如果不存在）
            # 优先查找 "default_site"（向后兼容），如果不存在则创建新的唯一站点
            default_site = db.query(Site).filter(
                Site.site_code == "default_site",
                Site.tenant_id == tenant_id,
            ).first()
            if not default_site:
                # 尝试查找是否有其他默认站点
                default_site = db.query(Site).filter(
                    Site.name == "默认站点",
                    Site.tenant_id == tenant_id,
                ).first()
                if not default_site:
                    # 生成唯一的站点ID
                    site_id = generate_site_id("默认站点")
                    # 确保站点ID唯一（如果冲突则重新生成）
                    max_retries = 10
                    retry_count = 0
                    while db.query(Site).filter(Site.site_code == site_id).first() and retry_count < max_retries:
                        site_id = generate_site_id("默认站点")
                        retry_count += 1
                    if retry_count >= max_retries:
                        # 如果多次重试仍然冲突，使用UUID
                        from app.core.id_generator import generate_uuid
                        site_id = f"site_{generate_uuid()[:16]}"
                        logger.warning(f"站点ID生成冲突，使用UUID: {site_id}")
                    default_site = Site(
                        site_code=site_id,
                        tenant_id=tenant_id,
                        name="默认站点",
                        address="地址未配置",
                        latitude=0.000001,
                        longitude=0.000001
                    )
                    db.add(default_site)
                    db.flush()
                    logger.info(f"创建新站点: {site_id} (默认站点)")
            
            # 检查序列号冲突
            if serial_number:
                existing_cp = db.query(ChargePoint).filter(
                    ChargePoint.serial_number == serial_number
                ).first()
                if existing_cp:
                    logger.warning(
                        f"序列号 {serial_number} 已被充电桩 {existing_cp.id} 使用，"
                        f"将生成新的充电桩ID以避免冲突"
                    )
                    # 如果序列号冲突，生成新的唯一ID
                    charge_point_id = None
            
            # 如果charge_point_id未提供，生成新的唯一ID
            if not charge_point_id:
                charge_point_id = generate_charge_point_id(serial_number=serial_number, vendor=vendor)
                # 确保ID唯一（如果冲突则重新生成）
                max_retries = 10
                retry_count = 0
                while db.query(ChargePoint).filter(ChargePoint.ocpp_identity == charge_point_id).first() and retry_count < max_retries:
                    charge_point_id = generate_charge_point_id(serial_number=serial_number, vendor=vendor)
                    retry_count += 1
                if retry_count >= max_retries:
                    # 如果多次重试仍然冲突，使用UUID
                    from app.core.id_generator import generate_uuid
                    charge_point_id = f"cp_{generate_uuid()[:16]}"
                    logger.warning(f"充电桩ID生成冲突，使用UUID: {charge_point_id}")
            # 如果charge_point_id已存在，生成新的唯一ID
            elif db.query(ChargePoint).filter(ChargePoint.ocpp_identity == charge_point_id).first():
                logger.warning(f"充电桩ID {charge_point_id} 已存在，生成新的唯一ID")
                charge_point_id = generate_charge_point_id(serial_number=serial_number, vendor=vendor)
                # 确保新ID唯一
                max_retries = 10
                retry_count = 0
                while db.query(ChargePoint).filter(ChargePoint.ocpp_identity == charge_point_id).first() and retry_count < max_retries:
                    charge_point_id = generate_charge_point_id(serial_number=serial_number, vendor=vendor)
                    retry_count += 1
                if retry_count >= max_retries:
                    from app.core.id_generator import generate_uuid
                    charge_point_id = f"cp_{generate_uuid()[:16]}"
                    logger.warning(f"充电桩ID生成冲突，使用UUID: {charge_point_id}")
            
            # 创建充电桩（需要tenant_id，但这个方法没有tenant_id参数）
            # 注意：这个方法需要更新以支持tenant_id，暂时使用默认值或从上下文获取
            # 这里暂时不设置tenant_id，需要在调用时确保已设置
            charge_point = ChargePoint(
                ocpp_identity=charge_point_id,
                tenant_id=tenant_id,
                site_id=default_site.id,
                vendor=vendor,
                model=model,
                serial_number=serial_number,
                firmware_version=firmware_version,
                device_id=device.id if device else None,
                device_serial_number=device_serial_number,
                # tenant_id 需要在调用时设置
            )
            db.add(charge_point)
            db.flush()
            
            # 创建默认充电桩配置
            ChargePointService.get_or_create_charge_point_config(db, charge_point.id)
            
            # 创建默认EVSE（如果不存在）
            evse = db.query(EVSE).filter(
                EVSE.charge_point_id == charge_point.id,
                EVSE.evse_id == 1
            ).first()
            
            if not evse:
                # 注意：EVSE需要tenant_id，但这里暂时不设置（需要在调用时确保已设置）
                evse = EVSE(
                    tenant_id=tenant_id,
                    charge_point_id=charge_point.id,
                    evse_id=1,
                    connector_type="Type2"  # 默认连接器类型
                    # tenant_id 需要在调用时设置
                )
                db.add(evse)
                db.flush()
                
                # 创建EVSE状态
                evse_status = EVSEStatus(
                    tenant_id=tenant_id,
                    evse_id=evse.id,
                    charge_point_id=charge_point.id,
                    status="Unknown",
                    last_seen=datetime.now(timezone.utc)
                    # tenant_id 需要在调用时设置
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
                # 验证设备是否存在（更新时也要验证外键约束）
                device = db.query(Device).filter(
                    Device.serial_number == device_serial_number
                ).first()
                if device and device.is_active:
                    if device.tenant_id != charge_point.tenant_id:
                        raise ValueError("Device belongs to another tenant")
                    charge_point.device_id = device.id
                    charge_point.device_serial_number = device_serial_number
                else:
                    # 设备不存在或未激活，不设置device_serial_number（保持原值或设为None）
                    if device_serial_number:
                        logger.warning(
                            f"更新充电桩 {charge_point_id} 时，设备 {device_serial_number} 不存在或未激活，"
                            f"不更新device_serial_number字段"
                        )
                    charge_point.device_serial_number = None
        
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
            ChargePoint.ocpp_identity == charge_point_id
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
        charge_point = db.query(ChargePoint).filter(
            ChargePoint.ocpp_identity == charge_point_id
        ).first()
        if not charge_point:
            return None
        evse = db.query(EVSE).filter(
            EVSE.charge_point_id == charge_point.id,
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
        # 首先检查ChargePoint是否存在
        charge_point = db.query(ChargePoint).filter(
            ChargePoint.ocpp_identity == charge_point_id
        ).first()
        
        if not charge_point:
            raise ValueError(f"ChargePoint {charge_point_id} 不存在，无法更新EVSE状态")
        
        evse = db.query(EVSE).filter(
            EVSE.charge_point_id == charge_point.id,
            EVSE.evse_id == evse_id
        ).first()
        
        if not evse:
            # 创建EVSE（需要tenant_id，但这个方法没有tenant_id参数）
            # 注意：需要在调用时确保tenant_id已设置
            evse = EVSE(
                tenant_id=charge_point.tenant_id,
                charge_point_id=charge_point.id,
                evse_id=evse_id,
                connector_type="Type2"  # 默认连接器类型
                # tenant_id 需要在调用时设置
            )
            db.add(evse)
            db.flush()
        
        # 获取或创建状态
        evse_status = db.query(EVSEStatus).filter(
            EVSEStatus.evse_id == evse.id
        ).first()
        
        if not evse_status:
            evse_status = EVSEStatus(
                tenant_id=charge_point.tenant_id,
                evse_id=evse.id,
                charge_point_id=charge_point.id,
                status=status,
                last_seen=datetime.now(timezone.utc)
                # tenant_id 需要在调用时设置
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
            # 获取tenant_id（从charge_point）
            tenant_id = None
            if charge_point_id:
                cp = db.query(ChargePoint).filter(ChargePoint.ocpp_identity == charge_point_id).first()
                if cp:
                    tenant_id = cp.tenant_id
            
            event = DeviceEvent(
                tenant_id=tenant_id,
                charge_point_id=charge_point.id,
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
    ) -> bool:
        """限频持久化在线快照，不为正常心跳创建历史事件。"""
        cp = db.query(ChargePoint).filter(
            ChargePoint.ocpp_identity == charge_point_id
        ).first()
        if not cp:
            raise ValueError(f"ChargePoint {charge_point_id} 不存在，无法记录心跳")

        now = datetime.now(timezone.utc)
        persist_interval = max(
            1, get_settings().heartbeat_persist_interval_seconds
        )
        cutoff = now - timedelta(seconds=persist_interval)

        # 在线状态只需要分钟级持久化。过滤条件也避免加载无需更新的 EVSE。
        evse_statuses = db.query(EVSEStatus).filter(
            EVSEStatus.charge_point_id == cp.id,
            or_(
                EVSEStatus.last_seen.is_(None),
                EVSEStatus.last_seen < cutoff,
            ),
        ).all()

        if not evse_statuses:
            return False

        for evse_status in evse_statuses:
            evse_status.last_seen = now

        db.commit()
        return True
    
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
    def infer_type_code(vendor: Optional[str] = None) -> str:
        """根据vendor推断type_code"""
        # 根据vendor推断type_code（简单映射，可以根据实际情况扩展）
        type_code_map = {
            "zcf": "zcf",
            "中车": "zcf",
            "tesla": "tesla",
            "abb": "abb",
            "schneider": "schneider",
        }
        
        # 尝试从vendor推断type_code
        if vendor:
            vendor_lower = vendor.lower().strip()
            for key, code in type_code_map.items():
                if key in vendor_lower:
                    return code
        
        # 如果没有匹配到，使用默认类型
        return "default"
    
    @staticmethod
    def get_or_create_device(
        db: Session,
        device_serial_number: str,
        vendor: Optional[str] = None,
        type_code: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> Optional[Device]:
        """获取或创建设备
        
        注意：如果设备序列号已存在，会检查是否已被其他充电桩使用
        """
        if not device_serial_number or len(device_serial_number.strip()) == 0:
            logger.warning(f"设备序列号无效: {device_serial_number}（不能为空）")
            return None
        
        # 查找设备（按租户）
        query = db.query(Device).filter(Device.serial_number == device_serial_number)
        if tenant_id:
            query = query.filter(Device.tenant_id == tenant_id)
        
        device = query.first()
        
        if not device:
            # 推断设备类型代码（如果未提供）
            if not type_code:
                type_code = ChargePointService.infer_type_code(vendor)
            
            # 生成MQTT信息
            mqtt_client_id = f"{type_code}&{device_serial_number}"
            mqtt_username = device_serial_number
            
            # 为每个设备生成独立的master_secret（使用设备序列号作为种子）
            try:
                from app.core.crypto import encrypt_master_secret
                import secrets
                # 生成随机master_secret（生产环境应该使用强随机密钥）
                # 使用设备序列号作为种子的一部分，确保每个设备都有唯一的secret
                master_secret = secrets.token_urlsafe(32) + device_serial_number[:8]
                encrypted_secret = encrypt_master_secret(master_secret)
            except ImportError:
                # 如果加密模块不可用，使用简单的哈希（仅用于开发环境）
                import hashlib
                import secrets
                master_secret = f"device_secret_{device_serial_number}_{secrets.token_urlsafe(16)}"
                encrypted_secret = hashlib.sha256(master_secret.encode()).hexdigest()
                logger.warning("加密模块不可用，使用简单哈希（仅用于开发环境）")
            
            # 创建设备（每个设备独立存储master_secret）
            if not tenant_id:
                logger.error(f"创建设备 {device_serial_number} 时缺少 tenant_id")
                return None
            
            device = Device(
                serial_number=device_serial_number,
                tenant_id=tenant_id,
                type_code=type_code,
                mqtt_client_id=mqtt_client_id,
                mqtt_username=mqtt_username,
                master_secret_encrypted=encrypted_secret,
                encryption_algorithm="AES-256-GCM",
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
                    tenant_id=tenant_id,
                    device_id=device.id,
                    device_serial_number=device_serial_number,
                    config_key=config_key,
                    config_value=config_value,
                    value_type=value_type
                )
                db.add(config)
            
            db.flush()
            logger.info(f"创建新设备: {device_serial_number} (type: {type_code})")
        else:
            # 设备已存在，检查是否已被其他充电桩使用
            existing_cp = db.query(ChargePoint).filter(
                ChargePoint.device_serial_number == device_serial_number
            ).first()
            if existing_cp:
                logger.warning(
                    f"设备序列号 {device_serial_number} 已被充电桩 {existing_cp.id} 使用。"
                    f"如果这是新设备，请使用不同的序列号。"
                )
        
        return device
    
    @staticmethod
    def get_or_create_charge_point_config(
        db: Session,
        charge_point_id: UUID,
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
        
        # 获取tenant_id（从charge_point）
        tenant_id = None
        cp = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
        if cp:
            tenant_id = cp.tenant_id
        
        for config_key, config_value, value_type in default_configs:
            config = ChargePointConfig(
                tenant_id=tenant_id,
                charge_point_id=charge_point_id,
                config_key=config_key,
                config_value=config_value,
                value_type=value_type
            )
            db.add(config)
        
        db.flush()
        logger.debug(f"创建充电桩默认配置: {charge_point_id}")
