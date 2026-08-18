#
# OCPP消息处理服务
# 使用新的表结构处理OCPP消息
#

import logging
import hashlib
import json
import os
import re
import uuid
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database.base import SessionLocal
from app.database.base import tenant_id_context
from app.database.models import DeviceEvent, Device, ChargePoint, RiskReservation
from app.core.asset_identifiers import get_charge_point_by_reference
from app.services.charge_point_service import ChargePointService
from app.services.meter_telemetry_service import (
    MeterTelemetryDecision,
    meter_telemetry_service,
)
from app.services.session_service import SessionService

logger = logging.getLogger("ocpp_csms")


def now_iso() -> str:
    """获取当前ISO格式时间（使用Z后缀）"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sanitize_charge_point_id(charge_point_id: str) -> str:
    """
    清理充电桩ID，保留设备常用的安全标识字符。

    OCPP 设备 ID 常包含下划线、短横线或点号。不能把这些字符删除，
    否则 WebSocket 连接身份会与 BootNotification 创建的资产 ID 不一致，
    后续 StartTransaction 会找不到充电桩。路径分隔符和控制字符仍会被移除。
    
    Args:
        charge_point_id: 原始充电桩ID
        
    Returns:
        清理后的充电桩ID
    """
    sanitized = re.sub(r'[^a-zA-Z0-9_.\-\u4e00-\u9fa5]', '', charge_point_id)
    
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
    
    def __init__(self, telemetry_service=None):
        self.charge_point_service = ChargePointService()
        self.session_service = SessionService()
        self.telemetry_service = telemetry_service or meter_telemetry_service

    @classmethod
    def _begin_inbound_message(
        cls,
        db: Session,
        charge_point_id: str,
        action: str,
        payload: Dict[str, Any],
        unique_id: Optional[str],
    ):
        """Claim one inbound CALL and return its first result on replay."""
        from app.database.models import OCPPMessageEvent

        cp = get_charge_point_by_reference(db, charge_point_id)
        if not cp or not cp.tenant_id:
            raise ValueError(f"Charge point tenant not found: {charge_point_id}")
        message_key = unique_id or cls._message_key(action, payload)
        query = db.query(OCPPMessageEvent).filter(
            OCPPMessageEvent.tenant_id == cp.tenant_id,
            OCPPMessageEvent.charge_point_id == cp.id,
        )
        if unique_id:
            existing = query.filter(OCPPMessageEvent.unique_id == unique_id).first()
        else:
            existing = query.filter(
                OCPPMessageEvent.action == action,
                OCPPMessageEvent.message_key == message_key,
            ).first()
        if existing:
            if existing.action != action or existing.payload != payload:
                return existing, {
                    "_ocpp_error": {
                        "code": "ProtocolError",
                        "description": "OCPP UniqueId was reused with a different action or payload",
                        "details": {},
                    }
                }
            if existing.processing_status == "completed" and existing.response_payload is not None:
                return existing, dict(existing.response_payload)
            return existing, {
                "_ocpp_error": {
                    "code": "InternalError",
                    "description": "Original OCPP request is still processing",
                    "details": {},
                }
            }

        event = OCPPMessageEvent(
            tenant_id=cp.tenant_id,
            charge_point_id=cp.id,
            action=action,
            unique_id=unique_id,
            message_key=message_key,
            payload=payload,
            processing_status="processing",
        )
        db.add(event)
        db.flush()
        return event, None

    @staticmethod
    def _complete_inbound_message(db: Session, event, response: Dict[str, Any]) -> None:
        event.response_payload = response
        event.response_message_type = 4 if response.get("_ocpp_error") else 3
        event.processing_status = "completed"
        event.outcome = response.get("_outcome") or (
            "call_error" if response.get("_ocpp_error") else "processed"
        )
        event.processed_at = datetime.now(timezone.utc)
        db.commit()

    @staticmethod
    def _allocate_transaction_id(db: Session, charge_point_id) -> int:
        """Allocate a positive OCPP integer without wall-clock collisions."""
        from app.database.models import ChargingSession

        for _ in range(32):
            candidate = (uuid.uuid4().int % 2_147_483_647) + 1
            exists = db.query(ChargingSession.id).filter(
                ChargingSession.charge_point_id == charge_point_id,
                ChargingSession.transaction_id == candidate,
            ).first()
            if not exists:
                return candidate
        raise RuntimeError("Unable to allocate a unique OCPP transaction ID")
    
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
            existing_charge_point = get_charge_point_by_reference(db, charge_point_id)

            # 严格模式：不允许 BootNotification 自动创建新桩（必须先在后台录入硬件码/charge_point_id）
            require_pre_registered = os.getenv("OCPP_WS_REQUIRE_PRE_REGISTERED", "true").lower() in ("true", "1", "yes")
            if require_pre_registered and not existing_charge_point:
                logger.warning(
                    f"[{charge_point_id}] BootNotification rejected: charge point not pre-registered"
                )
                # OCPP 1.6 BootNotificationResponse
                return {
                    "status": "Rejected",
                    "currentTime": datetime.now(timezone.utc).isoformat(),
                    "interval": 30,
                }
            
            # 如果是第一次BootNotification（充电桩不存在），清理charge_point_id
            if not existing_charge_point:
                # 清理charge_point_id，移除特殊字符（斜杠、星号等），只保留字母和数字
                sanitized_id = sanitize_charge_point_id(charge_point_id)
                
                # 如果清理后的ID与原ID不同，检查清理后的ID是否已存在
                if sanitized_id != charge_point_id:
                    existing_sanitized = db.query(ChargePoint).filter(
                        ChargePoint.ocpp_identity == sanitized_id
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
            serial_number = (
                str(payload.get("serialNumber", "")).strip()
                or str(payload.get("chargePointSerialNumber", "")).strip()
                or device_serial_number
            )
            
            # 如果提供了device_serial_number，验证设备是否存在
            # 对于MQTT传输，设备应该已经存在（因为已通过认证）
            # 如果设备不存在，说明可能是WebSocket连接或数据不一致，记录警告但不拒绝
            # 注意：如果设备不存在，将device_serial_number设为None，避免外键约束错误
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
                        f"将device_serial_number设为None，避免外键约束错误。"
                    )
                    # 将device_serial_number设为None，避免外键约束错误
                    device_serial_number = None
                elif not device.is_active:
                    logger.warning(
                        f"设备 {device_serial_number} 未激活，"
                        f"将device_serial_number设为None（charge_point_id={charge_point_id}）"
                    )
                    device_serial_number = None
            
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
            event_device = None
            if event_device_serial:
                event_device = db.query(Device).filter(
                    Device.serial_number == event_device_serial
                ).first()
                if not event_device:
                    logger.warning(
                        f"设备 {event_device_serial} 不存在于devices表中，"
                        f"boot事件将不关联设备（charge_point_id={charge_point_id}）"
                    )
                    event_device_serial = None
            
            # 注意：WebSocket/MQTT 的 OCPP 消息不经过 HTTP middleware，因此 tenant_id_context 可能为空。
            # 但 device_events.tenant_id 为 NOT NULL，这里必须补齐 tenant_id。
            resolved_tenant_id = tenant_id_context.get() or getattr(charge_point, "tenant_id", None)
            event = DeviceEvent(
                tenant_id=resolved_tenant_id,
                charge_point_id=charge_point.id,
                device_id=event_device.id if event_device else None,
                device_serial_number=event_device_serial,
                event_type="boot",
                event_data={
                    "vendor": vendor,
                    "model": model,
                    "firmware_version": firmware_version,
                    "serial_number": serial_number,
                },
                timestamp=datetime.now(timezone.utc),
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
            from app.database.models import ChargingSession, ChargePoint, EVSE
            from app.services.alert_service import AlertService
            
            # 首先检查ChargePoint是否存在
            charge_point = get_charge_point_by_reference(db, charge_point_id)
            
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

            evse = db.query(EVSE).filter(
                EVSE.charge_point_id == charge_point.id,
                EVSE.evse_id == evse_id,
            ).first()
            if new_status == "Faulted":
                AlertService.ensure_automatic_alert(
                    db,
                    tenant_id=charge_point.tenant_id,
                    alert_type="faulted",
                    severity="critical",
                    title=f"充电桩 {charge_point.ocpp_identity} 故障",
                    description=str(payload.get("info") or payload.get("errorCode") or "Faulted"),
                    charge_point_id=charge_point.id,
                    evse_id=evse.id if evse else None,
                    metadata={
                        "source": "StatusNotification",
                        "error_code": payload.get("errorCode"),
                        "vendor_error_code": payload.get("vendorErrorCode"),
                    },
                )
            elif new_status in {"Available", "Preparing", "Charging", "SuspendedEV", "SuspendedEVSE"}:
                AlertService.resolve_automatic_alerts(
                    db,
                    tenant_id=charge_point.tenant_id,
                    charge_point_id=charge_point.id,
                    alert_types=["faulted", "offline"],
                    evse_id=evse.id if evse else None,
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
            from app.database.models import ChargePoint

            charge_point = get_charge_point_by_reference(db, charge_point_id)
            if not charge_point:
                raise ValueError(f"Charge point not found: {charge_point_id}")
            transaction_id = self._allocate_transaction_id(db, charge_point.id)
            id_tag = str(payload.get("idTag", ""))
            meter_start = payload.get("meterStart", 0)
            authorization = await self.handle_authorize(charge_point_id, {"idTag": id_tag})
            auth_status = authorization["idTagInfo"]["status"]
            if auth_status != "Accepted":
                from app.api.v1.ocpp_control import mark_remote_start_finished
                mark_remote_start_finished(charge_point.ocpp_identity, evse_id)
                return {
                    "transactionId": transaction_id,
                    "idTagInfo": {"status": auth_status},
                    "_outcome": "authorization_rejected",
                }
            user_id = None
            # 爆改测试版：RemoteStart 使用 APP + UUID前17字符 作为 idTag (共20字符)
            # OCPP 1.6J 规定 idTag 最大长度为 20 个字符
            # 格式：APP + UUID去掉连字符后的前17个字符
            if id_tag.startswith("APP") and len(id_tag) == 20:
                # 提取 UUID 前缀（17个字符），然后查找匹配的 AppUser
                uuid_prefix = id_tag[3:]  # 去掉 "APP" 前缀
                # 在数据库中查找 UUID 前17个字符匹配的用户
                # UUID 格式：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (32个字符，去掉连字符)
                # 我们需要查找所有以这个前缀开头的 UUID
                from app.database.models import AppUser
                from sqlalchemy import func
                # 查找 UUID 字符串表示的前17个字符匹配的用户
                # 注意：UUID 在 PostgreSQL 中是二进制格式，需要转换为字符串比较
                from sqlalchemy import String
                matching_users = db.query(AppUser).filter(
                    func.replace(func.cast(AppUser.id, String), "-", "").like(f"{uuid_prefix}%")
                ).limit(1).all()
                if matching_users:
                    user_id = str(matching_users[0].id)
                    logger.info(f"[{charge_point_id}] Parsed AppUser ID from idTag {id_tag}: {user_id}")
                else:
                    logger.warning(f"[{charge_point_id}] Could not find AppUser for idTag prefix: {uuid_prefix}")
            
            # 开始会话
            session = self.session_service.start_session(
                db=db,
                charge_point_id=charge_point_id,
                evse_id=evse_id,
                transaction_id=transaction_id,
                id_tag=id_tag,
                user_id=user_id,
                meter_start=meter_start
            )
            from app.api.v1.ocpp_control import mark_remote_start_finished
            mark_remote_start_finished(charge_point.ocpp_identity, evse_id)
            
            logger.info(f"[{charge_point_id}] StartTransaction: transaction_id={transaction_id}, session_id={session.id}")
            
            return {
                "transactionId": transaction_id,
                "idTagInfo": {"status": "Accepted"},
                "_outcome": "session_started",
            }
        except Exception as e:
            logger.error(f"[{charge_point_id}] StartTransaction处理错误: {e}", exc_info=True)
            if should_close:
                db.rollback()
            return {
                "transactionId": self._allocate_transaction_id(
                    db, get_charge_point_by_reference(db, charge_point_id).id
                ) if get_charge_point_by_reference(db, charge_point_id) else 1,
                "idTagInfo": {
                    "status": "Rejected"
                },
                "_outcome": "session_rejected",
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
                # D-204 physical-stop authority is confirmed only by the
                # device's StopTransaction fact.  RemoteStop Accepted is not
                # used as a substitute.  A session without a risk reservation
                # is a legacy/P001 session and remains unchanged.
                try:
                    from app.services.risk_budget import RiskBudgetService, RiskBudgetError
                    RiskBudgetService.confirm_stop_transaction(
                        db,
                        session_id=session.id,
                        source_event_id=f"ocpp-stop:{charge_point_id}:{transaction_id}:{payload.get('timestamp') or session.end_time}",
                        meter_stop=meter_stop,
                    )
                except RiskBudgetError:
                    logger.warning("Risk stop confirmation did not converge for session=%s", session.id, exc_info=True)
                logger.info(f"[{charge_point_id}] StopTransaction: transaction_id={transaction_id}, session_id={session.id}")
                return {
                    "idTagInfo": {"status": "Accepted"},
                    "_outcome": "session_stopped",
                }
            else:
                logger.warning(f"[{charge_point_id}] StopTransaction: 未找到会话 transaction_id={transaction_id}")
                return {
                    "idTagInfo": {"status": "Invalid"},
                    "_outcome": "orphan_ignored",
                }
        except Exception as e:
            logger.error(f"[{charge_point_id}] StopTransaction处理错误: {e}", exc_info=True)
            if should_close:
                db.rollback()
            return {"idTagInfo": {"status": "Invalid"}, "_outcome": "stop_rejected"}
        finally:
            if should_close:
                db.close()
    
    async def handle_meter_values(
        self,
        charge_point_id: str,
        payload: Dict[str, Any],
        db: Optional[Session] = None,
        message_unique_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """处理MeterValues消息"""
        if db is None:
            db = SessionLocal()
            should_close = True
        else:
            should_close = False
        telemetry_decision: Optional[MeterTelemetryDecision] = None
        try:
            from app.database.models import ChargingSession
            transaction_id = payload.get("transactionId")
            meter_value = payload.get("meterValue", [])
            
            if transaction_id:
                # 查找会话
                cp = get_charge_point_by_reference(db, charge_point_id)
                if not cp:
                    raise ValueError(f"Charge point not found: {charge_point_id}")
                session = db.query(ChargingSession).filter(
                    ChargingSession.charge_point_id == cp.id,
                    ChargingSession.transaction_id == transaction_id,
                    ChargingSession.status == "ongoing"
                ).first()
                
                if session and meter_value:
                    prepared_values = []
                    for index, mv in enumerate(meter_value):
                        connector_id = mv.get("connectorId", payload.get("connectorId"))
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

                        prepared_values.append({
                            "index": index,
                            "connector_id": connector_id,
                            "sampled_values": sampled_values,
                            "timestamp": mv.get("timestamp") or now_iso(),
                            "value": int(value),
                        })

                    latest = prepared_values[-1]
                    message_key = message_unique_id or self._message_key("MeterValues", payload)
                    telemetry_decision = self.telemetry_service.record_latest(
                        tenant_id=session.tenant_id,
                        session_id=session.id,
                        message_key=message_key,
                        snapshot={
                            "id": f"realtime:{latest['timestamp']}",
                            "session_id": str(session.id),
                            "timestamp": latest["timestamp"],
                            "received_at": now_iso(),
                            "connector_id": latest["connector_id"],
                            "value_wh": latest["value"],
                            "sampled_value": latest["sampled_values"],
                            "source": "realtime",
                        },
                    )
                    if telemetry_decision.duplicate:
                        return {"_outcome": "meter_replayed"}

                    values_to_persist = (
                        prepared_values
                        if not telemetry_decision.redis_available
                        else ([latest] if telemetry_decision.should_persist else [])
                    )
                    for prepared in values_to_persist:
                        self.session_service.add_meter_value(
                            db=db,
                            session_id=session.id,
                            value=prepared["value"],
                            connector_id=prepared["connector_id"],
                            sampled_value=(
                                prepared["sampled_values"]
                                if prepared["sampled_values"]
                                else None
                            ),
                            idempotency_key=(
                                f"ocpp:{message_unique_id}:{prepared['index']}"
                                if message_unique_id
                                else self._meter_idempotency_key(
                                    charge_point_id,
                                    transaction_id,
                                    meter_value[prepared["index"]],
                                    prepared["index"],
                                )
                            ),
                            commit=False,
                        )
                    if values_to_persist:
                        db.commit()
                    # Persist the risk checkpoint independently of Redis's
                    # sampled telemetry gate.  RiskBudgetService is a no-op
                    # for sessions without a pinned BE-205 reservation.
                    try:
                        from app.services.risk_budget import RiskBudgetService, RiskBudgetError
                        risk_reservation = db.query(RiskReservation).filter(
                            RiskReservation.session_id == session.id,
                        ).order_by(RiskReservation.created_at.desc()).first()
                        if risk_reservation is not None:
                            meter_at = datetime.fromisoformat(
                                str(latest["timestamp"]).replace("Z", "+00:00")
                            )
                            RiskBudgetService.observe_meter(
                                db,
                                session_id=session.id,
                                expected_version=risk_reservation.version,
                                source_event_id=f"ocpp-meter:{message_key}:{latest['timestamp']}",
                                meter_wh=latest["value"],
                                meter_at=meter_at,
                            )
                    except RiskBudgetError:
                        # The device acknowledgement remains protocol-valid,
                        # while the risk state stays fail-closed and is picked
                        # up by the risk recovery worker.
                        logger.warning("Risk MeterValues checkpoint did not converge for session=%s", session.id, exc_info=True)
                    return {
                        "_outcome": (
                            "meter_recorded" if values_to_persist else "meter_buffered"
                        )
                    }
            return {"_outcome": "orphan_ignored"}
        except Exception as e:
            if telemetry_decision and telemetry_decision.should_persist:
                self.telemetry_service.release_write_claims(telemetry_decision)
            logger.error(f"[{charge_point_id}] MeterValues处理错误: {e}", exc_info=True)
            if should_close:
                db.rollback()
            # MeterValues 即使出错也返回空对象（OCPP 规范）
            return {}
        finally:
            if should_close:
                db.close()

    @staticmethod
    def _message_key(action: str, payload: Dict[str, Any]) -> str:
        raw = json.dumps({"action": action, "payload": payload}, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def _meter_idempotency_key(cls, charge_point_id: str, transaction_id: int, meter_value: Dict[str, Any], index: int) -> str:
        raw = json.dumps({
            "charge_point_id": charge_point_id,
            "transaction_id": transaction_id,
            "meter_value": meter_value,
            "index": index,
        }, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def handle_authorize(
        self,
        charge_point_id: str,
        payload: Dict[str, Any],
        db: Optional[Session] = None,
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
        evse_id: int = 1,
        message_unique_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """处理OCPP消息路由
        
        The charge_point_id argument is the authenticated transport identity. Boot
        payload serial numbers are asset metadata and must never replace it.
        """
        handler_map = {
            "BootNotification": self.handle_boot_notification,
            "Heartbeat": self.handle_heartbeat,
            "StatusNotification": self.handle_status_notification,
            "Authorize": self.handle_authorize,
            "StartTransaction": self.handle_start_transaction,
            "StopTransaction": self.handle_stop_transaction,
            "MeterValues": self.handle_meter_values,
        }
        
        db = SessionLocal()
        try:
            # Heartbeat 本身幂等，只更新限频在线快照，不建立永久消息历史。
            if action == "Heartbeat":
                return await self.handle_heartbeat(
                    charge_point_id,
                    payload,
                    device_serial_number,
                    db,
                )

            # MeterValues 是高频幂等遥测；Redis 提供短期去重和实时快照，
            # PostgreSQL 只保存分钟采样，不创建永久 OCPP 消息行。
            if action == "MeterValues":
                return await self.handle_meter_values(
                    charge_point_id,
                    payload,
                    db,
                    message_unique_id=message_unique_id,
                )

            event, replay = self._begin_inbound_message(
                db, charge_point_id, action, payload, message_unique_id
            )
            if replay is not None:
                return replay
            handler = handler_map.get(action)
            if not handler:
                result = {
                    "_ocpp_error": {
                        "code": "NotSupported",
                        "description": f"Unsupported OCPP action: {action}",
                        "details": {},
                    }
                }
            elif action in ["BootNotification", "Heartbeat"]:
                result = await handler(charge_point_id, payload, device_serial_number, db)
            elif action in ["StatusNotification", "StartTransaction"]:
                result = await handler(charge_point_id, payload, evse_id, db)
            else:
                result = await handler(charge_point_id, payload, db)
            self._complete_inbound_message(db, event, result)
            return result
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


# 全局消息处理器实例
ocpp_message_handler = OCPPMessageHandler()
