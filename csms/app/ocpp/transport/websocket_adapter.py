#
# WebSocket 传输适配器
# 支持 OCPP 消息通过 WebSocket 传输
#

import json
import logging
from typing import Dict, Any
from fastapi import WebSocket
from .base import TransportAdapter, TransportType

logger = logging.getLogger("ocpp_csms")


class WebSocketAdapter(TransportAdapter):
    """WebSocket 传输适配器
    
    支持 OCPP 消息通过 WebSocket 双向传输
    """
    
    def __init__(self):
        super().__init__(TransportType.WEBSOCKET)
        self._connections: Dict[str, WebSocket] = {}
    
    async def start(self) -> None:
        """启动 WebSocket 服务（由 FastAPI 管理）"""
        logger.info("WebSocket 传输适配器已初始化")
    
    async def stop(self) -> None:
        """停止 WebSocket 服务"""
        # 关闭所有连接
        for charger_id, ws in list(self._connections.items()):
            try:
                await ws.close()
            except Exception:
                pass
        self._connections.clear()
        logger.info("WebSocket 传输适配器已停止")
    
    async def register_connection(self, charge_point_id: str, websocket: WebSocket) -> None:
        """注册 WebSocket 连接"""
        self._connections[charge_point_id] = websocket
        logger.info(f"[{charge_point_id}] WebSocket 连接已注册")
    
    async def unregister_connection(self, charge_point_id: str) -> None:
        """注销 WebSocket 连接"""
        if charge_point_id in self._connections:
            del self._connections[charge_point_id]
            logger.info(f"[{charge_point_id}] WebSocket 连接已注销")
    
    async def send_message(
        self,
        charge_point_id: str,
        action: str,
        payload: Dict[str, Any],
        timeout: float = 5.0
    ) -> Dict[str, Any]:
        """发送消息到充电桩（使用 OCPP 1.6 标准格式）"""
        ws = self._connections.get(charge_point_id)
        if not ws:
            raise ConnectionError(f"Charger {charge_point_id} is not connected via WebSocket")
        
        try:
            # 使用 OCPP 1.6 标准格式: [2, UniqueId, Action, Payload]
            import uuid
            unique_id = f"csms_{uuid.uuid4().hex[:16]}"
            message = [2, unique_id, action, payload]
            
            await ws.send_text(json.dumps(message))
            logger.info(f"[{charge_point_id}] -> WebSocket OCPP {action} (标准格式, UniqueId={unique_id})")
            
            # 等待响应（简化版本，实际应该使用消息ID匹配）
            import asyncio
            try:
                response_text = await asyncio.wait_for(ws.receive_text(), timeout=timeout)
                response = json.loads(response_text)
                
                # 解析 OCPP 标准格式响应
                if isinstance(response, list) and len(response) >= 3:
                    resp_message_type = response[0]
                    resp_unique_id = response[1]
                    resp_payload = response[2] if len(response) > 2 else {}
                    
                    if resp_message_type == 3:  # CALLRESULT
                        return {"success": True, "data": resp_payload, "unique_id": resp_unique_id}
                    elif resp_message_type == 4:  # CALLERROR
                        error_code = resp_payload if isinstance(resp_payload, str) else response[2] if len(response) > 2 else "UnknownError"
                        error_desc = response[3] if len(response) > 3 else "Unknown error"
                        return {"success": False, "error": error_code, "errorDescription": error_desc}
                
                return {"success": True, "data": response}
            except asyncio.TimeoutError:
                logger.warning(f"[{charge_point_id}] WebSocket 响应超时: {action}")
                return {"success": False, "error": "Timeout waiting for response"}
                
        except Exception as e:
            logger.error(f"[{charge_point_id}] WebSocket 发送错误: {e}", exc_info=True)
            raise
    
    def is_connected(self, charge_point_id: str) -> bool:
        """检查充电桩是否已连接"""
        return charge_point_id in self._connections

