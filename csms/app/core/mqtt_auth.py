#
# MQTT 鉴权服务
# 处理设备MQTT连接认证和topic权限验证
# 支持所有品牌的充电桩
# 使用HMAC派生密码（不再使用明文共享密码）
#

import logging
from typing import Optional, Tuple, List, Dict
from sqlalchemy.orm import Session
from app.database.models import Device, ChargePoint
from app.core.crypto import derive_password, decrypt_master_secret

logger = logging.getLogger("ocpp_csms")


class MQTTAuthService:
    """MQTT鉴权服务 - 支持多品牌充电桩"""
    
    @staticmethod
    def authenticate_device(
        db: Session,
        client_id: str,
        username: str,
        password: str
    ) -> Tuple[bool, Optional[str]]:
        """
        验证设备MQTT连接认证
        
        Args:
            db: 数据库会话
            client_id: MQTT客户端ID，格式：{type_code}&{serial_number}，如 zcf&861076087029615
            username: MQTT用户名，格式：{serial_number}，如 861076087029615（设备SN号）
            password: MQTT密码（12位字符串）
        
        Returns:
            (认证是否成功, 错误信息)
        """
        try:
            # 验证client_id格式：{type_code}&{serial_number}
            if "&" not in client_id:
                return False, "Invalid client_id format, expected: type_code&serial_number"
            
            parts = client_id.split("&", 1)
            if len(parts) != 2:
                return False, "Invalid client_id format, expected: type_code&serial_number"
            
            type_code, serial_number = parts
            
            # 验证username是否与client_id中的serial_number一致
            if username != serial_number:
                return False, "Username does not match serial_number in client_id"
            
            # 验证serial_number不为空
            if not serial_number or len(serial_number.strip()) == 0:
                return False, "Serial number cannot be empty"
            
            # 验证password长度（12位）
            if len(password) != 12:
                return False, "Password must be 12 characters"
            
            # 查询设备
            device = db.query(Device).filter(
                Device.serial_number == serial_number
            ).first()
            
            if not device:
                logger.warning(f"Device not found: {serial_number}")
                return False, "Device not found"
            
            if not device.is_active:
                logger.warning(f"Device is inactive: {serial_number}")
                return False, "Device is inactive"
            
            # 验证client_id和username
            if device.mqtt_client_id != client_id:
                logger.warning(f"Client ID mismatch for device {serial_number}")
                return False, "Client ID mismatch"
            
            if device.mqtt_username != username:
                logger.warning(f"Username mismatch for device {serial_number}")
                return False, "Username mismatch"
            
            # 验证type_code是否匹配
            if device.type_code != type_code:
                logger.warning(f"Device type code mismatch: expected {device.type_code}, got {type_code}")
                return False, "Device type code mismatch"
            
            # 使用HMAC派生密码进行验证（从设备直接获取master_secret）
            try:
                # 解密master secret
                master_secret = decrypt_master_secret(device.master_secret_encrypted)
                # 派生该设备的密码
                expected_password = derive_password(master_secret, serial_number)
                
                if expected_password != password:
                    logger.warning(f"Password mismatch for device {serial_number}")
                    return False, "Password mismatch"
            except Exception as e:
                logger.error(f"密码验证失败: {e}", exc_info=True)
                return False, f"Password verification failed: {str(e)}"
            
            # 更新设备最后连接时间
            from datetime import datetime, timezone
            device.last_connected = datetime.now(timezone.utc)
            db.commit()
            
            logger.info(f"Device authenticated successfully: {serial_number} (type: {device.type_code})")
            return True, None
            
        except Exception as e:
            logger.error(f"Authentication error: {e}", exc_info=True)
            return False, f"Authentication error: {str(e)}"
    
    @staticmethod
    def check_topic_permission(
        db: Session,
        username: str,
        topic: str,
        operation: str  # "subscribe" or "publish"
    ) -> Tuple[bool, Optional[str]]:
        """
        检查设备对topic的权限
        
        Topic格式：{type_code}/{serial_number}/user/{up|down}
        例如：zcf/861076087029615/user/up
        
        Args:
            db: 数据库会话
            username: MQTT用户名（设备SN号）
            topic: MQTT主题
            operation: 操作类型（subscribe或publish）
        
        Returns:
            (是否有权限, 错误信息)
        """
        try:
            # 查询设备
            device = db.query(Device).filter(
                Device.mqtt_username == username
            ).first()
            
            if not device:
                return False, "Device not found"
            
            if not device.is_active:
                return False, "Device is inactive"
            
            # 解析topic格式：{type_code}/{serial_number}/user/{up|down}
            parts = topic.split("/")
            if len(parts) != 4:
                return False, f"Invalid topic format: {topic}, expected: {{type_code}}/{{serial_number}}/user/{{up|down}}"
            
            type_code, serial_number, category, direction = parts
            
            # 验证category必须是"user"
            if category != "user":
                return False, f"Invalid topic category: {category}, expected: user"
            
            # 验证serial_number是否匹配
            if serial_number != username:
                return False, "Serial number in topic does not match username"
            
            # 验证设备类型
            if device.type_code != type_code:
                return False, f"Device type mismatch: expected {device.type_code}, got {type_code}"
            
            # 权限规则：
            # - 设备只能发布到 {type_code}/{serial_number}/user/up
            # - 设备只能订阅 {type_code}/{serial_number}/user/down
            if operation == "publish":
                if direction != "up":
                    return False, f"Device can only publish to .../user/up, got: {topic}"
            elif operation == "subscribe":
                if direction != "down":
                    return False, f"Device can only subscribe to .../user/down, got: {topic}"
            else:
                return False, f"Invalid operation: {operation}"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Topic permission check error: {e}", exc_info=True)
            return False, f"Permission check error: {str(e)}"
    
    @staticmethod
    def get_device_by_serial(db: Session, serial_number: str) -> Optional[Device]:
        """根据SN号获取设备"""
        return db.query(Device).filter(
            Device.serial_number == serial_number
        ).first()
    
    @staticmethod
    def get_device_by_username(db: Session, username: str) -> Optional[Device]:
        """根据MQTT用户名获取设备"""
        return db.query(Device).filter(
            Device.mqtt_username == username
        ).first()
    
    @staticmethod
    def get_charge_point_id_from_serial(db: Session, serial_number: str) -> Optional[str]:
        """根据设备SN号获取关联的充电桩ID（charge_point_id）"""
        device = db.query(Device).filter(
            Device.serial_number == serial_number
        ).first()
        
        if device:
            # 查找关联的充电桩
            charge_point = db.query(ChargePoint).filter(
                ChargePoint.device_serial_number == serial_number
            ).first()
            
            if charge_point:
                return charge_point.id
        return None
    
    @staticmethod
    def get_all_active_device_types(db: Session) -> List[dict]:
        """获取所有激活的设备类型代码（用于动态订阅topic）"""
        # 从设备表中获取所有唯一的type_code
        devices = db.query(Device).filter(
            Device.is_active == True
        ).all()
        type_codes = list(set([d.type_code for d in devices]))
        return [{"type_code": tc} for tc in type_codes]
    
    @staticmethod
    def build_topic_up(type_code: str, serial_number: str) -> str:
        """构建设备发送消息的topic"""
        return f"{type_code}/{serial_number}/user/up"
    
    @staticmethod
    def build_topic_down(type_code: str, serial_number: str) -> str:
        """构建服务器发送消息的topic"""
        return f"{type_code}/{serial_number}/user/down"
    
    @staticmethod
    def get_device_info_from_charge_point_id(db: Session, charge_point_id: str) -> Optional[Dict[str, str]]:
        """根据charge_point_id获取设备信息（type_code和serial_number）"""
        # 通过charge_point查找关联的设备
        charge_point = db.query(ChargePoint).filter(
            ChargePoint.id == charge_point_id
        ).first()
        
        if charge_point and charge_point.device_serial_number:
            device = db.query(Device).filter(
                Device.serial_number == charge_point.device_serial_number
            ).first()
            
            if device:
                return {
                    "type_code": device.type_code,
                    "serial_number": device.serial_number
                }
        
        # 如果charge_point_id本身就是serial_number，尝试直接查找设备
        device = db.query(Device).filter(
            Device.serial_number == charge_point_id
        ).first()
        
        if device:
            return {
                "type_code": device.type_code,
                "serial_number": device.serial_number
            }
        
        return None
