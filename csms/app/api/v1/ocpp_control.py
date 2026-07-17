#
# OCPP控制API
# 提供OCPP远程控制功能（RemoteStart, RemoteStop等）
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.config import get_settings
from app.core.exceptions import ChargerNotConnectedException
from app.core.logging_config import get_logger
from app.database import SessionLocal
from app.database.models import ChargePoint
from app.services.outbox_service import OutboxService
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


def record_remote_command(charge_point_id: str, event_type: str, payload: dict) -> None:
    """把远程控制请求写入 Outbox，供异步发送/重试和审计使用。"""
    db = SessionLocal()
    try:
        cp = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
        if not cp or not cp.tenant_id:
            return
        command_id = str(uuid.uuid4())
        OutboxService.enqueue(
            db,
            tenant_id=cp.tenant_id,
            aggregate_type="ChargePoint",
            aggregate_id=charge_point_id,
            event_type=event_type,
            idempotency_key=f"remote-command:{command_id}",
            payload={"command_id": command_id, "charge_point_id": charge_point_id, **payload},
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("记录远程控制 Outbox 失败: charge_point_id=%s", charge_point_id)
    finally:
        db.close()


class RemoteStartRequest(BaseModel):
    chargePointId: str
    idTag: str
    connectorId: int = 1


class RemoteStopRequest(BaseModel):
    chargePointId: str
    transactionId: int


class ChangeConfigurationRequest(BaseModel):
    chargePointId: str
    key: str
    value: str


class GetConfigurationRequest(BaseModel):
    chargePointId: str
    keys: Optional[List[str]] = None


class ResetRequest(BaseModel):
    chargePointId: str
    type: str  # Hard or Soft


class UnlockConnectorRequest(BaseModel):
    chargePointId: str
    connectorId: int


class RemoteResponse(BaseModel):
    success: bool
    message: str
    details: dict = None


@router.post("/remote-start-transaction", response_model=RemoteResponse, summary="远程启动充电")
@router.post("/remoteStart", response_model=RemoteResponse, summary="远程启动充电")  # 兼容旧路径
async def remote_start(req: RemoteStartRequest) -> RemoteResponse:
    """远程启动充电事务"""
    logger.info(
        f"[API] POST /api/v1/ocpp_control/remoteStart | "
        f"充电桩ID: {req.chargePointId} | "
        f"用户标签: {req.idTag} | "
        f"连接器ID: {req.connectorId}"
    )
    
    # 检查连接状态（同时检查 WebSocket 和 MQTT）
    is_connected = check_charger_connection(req.chargePointId)
    
    if not is_connected:
        logger.warning(f"[API] 远程启动失败: 充电桩 {req.chargePointId} 未连接 (transport_manager可用: {TRANSPORT_MANAGER_AVAILABLE}, adapters: {len(transport_manager.adapters) if TRANSPORT_MANAGER_AVAILABLE and transport_manager and hasattr(transport_manager, 'adapters') else 0})")
        raise ChargerNotConnectedException(req.chargePointId)

    record_remote_command(req.chargePointId, "RemoteStartTransactionRequested", {
        "connector_id": req.connectorId, "id_tag": req.idTag,
    })
    
    # 使用消息处理器（支持分布式）
    if settings.enable_distributed:
        result = await message_handler.send_to_charger(
            req.chargePointId,
            "RemoteStartTransaction",
            {
                "connectorId": req.connectorId,
                "idTag": req.idTag
            }
        )
    else:
        result = await message_handler.send_call(
            req.chargePointId,
            "RemoteStartTransaction",
            {
                "connectorId": req.connectorId,
                "idTag": req.idTag
            }
        )
    
    success = result.get("success", False)
    logger.info(
        f"[API] POST /api/v1/ocpp_control/remoteStart {'成功' if success else '失败'} | "
        f"充电桩ID: {req.chargePointId} | "
        f"用户标签: {req.idTag}"
    )
    
    return RemoteResponse(
        success=success,
        message="远程启动请求已发送" if success else "远程启动失败",
        details=result
    )


@router.post("/remote-stop-transaction", response_model=RemoteResponse, summary="远程停止充电")
@router.post("/remoteStop", response_model=RemoteResponse, summary="远程停止充电")  # 兼容旧路径
async def remote_stop(req: RemoteStopRequest) -> RemoteResponse:
    """远程停止充电事务"""
    logger.info(
        f"[API] POST /api/v1/ocpp_control/remoteStop | "
        f"充电桩ID: {req.chargePointId} | "
        f"交易ID: {req.transactionId}"
    )
    
    # 检查连接状态（同时检查 WebSocket 和 MQTT）
    is_connected = check_charger_connection(req.chargePointId)
    
    if not is_connected:
        logger.warning(f"[API] 远程停止失败: 充电桩 {req.chargePointId} 未连接")
        raise ChargerNotConnectedException(req.chargePointId)

    record_remote_command(req.chargePointId, "RemoteStopTransactionRequested", {
        "transaction_id": req.transactionId,
    })
    
    # 使用消息处理器（支持分布式）
    if settings.enable_distributed:
        result = await message_handler.send_to_charger(
            req.chargePointId,
            "RemoteStopTransaction",
            {
                "transactionId": req.transactionId
            }
        )
    else:
        result = await message_handler.send_call(
            req.chargePointId,
            "RemoteStopTransaction",
            {
                "transactionId": req.transactionId
            }
        )
    
    success = result.get("success", False)
    logger.info(
        f"[API] POST /api/v1/ocpp_control/remoteStop {'成功' if success else '失败'} | "
        f"充电桩ID: {req.chargePointId} | "
        f"交易ID: {req.transactionId}"
    )
    
    return RemoteResponse(
        success=success,
        message="远程停止请求已发送" if success else "远程停止失败",
        details=result
    )


@router.post("/change-configuration", response_model=RemoteResponse, summary="更改配置")
@router.post("/changeConfiguration", response_model=RemoteResponse, summary="更改配置")  # 兼容旧路径
async def change_configuration(req: ChangeConfigurationRequest) -> RemoteResponse:
    """更改充电桩配置参数"""
    logger.info(
        f"[API] POST /api/v1/ocpp/change-configuration | "
        f"充电桩ID: {req.chargePointId} | "
        f"配置键: {req.key} | "
        f"配置值: {req.value}"
    )
    
    # 检查连接状态（同时检查 WebSocket 和 MQTT）
    is_connected = check_charger_connection(req.chargePointId)
    
    if not is_connected:
        logger.warning(f"[API] 更改配置失败: 充电桩 {req.chargePointId} 未连接")
        raise ChargerNotConnectedException(req.chargePointId)
    
    if settings.enable_distributed:
        result = await message_handler.send_to_charger(
            req.chargePointId,
            "ChangeConfiguration",
            {"key": req.key, "value": req.value}
        )
    else:
        result = await message_handler.send_call(
            req.chargePointId,
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
@router.post("/getConfiguration", response_model=RemoteResponse, summary="获取配置")  # 兼容旧路径
async def get_configuration(req: GetConfigurationRequest) -> RemoteResponse:
    """获取充电桩配置参数"""
    logger.info(
        f"[API] POST /api/v1/ocpp/get-configuration | "
        f"充电桩ID: {req.chargePointId} | "
        f"配置键: {req.keys or '全部'}"
    )
    
    # 检查连接状态（同时检查 WebSocket 和 MQTT）
    is_connected = check_charger_connection(req.chargePointId)
    
    if not is_connected:
        logger.warning(f"[API] 获取配置失败: 充电桩 {req.chargePointId} 未连接")
        raise ChargerNotConnectedException(req.chargePointId)
    
    payload = {"key": req.keys} if req.keys else {}
    if settings.enable_distributed:
        result = await message_handler.send_to_charger(
            req.chargePointId,
            "GetConfiguration",
            payload
        )
    else:
        result = await message_handler.send_call(
            req.chargePointId,
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
async def reset_charger(req: ResetRequest) -> RemoteResponse:
    """重置充电桩（软重启或硬重启）"""
    logger.info(
        f"[API] POST /api/v1/ocpp/reset | "
        f"充电桩ID: {req.chargePointId} | "
        f"重置类型: {req.type}"
    )
    
    # 检查连接状态（同时检查 WebSocket 和 MQTT）
    is_connected = check_charger_connection(req.chargePointId)
    
    if not is_connected:
        logger.warning(f"[API] 重置失败: 充电桩 {req.chargePointId} 未连接")
        raise ChargerNotConnectedException(req.chargePointId)
    
    if settings.enable_distributed:
        result = await message_handler.send_to_charger(
            req.chargePointId,
            "Reset",
            {"type": req.type}
        )
    else:
        result = await message_handler.send_call(
            req.chargePointId,
            "Reset",
            {"type": req.type}
        )
    
    success = result.get("success", False)
    return RemoteResponse(
        success=success,
        message="重置请求已发送" if success else "重置失败",
        details=result
    )


@router.post("/unlock-connector", response_model=RemoteResponse, summary="解锁连接器")
@router.post("/unlockConnector", response_model=RemoteResponse, summary="解锁连接器")  # 兼容旧路径
async def unlock_connector(req: UnlockConnectorRequest) -> RemoteResponse:
    """解锁连接器"""
    logger.info(
        f"[API] POST /api/v1/ocpp/unlock-connector | "
        f"充电桩ID: {req.chargePointId} | "
        f"连接器ID: {req.connectorId}"
    )
    
    # 检查连接状态（同时检查 WebSocket 和 MQTT）
    is_connected = check_charger_connection(req.chargePointId)
    
    if not is_connected:
        logger.warning(f"[API] 解锁连接器失败: 充电桩 {req.chargePointId} 未连接")
        raise ChargerNotConnectedException(req.chargePointId)
    
    if settings.enable_distributed:
        result = await message_handler.send_to_charger(
            req.chargePointId,
            "UnlockConnector",
            {"connectorId": req.connectorId}
        )
    else:
        result = await message_handler.send_call(
            req.chargePointId,
            "UnlockConnector",
            {"connectorId": req.connectorId}
        )
    
    success = result.get("success", False)
    return RemoteResponse(
        success=success,
        message="解锁连接器请求已发送" if success else "解锁连接器失败",
        details=result
    )


@router.get("/connected", summary="获取所有已连接的充电桩列表")
async def get_connected_chargers() -> dict:
    """获取所有已连接的充电桩ID列表"""
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
    all_connected = list(set(ws_connected + connected_ids))
    
    logger.info(f"[API] GET /api/v1/ocpp/connected 成功 | 总共 {len(all_connected)} 个已连接充电桩")
    
    return {
        "connected_chargers": all_connected,
        "count": len(all_connected),
        "sources": {
            "websocket": list(set(ws_connected + connected_ids))
        }
    }


@router.get("/debug/connection-status/{charge_point_id}", summary="调试：检查连接状态")
async def debug_connection_status(charge_point_id: str):
    """调试端点：检查充电桩的连接状态"""
    result = {
        "charge_point_id": charge_point_id,
        "transport_manager_available": TRANSPORT_MANAGER_AVAILABLE,
        "transport_manager_initialized": False,
        "adapters": {},
        "connection_status": {}
    }
    
    if TRANSPORT_MANAGER_AVAILABLE and transport_manager:
        result["transport_manager_initialized"] = hasattr(transport_manager, 'adapters') and len(transport_manager.adapters) > 0
        result["adapters"] = {
            str(k): {
                "type": str(k),
                "initialized": hasattr(v, 'is_connected'),
                "connected": v.is_connected(charge_point_id) if hasattr(v, 'is_connected') else False
            }
            for k, v in transport_manager.adapters.items()
        }
        
    result["connection_status"]["connection_manager"] = connection_manager.is_connected(charge_point_id)
    result["connection_status"]["transport_manager"] = transport_manager.is_connected(charge_point_id) if TRANSPORT_MANAGER_AVAILABLE and transport_manager and hasattr(transport_manager, 'adapters') and transport_manager.adapters else False
    
    return result
