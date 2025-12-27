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

settings = get_settings()
logger = get_logger("ocpp_csms")

# 根据配置选择使用分布式或单机模式
if settings.enable_distributed:
    from app.ocpp.message_router import message_router as message_handler
    from app.ocpp.distributed_connection_manager import distributed_connection_manager as connection_manager
else:
    from app.ocpp.message_sender import message_sender as message_handler
    from app.ocpp.connection_manager import connection_manager

# 导入 transport_manager 用于检查 MQTT 连接
try:
    from app.ocpp.transport_manager import transport_manager, TransportType
    TRANSPORT_MANAGER_AVAILABLE = True
except ImportError:
    TRANSPORT_MANAGER_AVAILABLE = False
    transport_manager = None
    TransportType = None

router = APIRouter()


def check_charger_connection(charge_point_id: str) -> bool:
    """
    检查充电桩连接状态
    同时检查 WebSocket (charger_websockets, connection_manager, transport_manager) 和 MQTT (transport_manager) 连接
    只要有一个连接就返回 True
    """
    is_connected_ws = False
    is_connected_mqtt = False
    
    # 首先检查 charger_websockets 字典（WebSocket连接的主要存储位置）
    try:
        # 动态导入 charger_websockets（避免循环导入）
        import sys
        main_module = sys.modules.get('app.main')
        if main_module and hasattr(main_module, 'charger_websockets'):
            charger_websockets = getattr(main_module, 'charger_websockets')
            if charge_point_id in charger_websockets:
                ws = charger_websockets[charge_point_id]
                # 简单检查WebSocket对象是否存在（FastAPI WebSocket对象）
                if ws is not None:
                    # 尝试检查连接状态（FastAPI WebSocket使用client_state）
                    try:
                        # FastAPI WebSocket 使用 client_state 属性
                        if hasattr(ws, 'client_state'):
                            # 0 = CONNECTING, 1 = CONNECTED, 2 = DISCONNECTED
                            if ws.client_state == 1:  # CONNECTED
                                is_connected_ws = True
                                logger.debug(f"[API] charger_websockets中找到有效连接: {charge_point_id}")
                            else:
                                logger.debug(f"[API] charger_websockets中的连接状态异常: {charge_point_id}, state={ws.client_state}")
                        else:
                            # 如果没有client_state属性，假设连接有效（向后兼容）
                            is_connected_ws = True
                            logger.debug(f"[API] charger_websockets中找到连接（无法验证状态）: {charge_point_id}")
                    except Exception as e:
                        # 如果检查状态失败，假设连接有效（向后兼容）
                        is_connected_ws = True
                        logger.debug(f"[API] charger_websockets中找到连接（状态检查失败，假设有效）: {charge_point_id}, 错误: {e}")
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
    
    # 检查 MQTT 连接（transport_manager）
    if TRANSPORT_MANAGER_AVAILABLE and transport_manager and TransportType:
        try:
            if hasattr(transport_manager, 'adapters') and transport_manager.adapters:
                # 只检查MQTT适配器，不包括WebSocket
                mqtt_adapter = transport_manager.adapters.get(TransportType.MQTT)
                if mqtt_adapter and hasattr(mqtt_adapter, 'is_connected'):
                    is_connected_mqtt = mqtt_adapter.is_connected(charge_point_id)
                    logger.debug(f"[API] transport_manager MQTT适配器.is_connected({charge_point_id}) = {is_connected_mqtt}")
                else:
                    # 如果没有MQTT适配器，使用transport_manager.is_connected（它会检查所有适配器）
                    is_connected_mqtt = transport_manager.is_connected(charge_point_id)
                    logger.debug(f"[API] transport_manager.is_connected({charge_point_id}) = {is_connected_mqtt}, adapters: {list(transport_manager.adapters.keys())}")
        except Exception as e:
            logger.warning(f"[API] transport_manager.is_connected() 检查失败: {e}")
    
    # 只要有一个连接就认为已连接
    is_connected = is_connected_ws or is_connected_mqtt
    logger.info(f"[API] 充电桩 {charge_point_id} 连接状态: WebSocket={is_connected_ws}, MQTT={is_connected_mqtt}, 最终={is_connected}")
    return is_connected


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
    
    # 从transport_manager获取MQTT连接的充电桩
    mqtt_connected = []
    if TRANSPORT_MANAGER_AVAILABLE and transport_manager:
        try:
            if hasattr(transport_manager, 'adapters'):
                for transport_type, adapter in transport_manager.adapters.items():
                    if transport_type.value == "mqtt" and hasattr(adapter, '_connected_chargers'):
                        mqtt_connected = list(adapter._connected_chargers)
                        logger.info(f"[API] 从MQTT适配器获取到 {len(mqtt_connected)} 个已连接充电桩")
                        break
        except Exception as e:
            logger.warning(f"[API] 从transport_manager获取连接列表失败: {e}")
    
    # 合并连接列表（去重）
    all_connected = list(set(connected_ids + mqtt_connected))
    
    logger.info(f"[API] GET /api/v1/ocpp/connected 成功 | 总共 {len(all_connected)} 个已连接充电桩")
    
    return {
        "connected_chargers": all_connected,
        "count": len(all_connected),
        "sources": {
            "websocket": connected_ids,
            "mqtt": mqtt_connected
        }
    }


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
    
    # 从transport_manager获取MQTT连接的充电桩
    mqtt_connected = []
    if TRANSPORT_MANAGER_AVAILABLE and transport_manager:
        try:
            if hasattr(transport_manager, 'adapters'):
                for transport_type, adapter in transport_manager.adapters.items():
                    if transport_type.value == "mqtt" and hasattr(adapter, '_connected_chargers'):
                        mqtt_connected = list(adapter._connected_chargers)
                        logger.info(f"[API] 从MQTT适配器获取到 {len(mqtt_connected)} 个已连接充电桩")
                        break
        except Exception as e:
            logger.warning(f"[API] 从transport_manager获取连接列表失败: {e}")
    
    # 合并连接列表（去重）
    all_connected = list(set(connected_ids + mqtt_connected))
    
    logger.info(f"[API] GET /api/v1/ocpp/connected 成功 | 总共 {len(all_connected)} 个已连接充电桩")
    
    return {
        "connected_chargers": all_connected,
        "count": len(all_connected),
        "sources": {
            "websocket": connected_ids,
            "mqtt": mqtt_connected
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
        
        # 如果是 MQTT 适配器，显示连接的充电桩列表
        for transport_type, adapter in transport_manager.adapters.items():
            if transport_type.value == "mqtt" and hasattr(adapter, '_connected_chargers'):
                result["connection_status"]["mqtt_connected_chargers"] = list(adapter._connected_chargers)
                result["connection_status"]["mqtt_is_connected"] = charge_point_id in adapter._connected_chargers
    
    result["connection_status"]["connection_manager"] = connection_manager.is_connected(charge_point_id)
    result["connection_status"]["transport_manager"] = transport_manager.is_connected(charge_point_id) if TRANSPORT_MANAGER_AVAILABLE and transport_manager and hasattr(transport_manager, 'adapters') and transport_manager.adapters else False
    
    return result
