#
# OCPP控制API
# 提供OCPP远程控制功能（RemoteStart, RemoteStop等）
#

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


class RemoteResponse(BaseModel):
    success: bool
    message: str
    details: dict = None


@router.post("/remoteStart", response_model=RemoteResponse, summary="远程启动充电")
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


@router.post("/remoteStop", response_model=RemoteResponse, summary="远程停止充电")
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

