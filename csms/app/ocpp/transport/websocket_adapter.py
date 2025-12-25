#
# WebSocket 传输适配器
# 支持 OCPP 消息通过 WebSocket 传输
#

import json
import logging
import asyncio
import uuid
from typing import Dict, Any, Optional
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
        self._pending_responses: Dict[str, asyncio.Future] = {}  # unique_id -> Future
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
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
        
        # 创建 Future 用于等待响应
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        
        unique_id = f"csms_{uuid.uuid4().hex[:16]}"
        future = self._loop.create_future()
        self._pending_responses[unique_id] = future
        
        try:
            # 使用 OCPP 1.6 标准格式: [2, UniqueId, Action, Payload]
            message = [2, unique_id, action, payload]
            
            await ws.send_text(json.dumps(message))
            logger.info(f"[{charge_point_id}] -> WebSocket OCPP {action} (标准格式, UniqueId={unique_id})")
            
            # 等待响应（通过消息匹配机制）
            try:
                response_data = await asyncio.wait_for(future, timeout=timeout)
                logger.info(f"[{charge_point_id}] <- WebSocket OCPP {action} 响应 (UniqueId: {unique_id}): {response_data}")
                # 返回 data 字段（与 MQTT 适配器保持一致）
                if isinstance(response_data, dict) and "data" in response_data:
                    return response_data["data"]
                return response_data
            except asyncio.TimeoutError:
                self._pending_responses.pop(unique_id, None)
                logger.warning(f"[{charge_point_id}] WebSocket OCPP {action} 响应超时 (UniqueId: {unique_id}, 超时: {timeout}秒)")
                raise ConnectionError(f"等待 {action} 响应超时 ({timeout}秒)")
            except Exception as e:
                self._pending_responses.pop(unique_id, None)
                logger.error(f"[{charge_point_id}] WebSocket OCPP {action} 响应错误 (UniqueId: {unique_id}): {e}")
                raise
                
        except Exception as e:
            self._pending_responses.pop(unique_id, None)
            logger.error(f"[{charge_point_id}] WebSocket 发送错误: {e}", exc_info=True)
            raise
    
    def handle_response(self, unique_id: str, response_data: Dict[str, Any]):
        """处理来自充电桩的响应消息（由 WebSocket 端点调用）"""
        if unique_id in self._pending_responses:
            future = self._pending_responses.pop(unique_id)
            if not future.done():
                future.set_result(response_data)
            logger.debug(f"[WebSocketAdapter] 处理响应 (UniqueId: {unique_id})")
        else:
            logger.warning(f"[WebSocketAdapter] 收到未预期的响应 (UniqueId: {unique_id})")
    
    async def unregister_connection(self, charge_point_id: str) -> None:
        """注销 WebSocket 连接（清理待处理的响应）"""
        if charge_point_id in self._connections:
            del self._connections[charge_point_id]
            # 清理该充电桩的所有待处理响应
            keys_to_remove = [key for key in self._pending_responses.keys() if key.startswith(f"{charge_point_id}_")]
            for key in keys_to_remove:
                future = self._pending_responses.pop(key, None)
                if future and not future.done():
                    future.cancel()
            logger.info(f"[{charge_point_id}] WebSocket 连接已注销")
    
    def is_connected(self, charge_point_id: str) -> bool:
        """检查充电桩是否已连接"""
        return charge_point_id in self._connections

