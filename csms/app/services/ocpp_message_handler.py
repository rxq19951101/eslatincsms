#
# OCPP消息处理服务
# 使用新的表结构处理OCPP消息
#

import logging
import re
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import Optional
from app.database.base import SessionLocal
from app.database.models import DeviceEvent, Device, ChargePoint
from app.services.charge_point_service import ChargePointService
from app.services.session_service import SessionService

logger = logging.getLogger("ocpp_csms")


def now_iso() -> str:
    """获取当前ISO格式时间（使用Z后缀）"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sanitize_charge_point_id(charge_point_id: str) -> str:
    """
    清理充电桩ID，只保留字母和数字
    移除所有特殊字符（如斜杠、星号等）
    
    Args:
        charge_point_id: 原始充电桩ID
        
    Returns:
        清理后的充电桩ID（只包含字母和数字）
    """
    # 只保留字母（包括中文）和数字，移除其他所有字符
    sanitized = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '', charge_point_id)
    
    # 如果清理后为空，返回一个默认值
    if not sanitized:
        sanitized = "CP_INVALID"
        logger.warning(f"充电桩ID清理后为空，使用默认值: {sanitized}")
    elif sanitized != charge_point_id:
        logger.warning(
            f"充电桩ID包含特殊字符，已清理: '{charge_point_id}' -> '{sanitized}'"
        )
    
    return sanitized


class OCPPMessageHandler:
    """OCPP消息处理器（使用新表结构）"""
    
    def __init__(self):
        self.charge_point_service = ChargePointService()
        self.session_service = SessionService()
    
    def _verify_device_authentication(
        self,
        db: Session,
        device_serial_number: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        验证设备是否已通过认证
        
        Returns:
            (是否通过认证, 错误信息)
        """
        if not device_serial_number:
            # 如果没有提供device_serial_number，允许继续（可能是WebSocket连接）
            return True, None
        
        from app.database.models import Device
        device = db.query(Device).filter(
            Device.serial_number == device_serial_number
        ).first()
        
        if not device:
            return False, f"设备 {device_serial_number} 不存在，未通过认证"
        
        if not device.is_active:
            return False, f"设备 {device_serial_number} 未激活"
        
        return True, None
    
    async def handle_boot_notification(
        self,
        charge_point_id: str,
        payload: Dict[str, Any],
        device_serial_number: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """处理BootNotification消息
        
        注意：对于MQTT传输，设备认证在broker层完成，能到达这里的消息说明设备已通过认证。
        对于WebSocket传输，可能没有device_serial_number，需要特殊处理。
        
        对于第一次发送BootNotification的充电桩，会清理charge_point_id中的特殊字符，
        只保留字母和数字，以防止注入攻击。
        """
        if db is None:
            db = SessionLocal()
            should_close = True
        else:
            should_close = False
        try:
            # 检查是否为第一次BootNotification（充电桩是否已存在）
            original_id = charge_point_id
            existing_charge_point = db.query(ChargePoint).filter(
                ChargePoint.id == charge_point_id
            ).first()
            
            # 如果是第一次BootNotification（充电桩不存在），清理charge_point_id
            if not existing_charge_point:
                # 清理charge_point_id，移除特殊字符（斜杠、星号等），只保留字母和数字
                sanitized_id = sanitize_charge_point_id(charge_point_id)
                
                # 如果清理后的ID与原ID不同，检查清理后的ID是否已存在
                if sanitized_id != charge_point_id:
                    existing_sanitized = db.query(ChargePoint).filter(
                        ChargePoint.id == sanitized_id
                    ).first()
                    
                    if existing_sanitized:
                        # 如果清理后的ID已存在，记录警告但继续使用清理后的ID
                        # get_or_create_charge_point会处理ID冲突（会创建新的唯一ID）
                        logger.warning(
                            f"首次BootNotification：清理后的充电桩ID '{sanitized_id}' 已存在，"
                            f"原始ID: '{original_id}'，系统将生成新的唯一ID"
                        )
                    else:
                        logger.info(
                            f"首次BootNotification：充电桩ID已清理 "
                            f"'{original_id}' -> '{sanitized_id}'"
                        )
                    
                    charge_point_id = sanitized_id
            vendor = str(payload.get("vendor", "")).strip() or str(payload.get("chargePointVendor", "")).strip()
            model = str(payload.get("model", "")).strip() or str(payload.get("chargePointModel", "")).strip()
            firmware_version = str(payload.get("firmwareVersion", "")).strip()
            serial_number = str(payload.get("serialNumber", "")).strip() or device_serial_number
            
            # 如果提供了device_serial_number，验证设备是否存在
            # 对于MQTT传输，设备应该已经存在（因为已通过认证）
            # 如果设备不存在，说明可能是WebSocket连接或数据不一致，记录警告但不拒绝
            if device_serial_number:
                from app.database.models import Device
                device = db.query(Device).filter(
                    Device.serial_number == device_serial_number
                ).first()
                
                if not device:
                    logger.warning(
                        f"设备 {device_serial_number} 不存在于devices表中，"
                        f"但消息已到达应用层（charge_point_id={charge_point_id}）。"
                        f"可能是WebSocket连接或数据不一致。"
                    )
                    # 不拒绝请求，允许继续处理（可能是WebSocket连接）
            
            # 获取或创建充电桩
            # 注意：如果device_serial_number存在但设备不存在，get_or_create_charge_point不会创建设备
            charge_point = self.charge_point_service.get_or_create_charge_point(
                db=db,
                charge_point_id=charge_point_id,
                device_serial_number=device_serial_number,
                vendor=vendor or None,
                model=model or None,
                serial_number=serial_number or None,
                firmware_version=firmware_version or None
            )
            
            # 更新EVSE状态为Available
            self.charge_point_service.update_evse_status(
                db=db,
                charge_point_id=charge_point_id,
                evse_id=1,
                status="Available"
            )
            
            # 记录Boot事件
            # 此时设备应该已经创建（通过get_or_create_charge_point），
            # 但为了安全起见，仍然检查设备是否存在
            event_device_serial = device_serial_number
            if event_device_serial:
                device = db.query(Device).filter(
                    Device.serial_number == event_device_serial
                ).first()
                if not device:
                    logger.warning(
                        f"设备 {event_device_serial} 不存在于devices表中，"
                        f"boot事件将不关联设备（charge_point_id={charge_point_id}）"
                    )
                    event_device_serial = None
            
            event = DeviceEvent(
                charge_point_id=charge_point_id,
                device_serial_number=event_device_serial,
                event_type="boot",
                event_data={
                    "vendor": vendor,
                    "model": model,
                    "firmware_version": firmware_version,
                    "serial_number": serial_number
                },
                timestamp=datetime.now(timezone.utc)
            )
            db.add(event)
            db.commit()
            
            logger.info(
                f"[{charge_point_id}] BootNotification: vendor={vendor or 'N/A'}, "
                f"model={model or 'N/A'}, firmware={firmware_version or 'N/A'}"
            )
            
            return {
                "status": "Accepted",
                "currentTime": now_iso(),
                "interval": 30,
            }
        except Exception as e:
            logger.error(f"[{charge_point_id}] BootNotification处理错误: {e}", exc_info=True)
            if should_close:
                db.rollback()
            # 返回符合 OCPP 规范的错误格式
            return {
                "status": "Rejected",
                "errorCode": "InternalError",
                "errorDescription": str(e)
            }
        finally:
            if should_close:
                db.close()
    
    async def handle_heartbeat(
        self,
        charge_point_id: str,
        payload: Dict[str, Any],
        device_serial_number: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """处理Heartbeat消息"""
        if db is None:
            db = SessionLocal()
            should_close = True
        else:
            should_close = False
        try:
            # 记录心跳
            self.charge_point_service.record_heartbeat(
                db=db,
                charge_point_id=charge_point_id,
                device_serial_number=device_serial_number
            )
            
            logger.info(f"[{charge_point_id}] Heartbeat处理完成")
            return {"currentTime": now_iso()}
        except Exception as e:
            logger.error(f"[{charge_point_id}] Heartbeat处理错误: {e}", exc_info=True)
            if should_close:
                db.rollback()
            return {"currentTime": now_iso()}
        finally:
            if should_close:
                db.close()
    
    async def handle_status_notification(
        self,
        charge_point_id: str,
        payload: Dict[str, Any],
        evse_id: int = 1,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """处理StatusNotification消息"""
        if db is None:
            db = SessionLocal()
            should_close = True
        else:
            should_close = False
        try:
            from app.database.models import ChargingSession, ChargePoint
            
            # 首先检查ChargePoint是否存在
            charge_point = db.query(ChargePoint).filter(
                ChargePoint.id == charge_point_id
            ).first()
            
            if not charge_point:
                logger.warning(
                    f"ChargePoint {charge_point_id} 不存在，拒绝StatusNotification请求。"
                    f"设备必须先发送BootNotification。"
                )
                if should_close:
                    db.close()
                return {}
            
            new_status = str(payload.get("status", "Unknown"))
            
            # 获取当前状态
            evse_status = self.charge_point_service.get_evse_status(
                db=db,
                charge_point_id=charge_point_id,
                evse_id=evse_id
            )
            
            previous_status = evse_status.status if evse_status else None
            
            # 更新状态
            self.charge_point_service.update_evse_status(
                db=db,
                charge_point_id=charge_point_id,
                evse_id=evse_id,
                status=new_status,
                previous_status=previous_status
            )
            
            # 如果状态变为Available，清理当前会话
            if new_status == "Available" and evse_status and evse_status.current_session_id:
                # 停止会话（如果存在）
                session = db.query(ChargingSession).filter(
                    ChargingSession.id == evse_status.current_session_id
                ).first()
                if session and session.status == "ongoing":
                    self.session_service.stop_session(
                        db=db,
                        charge_point_id=charge_point_id,
                        transaction_id=session.transaction_id
                    )
            
            logger.info(f"[{charge_point_id}] StatusNotification: {previous_status} -> {new_status}")
            return {}
        except Exception as e:
            logger.error(f"[{charge_point_id}] StatusNotification处理错误: {e}", exc_info=True)
            if should_close:
                db.rollback()
            # StatusNotification 即使出错也返回空对象（OCPP 规范）
            return {}
        finally:
            if should_close:
                db.close()
    
    async def handle_start_transaction(
        self,
        charge_point_id: str,
        payload: Dict[str, Any],
        evse_id: int = 1,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """处理StartTransaction消息"""
        if db is None:
            db = SessionLocal()
            should_close = True
        else:
            should_close = False
        try:
            from app.database.models import ChargingSession
            
            transaction_id = payload.get("transactionId") or int(datetime.now().timestamp())
            id_tag = str(payload.get("idTag", ""))
            meter_start = payload.get("meterStart", 0)
            
            # 开始会话
            session = self.session_service.start_session(
                db=db,
                charge_point_id=charge_point_id,
                evse_id=evse_id,
                transaction_id=transaction_id,
                id_tag=id_tag,
                meter_start=meter_start
            )
            
            logger.info(f"[{charge_point_id}] StartTransaction: transaction_id={transaction_id}, session_id={session.id}")
            
            return {
                "transactionId": transaction_id,
                "idTagInfo": {"status": "Accepted"}
            }
        except Exception as e:
            logger.error(f"[{charge_point_id}] StartTransaction处理错误: {e}", exc_info=True)
            if should_close:
                db.rollback()
            transaction_id = payload.get("transactionId", 0)
            # 返回符合 OCPP 规范的错误格式
            return {
                "transactionId": transaction_id,
                "idTagInfo": {
                    "status": "Rejected"
                },
                "errorCode": "InternalError",
                "errorDescription": str(e)
            }
        finally:
            if should_close:
                db.close()
    
    async def handle_stop_transaction(
        self,
        charge_point_id: str,
        payload: Dict[str, Any],
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """处理StopTransaction消息"""
        if db is None:
            db = SessionLocal()
            should_close = True
        else:
            should_close = False
        try:
            from app.database.models import ChargingSession
            
            transaction_id = payload.get("transactionId")
            meter_stop = payload.get("meterStop")
            
            # 停止会话
            session = self.session_service.stop_session(
                db=db,
                charge_point_id=charge_point_id,
                transaction_id=transaction_id,
                meter_stop=meter_stop
            )
            
            if session:
                logger.info(f"[{charge_point_id}] StopTransaction: transaction_id={transaction_id}, session_id={session.id}")
                return {
                    "idTagInfo": {"status": "Accepted"}
                }
            else:
                logger.warning(f"[{charge_point_id}] StopTransaction: 未找到会话 transaction_id={transaction_id}")
                return {
                    "idTagInfo": {"status": "Accepted"}  # 即使没找到也返回Accepted
                }
        except Exception as e:
            logger.error(f"[{charge_point_id}] StopTransaction处理错误: {e}", exc_info=True)
            if should_close:
                db.rollback()
            return {"idTagInfo": {"status": "Accepted"}}
        finally:
            if should_close:
                db.close()
    
    async def handle_meter_values(
        self,
        charge_point_id: str,
        payload: Dict[str, Any],
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """处理MeterValues消息"""
        if db is None:
            db = SessionLocal()
            should_close = True
        else:
            should_close = False
        try:
            from app.database.models import ChargingSession
            
            transaction_id = payload.get("transactionId")
            meter_value = payload.get("meterValue", [])
            
            if transaction_id:
                # 查找会话
                session = db.query(ChargingSession).filter(
                    ChargingSession.charge_point_id == charge_point_id,
                    ChargingSession.transaction_id == transaction_id,
                    ChargingSession.status == "ongoing"
                ).first()
                
                if session:
                    # 处理meter values
                    # OCPP格式：meterValue是一个数组，每个元素包含connectorId和sampledValue
                    for mv in meter_value:
                        connector_id = mv.get("connectorId")
                        sampled_values = mv.get("sampledValue", [])
                        
                        # 从sampledValue中提取主要值（通常是Energy.Active.Import.Register）
                        value = 0
                        for sv in sampled_values:
                            if sv.get("measurand") == "Energy.Active.Import.Register":
                                try:
                                    value = int(float(sv.get("value", 0)))
                                    break
                                except (ValueError, TypeError):
                                    pass
                        
                        # 如果没有找到Energy值，尝试使用value字段
                        if value == 0:
                            value = mv.get("value", 0)
                        
                        self.session_service.add_meter_value(
                            db=db,
                            session_id=session.id,
                            value=value,
                            connector_id=connector_id,
                            sampled_value=sampled_values if sampled_values else None
                        )
            
            return {}
        except Exception as e:
            logger.error(f"[{charge_point_id}] MeterValues处理错误: {e}", exc_info=True)
            if should_close:
                db.rollback()
            # MeterValues 即使出错也返回空对象（OCPP 规范）
            return {}
        finally:
            if should_close:
                db.close()
    
    async def handle_authorize(
        self,
        charge_point_id: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理Authorize消息"""
        id_tag = str(payload.get("idTag", ""))
        auth_status = "Accepted" if id_tag else "Invalid"
        return {"idTagInfo": {"status": auth_status}}
    
    async def handle_message(
        self,
        charge_point_id: str,
        action: str,
        payload: Dict[str, Any],
        device_serial_number: Optional[str] = None,
        evse_id: int = 1
    ) -> Dict[str, Any]:
        """处理OCPP消息路由"""
        # 对于BootNotification，优先使用payload中的serialNumber作为charge_point_id
        if action == "BootNotification":
            serial_number = payload.get("serialNumber") or payload.get("chargePointSerialNumber")
            if serial_number:
                serial_number = str(serial_number).strip()
                if serial_number:
                    original_id = charge_point_id
                    charge_point_id = serial_number
                    logger.info(
                        f"BootNotification使用payload中的serialNumber作为charge_point_id: "
                        f"'{original_id}' -> '{charge_point_id}'"
                    )
        
        handler_map = {
            "BootNotification": self.handle_boot_notification,
            "Heartbeat": self.handle_heartbeat,
            "StatusNotification": self.handle_status_notification,
            "Authorize": self.handle_authorize,
            "StartTransaction": self.handle_start_transaction,
            "StopTransaction": self.handle_stop_transaction,
            "MeterValues": self.handle_meter_values,
        }
        
        handler = handler_map.get(action)
        if handler:
            if action in ["BootNotification", "Heartbeat"]:
                return await handler(charge_point_id, payload, device_serial_number)
            elif action == "StatusNotification":
                return await handler(charge_point_id, payload, evse_id)
            elif action == "StartTransaction":
                # StartTransaction 需要 evse_id 来关联正确的 EVSE
                return await handler(charge_point_id, payload, evse_id)
            else:
                return await handler(charge_point_id, payload)
        else:
            logger.warning(f"[{charge_point_id}] 未知的OCPP动作: {action}")
            return {}


# 全局消息处理器实例
ocpp_message_handler = OCPPMessageHandler()
