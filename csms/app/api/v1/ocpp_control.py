#
# OCPP控制API
# 提供OCPP远程控制功能（RemoteStart, RemoteStop等）
#

import asyncio
import time
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.exceptions import ChargerNotConnectedException
from app.core.logging_config import get_logger
from app.core.asset_identifiers import (
    get_charge_point_by_reference,
    get_tenant_charge_point_by_reference,
)
from app.core.permissions import require_permission
from app.database.base import get_db, tenant_id_context
from app.database.models import (
    AuditLog,
    ChargePoint,
    ChargingSession,
    EVSE,
    EVSEStatus,
    OutboxEvent,
)
from app.services.outbox_service import OutboxService
from app.services.asset_lifecycle_service import (
    AssetNotOperationalError,
    require_charge_point_operational,
)
from app.api.validation import StrictRequestModel
import uuid

settings = get_settings()
logger = get_logger("ocpp_csms")

# 根据配置选择使用分布式或单机模式
if settings.enable_distributed:
    from app.ocpp.message_router import message_router as message_handler
    from app.ocpp.distributed_connection_manager import distributed_connection_manager as connection_manager
else:
    from app.ocpp.message_sender import message_sender as message_handler
    from app.ocpp.connection_manager import connection_manager

# 导入 WebSocket transport_manager 用于检查连接
try:
    from app.ocpp.transport_manager import transport_manager, TransportType
    TRANSPORT_MANAGER_AVAILABLE = True
except ImportError:
    TRANSPORT_MANAGER_AVAILABLE = False
    transport_manager = None
    TransportType = None

router = APIRouter()

_remote_start_inflight: dict[tuple[str, int], float] = {}
_remote_start_guard = asyncio.Lock()
_REMOTE_START_INFLIGHT_SECONDS = 30.0


def mark_remote_start_finished(charge_point_identity: str, connector_id: int) -> None:
    _remote_start_inflight.pop((charge_point_identity, connector_id), None)


def check_charger_connection(charge_point_id: str) -> bool:
    """检查充电桩 WebSocket 连接状态。"""
    is_connected_ws = False
    
    # 首先检查 charger_websockets 字典（WebSocket连接的主要存储位置）
    try:
        # 动态导入 charger_websockets（避免循环导入）
        import sys
        main_module = sys.modules.get('app.main')
        if main_module and hasattr(main_module, 'charger_websockets'):
            charger_websockets = getattr(main_module, 'charger_websockets')
            if charge_point_id in charger_websockets:
                ws = charger_websockets[charge_point_id]
                # 如果WebSocket对象存在，认为连接有效
                # 因为如果连接断开，WebSocket对象会从字典中移除
                if ws is not None:
                    is_connected_ws = True
                    logger.info(f"[API] charger_websockets中找到连接: {charge_point_id}")
    except Exception as e:
        logger.debug(f"[API] 检查charger_websockets失败: {e}")
    
    # 检查 WebSocket 连接（connection_manager）
    if not is_connected_ws:
        try:
            is_connected_ws = connection_manager.is_connected(charge_point_id)
            logger.debug(f"[API] connection_manager.is_connected({charge_point_id}) = {is_connected_ws}")
        except Exception as e:
            logger.warning(f"[API] connection_manager.is_connected() 检查失败: {e}")
    
    # 检查 transport_manager 的 WebSocket 适配器
    if not is_connected_ws and TRANSPORT_MANAGER_AVAILABLE and transport_manager and TransportType:
        try:
            if hasattr(transport_manager, 'adapters') and transport_manager.adapters:
                ws_adapter = transport_manager.adapters.get(TransportType.WEBSOCKET)
                if ws_adapter and hasattr(ws_adapter, 'is_connected'):
                    is_connected_ws = ws_adapter.is_connected(charge_point_id)
                    logger.debug(f"[API] transport_manager WebSocket适配器.is_connected({charge_point_id}) = {is_connected_ws}")
        except Exception as e:
            logger.debug(f"[API] 检查transport_manager WebSocket适配器失败: {e}")
    
    logger.info(f"[API] 充电桩 {charge_point_id} WebSocket连接状态: {is_connected_ws}")
    is_connected = is_connected_ws
    return is_connected


