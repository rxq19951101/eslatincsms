#
# OCPP消息发送
# 负责从CSMS发送消息到充电桩
#

import asyncio
import json
from typing import Dict, Any
from fastapi import HTTPException
from app.ocpp.connection_manager import connection_manager
import logging

logger = logging.getLogger("ocpp_csms")


class OCPPMessageSender:
    """OCPP消息发送器"""
    
    @staticmethod
    async def send_call(
        charger_id: str, 
        action: str, 
        payload: Dict[str, Any], 
        timeout: float = 5.0
    ) -> Dict[str, Any]:
        """
        发送OCPP调用从CSMS到充电桩，并等待响应。
        优先使用 transport_manager（支持 MQTT 和 WebSocket），如果没有则使用 WebSocket。
        返回响应数据或错误信息。
        """
        # 优先使用 transport_manager（支持 MQTT 和 WebSocket）
        try:
            from app.ocpp.transport_manager import transport_manager, TransportType
            if hasattr(transport_manager, 'adapters') and transport_manager.adapters:
                if transport_manager.is_connected(charger_id):
                    logger.info(f"[{charger_id}] message_sender.send_call 通过 transport_manager 发送: {action}")
                    result = await transport_manager.send_message(
                        charger_id,
                        action,
                        payload,
                        preferred_transport=TransportType.MQTT,
                        timeout=timeout
                    )
                    return {"success": True, "data": result, "transport": "MQTT"}
        except Exception as e:
            logger.warning(f"[{charger_id}] transport_manager 发送失败: {e}，回退到 WebSocket")
        
        # Fallback: 使用 transport_manager 的 WebSocket 适配器
        try:
            from app.ocpp.transport_manager import TransportType
            if transport_manager and hasattr(transport_manager, 'adapters'):
                ws_adapter = transport_manager.adapters.get(TransportType.WEBSOCKET)
                if ws_adapter and transport_manager.is_connected(charger_id):
                    logger.info(f"[{charger_id}] message_sender.send_call 通过 transport_manager WebSocket 发送: {action}")
                    result = await transport_manager.send_message(
                        charger_id,
                        action,
                        payload,
                        preferred_transport=TransportType.WEBSOCKET,
                        timeout=timeout
                    )
                    return {"success": True, "data": result, "transport": "WebSocket"}
        except Exception as e:
            logger.warning(f"[{charger_id}] transport_manager WebSocket 发送失败: {e}")
        
        # 如果 transport_manager 不可用，抛出错误（不再直接使用 ws.receive_text()）
        raise HTTPException(
            status_code=404, 
            detail=f"Charger {charger_id} is not connected via any available transport"
        )


# 全局消息发送器实例
message_sender = OCPPMessageSender()

