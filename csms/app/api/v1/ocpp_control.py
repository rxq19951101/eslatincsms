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

router = APIRouter()


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
    
    if not connection_manager.is_connected(req.chargePointId):
        logger.warning(f"[API] 远程启动失败: 充电桩 {req.chargePointId} 未连接")
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
    
    if not connection_manager.is_connected(req.chargePointId):
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
    
    if not connection_manager.is_connected(req.chargePointId):
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
    
    if not connection_manager.is_connected(req.chargePointId):
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
    
    if not connection_manager.is_connected(req.chargePointId):
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
    
    if not connection_manager.is_connected(req.chargePointId):
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