def _scoped_charge_point(db: Session, reference: str) -> ChargePoint:
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    cp = get_tenant_charge_point_by_reference(db, reference, tenant_id)
    if not cp:
        if get_charge_point_by_reference(db, reference):
            raise HTTPException(status_code=403, detail="Charge point belongs to another tenant")
        raise HTTPException(status_code=404, detail="Charge point not found")
    return cp


def _normalize_remote_command_key(
    idempotency_key: Optional[str],
    *,
    generate: bool,
) -> Optional[str]:
    if idempotency_key is None:
        return str(uuid.uuid4()) if generate else None
    command_key = idempotency_key.strip()
    if not command_key or len(command_key) > 255:
        raise HTTPException(status_code=422, detail="Idempotency-Key must contain 1-255 characters")
    return command_key


def _raise_idempotency_key_reused() -> None:
    exc = HTTPException(
        status_code=409,
        detail="Idempotency-Key was already used for a different remote command",
    )
    exc.error_code = "IDEMPOTENCY_KEY_REUSED"
    raise exc


def _validate_remote_command_match(
    event: OutboxEvent,
    *,
    charge_point: ChargePoint,
    action: str,
    payload: dict,
) -> None:
    stored_payload = event.payload or {}
    expected_payload = {
        "charge_point_id": str(charge_point.id),
        "ocpp_identity": charge_point.ocpp_identity,
        **payload,
    }
    if (
        event.aggregate_type != "ChargePoint"
        or event.aggregate_id != str(charge_point.id)
        or event.event_type != f"{action}Requested"
        or any(stored_payload.get(key) != value for key, value in expected_payload.items())
    ):
        _raise_idempotency_key_reused()


def _find_remote_command(
    db: Session,
    *,
    charge_point: ChargePoint,
    action: str,
    payload: dict,
    idempotency_key: Optional[str],
) -> Optional[OutboxEvent]:
    command_key = _normalize_remote_command_key(idempotency_key, generate=False)
    if command_key is None:
        return None
    existing = db.query(OutboxEvent).filter(
        OutboxEvent.tenant_id == charge_point.tenant_id,
        OutboxEvent.idempotency_key == f"remote-command:{command_key}",
    ).first()
    if existing:
        _validate_remote_command_match(
            existing,
            charge_point=charge_point,
            action=action,
            payload=payload,
        )
    return existing


def _record_remote_command(
    db: Session,
    *,
    charge_point: ChargePoint,
    admin,
    action: str,
    payload: dict,
    idempotency_key: Optional[str],
) -> tuple[OutboxEvent, bool]:
    command_key = _normalize_remote_command_key(idempotency_key, generate=True)
    assert command_key is not None
    stored_key = f"remote-command:{command_key}"
    existing = db.query(OutboxEvent).filter(
        OutboxEvent.tenant_id == charge_point.tenant_id,
        OutboxEvent.idempotency_key == stored_key,
    ).first()
    if existing:
        _validate_remote_command_match(
            existing,
            charge_point=charge_point,
            action=action,
            payload=payload,
        )
        return existing, False

    command_id = str(uuid.uuid4())
    event = OutboxService.enqueue(
        db,
        tenant_id=charge_point.tenant_id,
        aggregate_type="ChargePoint",
        aggregate_id=str(charge_point.id),
        event_type=f"{action}Requested",
        idempotency_key=stored_key,
        payload={
            "command_id": command_id,
            "charge_point_id": str(charge_point.id),
            "ocpp_identity": charge_point.ocpp_identity,
            **payload,
        },
    )
    db.add(AuditLog(
        tenant_id=charge_point.tenant_id,
        actor_id=admin.id,
        actor_type="admin",
        action=f"ocpp.{action}",
        resource_type="charge_point",
        resource_id=str(charge_point.id),
        after_data={"ocpp_identity": charge_point.ocpp_identity, **payload},
        audit_metadata={"command_id": command_id, "idempotency_key": command_key},
    ))
    db.commit()
    return event, True


def _store_remote_command_response(
    db: Session,
    event: OutboxEvent,
    response: "RemoteResponse",
) -> None:
    """Persist the first device response so an idempotent replay is truthful."""
    payload = dict(event.payload or {})
    payload["command_result"] = {
        "kind": "response",
        "success": response.success,
        "message": response.message,
        "details": response.details,
    }
    event.payload = payload
    event.status = "published" if response.success else "failed"
    event.last_error = None if response.success else response.message
    db.commit()


def _store_remote_command_error(
    db: Session,
    event: OutboxEvent,
    exc: HTTPException,
) -> None:
    """Persist the first HTTP failure, including offline charger failures."""
    payload = dict(event.payload or {})
    payload["command_result"] = {
        "kind": "http_error",
        "status_code": exc.status_code,
        "detail": exc.detail,
        "error_code": getattr(exc, "error_code", "HTTP_ERROR"),
    }
    event.payload = payload
    event.status = "failed"
    event.last_error = str(exc.detail)
    db.commit()


def _replay_remote_command(event: OutboxEvent) -> "RemoteResponse":
    """Return or raise the exact first recorded outcome for an idempotency key."""
    result = (event.payload or {}).get("command_result")
    if not result:
        raise HTTPException(status_code=409, detail="Original command outcome is not yet available")
    if result.get("kind") == "http_error":
        exc = HTTPException(
            status_code=result["status_code"],
            detail=result["detail"],
        )
        exc.error_code = result.get("error_code", "HTTP_ERROR")
        raise exc

    details = dict(result.get("details") or {})
    details.update({
        "command_id": (event.payload or {}).get("command_id"),
        "idempotent_replay": True,
    })
    return RemoteResponse(
        success=bool(result.get("success")),
        message=result.get("message") or "远程命令失败",
        details=details,
    )


async def _execute_remote_command(db: Session, event: OutboxEvent, sender) -> "RemoteResponse":
    try:
        response = await sender()
    except HTTPException as exc:
        _store_remote_command_error(db, event, exc)
        raise
    except Exception as exc:
        failure = HTTPException(status_code=502, detail="Failed to send remote command")
        _store_remote_command_error(db, event, failure)
        raise failure from exc
    _store_remote_command_response(db, event, response)
    return response


class RemoteStartRequest(StrictRequestModel):
    charge_point_id: str = Field(..., min_length=1, max_length=64)
    connector_id: int = Field(..., ge=1, le=255)
    operation_reason: str = Field(..., min_length=3, max_length=200)
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=255)

    @field_validator("operation_reason")
    @classmethod
    def normalize_operation_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("operation_reason must contain at least 3 non-space characters")
        return normalized


class RemoteStopSessionRequest(StrictRequestModel):
    session_id: uuid.UUID
    operation_reason: str = Field(..., min_length=3, max_length=200)

    @field_validator("operation_reason", mode="before")
    @classmethod
    def normalize_operation_reason(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class ChangeConfigurationRequest(StrictRequestModel):
    charge_point_id: str = Field(..., min_length=1, max_length=64)
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., max_length=500)


class GetConfigurationRequest(StrictRequestModel):
    charge_point_id: str = Field(..., min_length=1, max_length=64)
    keys: Optional[List[str]] = Field(None, max_length=100)


class ResetRequest(StrictRequestModel):
    charge_point_id: str = Field(..., min_length=1, max_length=64)
    type: Literal["Soft", "Hard"]
    operation_reason: str = Field(..., min_length=3, max_length=200)

    @field_validator("operation_reason", mode="before")
    @classmethod
    def normalize_operation_reason(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class UnlockConnectorRequest(StrictRequestModel):
    charge_point_id: str = Field(..., min_length=1, max_length=64)
    connector_id: int = Field(..., ge=1, le=255)
    operation_reason: str = Field(..., min_length=3, max_length=200)

    @field_validator("operation_reason", mode="before")
    @classmethod
    def normalize_operation_reason(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class RemoteResponse(BaseModel):
    success: bool
    message: str
    details: Optional[dict] = None


def _remote_start_conflict(code: str, message: str) -> HTTPException:
    exc = HTTPException(status_code=409, detail=message)
    exc.error_code = code
    return exc


def _operations_id_tag(admin) -> str:
    admin_id_prefix = str(admin.id).replace("-", "")[:16]
    return f"OPS-{admin_id_prefix}"


async def send_remote_start(charge_point_identity: str, id_tag: str, connector_id: int) -> RemoteResponse:
    if not check_charger_connection(charge_point_identity):
        raise ChargerNotConnectedException(charge_point_identity)
    inflight_key = (charge_point_identity, connector_id)
    async with _remote_start_guard:
        expires_at = _remote_start_inflight.get(inflight_key, 0)
        if expires_at > time.monotonic():
            return RemoteResponse(
                success=False,
                message="远程启动被拒绝：该连接器已有启动流程进行中",
                details={
                    "device_status": "Rejected",
                    "workflow_status": "start_in_progress",
                },
            )
        _remote_start_inflight[inflight_key] = (
            time.monotonic() + _REMOTE_START_INFLIGHT_SECONDS
        )
    payload = {"connectorId": connector_id, "idTag": id_tag}
    try:
        if settings.enable_distributed:
            result = await message_handler.send_to_charger(charge_point_identity, "RemoteStartTransaction", payload)
        else:
            result = await message_handler.send_call(charge_point_identity, "RemoteStartTransaction", payload)
    except Exception:
        mark_remote_start_finished(charge_point_identity, connector_id)
        raise
    device_result = result.get("data", result) if isinstance(result, dict) else {}
    device_status = device_result.get("status") if isinstance(device_result, dict) else None
    error_text = str(result.get("error", "")) if isinstance(result, dict) else ""
    if not device_status and "timeout" in error_text.lower():
        mark_remote_start_finished(charge_point_identity, connector_id)
        exc = HTTPException(
            status_code=504,
            detail="Timed out waiting for RemoteStartTransaction response",
        )
        exc.error_code = "OCPP_RESPONSE_TIMEOUT"
        raise exc
    success = bool(result.get("success")) and device_status == "Accepted"
    if not success:
        mark_remote_start_finished(charge_point_identity, connector_id)
    details = dict(result) if isinstance(result, dict) else {"transport_result": result}
    details["device_status"] = device_status
    details["workflow_status"] = "pending" if success else "not_started"
    return RemoteResponse(success=success, message="远程启动已被充电桩接受" if success else "远程启动被拒绝", details=details)


async def send_remote_stop(charge_point_identity: str, transaction_id: int) -> RemoteResponse:
    if not check_charger_connection(charge_point_identity):
        raise ChargerNotConnectedException(charge_point_identity)
    payload = {"transactionId": transaction_id}
    if settings.enable_distributed:
        result = await message_handler.send_to_charger(charge_point_identity, "RemoteStopTransaction", payload)
    else:
        result = await message_handler.send_call(charge_point_identity, "RemoteStopTransaction", payload)
    device_result = result.get("data", result) if isinstance(result, dict) else {}
    device_status = device_result.get("status") if isinstance(device_result, dict) else None
    success = bool(result.get("success")) and device_status == "Accepted"
    details = dict(result) if isinstance(result, dict) else {"transport_result": result}
    details["device_status"] = device_status
    details["workflow_status"] = "pending" if success else "not_stopped"
    return RemoteResponse(success=success, message="远程停止已被充电桩接受" if success else "远程停止被拒绝", details=details)


@router.post("/remote-start-transaction", response_model=RemoteResponse, summary="远程启动充电")
async def remote_start(
    req: RemoteStartRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    admin=Depends(require_permission("chargers.control")),
    db: Session = Depends(get_db),
) -> RemoteResponse:
    """远程启动充电事务"""
    if idempotency_key and req.idempotency_key and idempotency_key != req.idempotency_key:
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key header and idempotency_key body field must match",
        )
    command_idempotency_key = idempotency_key or req.idempotency_key
    operations_id_tag = _operations_id_tag(admin)
    logger.info(
        f"[API] POST /api/v1/ocpp_control/remoteStart | "
        f"充电桩ID: {req.charge_point_id} | "
        f"连接器ID: {req.connector_id} | "
        f"运维管理员ID: {admin.id}"
    )
    cp = _scoped_charge_point(db, req.charge_point_id)
    command_payload = {
        "operation_reason": req.operation_reason,
        "connector_id": req.connector_id,
        "id_tag": operations_id_tag,
    }
    existing = _find_remote_command(
        db,
        charge_point=cp,
        action="remote_start",
        payload=command_payload,
        idempotency_key=command_idempotency_key,
    )
    if existing:
        return _replay_remote_command(existing)

    try:
        require_charge_point_operational(cp)
    except AssetNotOperationalError as exc:
        raise _remote_start_conflict(exc.code, exc.message) from exc
    if not check_charger_connection(cp.ocpp_identity):
        raise _remote_start_conflict(
            "CHARGER_OFFLINE",
            "Charge point WebSocket is offline",
        )

    evse = db.query(EVSE).filter(
        EVSE.tenant_id == cp.tenant_id,
        EVSE.charge_point_id == cp.id,
        EVSE.evse_id == req.connector_id,
    ).first()
    if not evse:
        raise HTTPException(status_code=422, detail="connector_id does not exist on this charge point")

    evse_status = db.query(EVSEStatus).filter(
        EVSEStatus.tenant_id == cp.tenant_id,
        EVSEStatus.charge_point_id == cp.id,
        EVSEStatus.evse_id == evse.id,
    ).first()
    if not evse_status or not evse_status.status or evse_status.status == "Unknown":
        raise _remote_start_conflict(
            "CONNECTOR_STATUS_UNKNOWN",
            "Connector status is unknown",
        )
    if evse_status.status != "Available":
        raise _remote_start_conflict(
            "CONNECTOR_NOT_AVAILABLE",
            "Connector is not available",
        )

    active_session = db.query(ChargingSession).filter(
        ChargingSession.tenant_id == cp.tenant_id,
        ChargingSession.charge_point_id == cp.id,
        ChargingSession.evse_id == evse.id,
        ChargingSession.status == "ongoing",
        ChargingSession.end_time.is_(None),
    ).first()
    if active_session:
        raise _remote_start_conflict(
            "CONNECTOR_SESSION_ACTIVE",
            "Connector already has an ongoing charging session",
        )

    event, is_new = _record_remote_command(
        db, charge_point=cp, admin=admin, action="remote_start",
        payload=command_payload,
        idempotency_key=command_idempotency_key,
    )
    if not is_new:
        return _replay_remote_command(event)
    return await _execute_remote_command(
        db,
        event,
        lambda: send_remote_start(
            cp.ocpp_identity,
            operations_id_tag,
            req.connector_id,
        ),
    )


@router.post("/remote-stop-session", response_model=RemoteResponse, summary="远程停止充电会话")
async def remote_stop_session(
    req: RemoteStopSessionRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    admin=Depends(require_permission("chargers.control")),
    db: Session = Depends(get_db),
) -> RemoteResponse:
    """通过当前租户的业务会话解析并停止 OCPP 事务。"""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    logger.info(
        f"[API] POST /api/v1/ocpp/remote-stop-session | "
        f"会话ID: {req.session_id} | "
        f"运维管理员ID: {admin.id}"
    )
    scoped_session = (
        db.query(ChargingSession, ChargePoint)
        .join(ChargePoint, ChargePoint.id == ChargingSession.charge_point_id)
        .filter(
            ChargingSession.id == req.session_id,
            ChargingSession.tenant_id == tenant_id,
            ChargePoint.tenant_id == tenant_id,
        )
        .first()
    )
    if not scoped_session:
        raise HTTPException(status_code=404, detail="Charging session not found")

    active_session, cp = scoped_session
    if active_session.status != "ongoing" or active_session.end_time is not None:
        raise HTTPException(status_code=422, detail="Charging session is not ongoing")

    event, is_new = _record_remote_command(
        db, charge_point=cp, admin=admin, action="remote_stop",
        payload={
            "operation_reason": req.operation_reason,
            "transaction_id": active_session.transaction_id,
            "session_id": str(active_session.id),
        },
        idempotency_key=idempotency_key,
    )
    if not is_new:
        return _replay_remote_command(event)
    return await _execute_remote_command(
        db,
        event,
        lambda: send_remote_stop(cp.ocpp_identity, active_session.transaction_id),
    )


@router.post("/change-configuration", response_model=RemoteResponse, summary="更改配置")
async def change_configuration(
    req: ChangeConfigurationRequest,
    admin=Depends(require_permission("chargers.control")),
    db: Session = Depends(get_db),
) -> RemoteResponse:
    """更改充电桩配置参数"""
    cp = _scoped_charge_point(db, req.charge_point_id)
    logger.info(
        f"[API] POST /api/v1/ocpp/change-configuration | "
        f"充电桩ID: {req.charge_point_id} | "
        f"配置键: {req.key} | "
        f"配置值: {req.value}"
    )
    
    # 检查连接状态（同时检查 WebSocket 和 MQTT）
    is_connected = check_charger_connection(cp.ocpp_identity)
    
    if not is_connected:
        logger.warning(f"[API] 更改配置失败: 充电桩 {cp.ocpp_identity} 未连接")
        raise ChargerNotConnectedException(cp.ocpp_identity)
    
    if settings.enable_distributed:
        result = await message_handler.send_to_charger(
            cp.ocpp_identity,
            "ChangeConfiguration",
            {"key": req.key, "value": req.value}
        )
    else:
        result = await message_handler.send_call(
            cp.ocpp_identity,
            "ChangeConfiguration",
            {"key": req.key, "value": req.value}
        )
    
    success = result.get("success", False)
    return RemoteResponse(
        success=success,
        message="配置更改请求已发送" if success else "配置更改失败",
        details=result
    )


@router.post("/get-configuration", response_model=RemoteResponse, summary="获取配置")
async def get_configuration(
    req: GetConfigurationRequest,
    admin=Depends(require_permission("chargers.read")),
    db: Session = Depends(get_db),
) -> RemoteResponse:
    """获取充电桩配置参数"""
    cp = _scoped_charge_point(db, req.charge_point_id)
    logger.info(
        f"[API] POST /api/v1/ocpp/get-configuration | "
        f"充电桩ID: {req.charge_point_id} | "
        f"配置键: {req.keys or '全部'}"
    )
    
    # 检查连接状态（同时检查 WebSocket 和 MQTT）
    is_connected = check_charger_connection(cp.ocpp_identity)
    
    if not is_connected:
        logger.warning(f"[API] 获取配置失败: 充电桩 {cp.ocpp_identity} 未连接")
        raise ChargerNotConnectedException(cp.ocpp_identity)
    
    payload = {"key": req.keys} if req.keys else {}
    if settings.enable_distributed:
        result = await message_handler.send_to_charger(
            cp.ocpp_identity,
            "GetConfiguration",
            payload
        )
    else:
        result = await message_handler.send_call(
            cp.ocpp_identity,
            "GetConfiguration",
            payload
        )
    
    success = result.get("success", False)
    return RemoteResponse(
        success=success,
        message="获取配置请求已发送" if success else "获取配置失败",
        details=result
    )


@router.post("/reset", response_model=RemoteResponse, summary="重置充电桩")
async def reset_charger(
    req: ResetRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    admin=Depends(require_permission("chargers.control")),
    db: Session = Depends(get_db),
) -> RemoteResponse:
    """重置充电桩（软重启或硬重启）"""
    logger.info(
        f"[API] POST /api/v1/ocpp/reset | "
        f"充电桩ID: {req.charge_point_id} | "
        f"重置类型: {req.type}"
    )
    cp = _scoped_charge_point(db, req.charge_point_id)
    event, is_new = _record_remote_command(
        db, charge_point=cp, admin=admin, action="reset",
        payload={"operation_reason": req.operation_reason, "type": req.type},
        idempotency_key=idempotency_key,
    )
    if not is_new:
        return _replay_remote_command(event)

    async def send_reset() -> RemoteResponse:
        if not check_charger_connection(cp.ocpp_identity):
            raise ChargerNotConnectedException(cp.ocpp_identity)
        if settings.enable_distributed:
            result = await message_handler.send_to_charger(
                cp.ocpp_identity,
                "Reset",
                {"type": req.type}
            )
        else:
            result = await message_handler.send_call(
                cp.ocpp_identity,
                "Reset",
                {"type": req.type}
            )
        success = result.get("success", False)
        return RemoteResponse(
            success=success,
            message="重置请求已发送" if success else "重置失败",
            details=result,
        )

    return await _execute_remote_command(db, event, send_reset)


@router.post("/unlock-connector", response_model=RemoteResponse, summary="解锁连接器")
async def unlock_connector(
    req: UnlockConnectorRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    admin=Depends(require_permission("chargers.control")),
    db: Session = Depends(get_db),
) -> RemoteResponse:
    """解锁连接器"""
    cp = _scoped_charge_point(db, req.charge_point_id)
    logger.info(
        f"[API] POST /api/v1/ocpp/unlock-connector | "
        f"充电桩ID: {req.charge_point_id} | "
        f"连接器ID: {req.connector_id}"
    )

    connector = db.query(EVSE).filter(
        EVSE.tenant_id == cp.tenant_id,
        EVSE.charge_point_id == cp.id,
        EVSE.evse_id == req.connector_id,
    ).first()
    if not connector:
        raise HTTPException(
            status_code=422,
            detail="connector_id does not exist on this charge point",
        )

    event, is_new = _record_remote_command(
        db,
        charge_point=cp,
        admin=admin,
        action="unlock_connector",
        payload={
            "operation_reason": req.operation_reason,
            "connector_id": req.connector_id,
        },
        idempotency_key=idempotency_key,
    )
    if not is_new:
        return _replay_remote_command(event)

    async def send_unlock() -> RemoteResponse:
        if not check_charger_connection(cp.ocpp_identity):
            raise ChargerNotConnectedException(cp.ocpp_identity)
        if settings.enable_distributed:
            result = await message_handler.send_to_charger(
                cp.ocpp_identity,
                "UnlockConnector",
                {"connectorId": req.connector_id},
            )
        else:
            result = await message_handler.send_call(
                cp.ocpp_identity,
                "UnlockConnector",
                {"connectorId": req.connector_id},
            )
        success = result.get("success", False)
        return RemoteResponse(
            success=success,
            message="解锁连接器请求已发送" if success else "解锁连接器失败",
            details=result,
        )

    return await _execute_remote_command(db, event, send_unlock)


@router.get("/connected", summary="获取所有已连接的充电桩列表")
async def get_connected_chargers(
    admin=Depends(require_permission("chargers.read")),
    db: Session = Depends(get_db),
) -> dict:
    """获取所有已连接的充电桩ID列表"""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    logger.info("[API] GET /api/v1/ocpp/connected | 获取已连接充电桩列表")
    
    connected_ids = []
    
    try:
        # 从connection_manager获取已连接的充电桩
        if hasattr(connection_manager, 'get_all_charger_ids'):
            connected_ids = connection_manager.get_all_charger_ids()
            logger.info(f"[API] 从connection_manager获取到 {len(connected_ids)} 个已连接充电桩")
    except Exception as e:
        logger.warning(f"[API] 从connection_manager获取连接列表失败: {e}")
    
    # 从charger_websockets获取已连接的充电桩（WebSocket连接的主要存储位置）
    ws_connected = []
    try:
        import sys
        main_module = sys.modules.get('app.main')
        if main_module and hasattr(main_module, 'charger_websockets'):
            charger_websockets = getattr(main_module, 'charger_websockets')
            ws_connected = list(charger_websockets.keys())
            logger.info(f"[API] 从charger_websockets获取到 {len(ws_connected)} 个已连接充电桩")
    except Exception as e:
        logger.warning(f"[API] 从charger_websockets获取连接列表失败: {e}")
        ws_connected = []
    
    # 合并连接列表（去重，优先使用charger_websockets）
    all_connected = set(ws_connected + connected_ids)
    scoped_connected = {
        identity for (identity,) in db.query(ChargePoint.ocpp_identity).filter(
            ChargePoint.tenant_id == tenant_id,
            ChargePoint.ocpp_identity.in_(all_connected),
        ).all()
    } if all_connected else set()
    
    logger.info(f"[API] GET /api/v1/ocpp/connected 成功 | 总共 {len(scoped_connected)} 个已连接充电桩")
    
    return {
        "connected_chargers": sorted(scoped_connected),
        "count": len(scoped_connected),
        "sources": {
            "websocket": sorted(scoped_connected)
        }
    }
