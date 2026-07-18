#
# 跨服务器消息路由
# 处理分布式环境下的消息转发
#

import json
import asyncio
from typing import Dict, Any, Optional
from app.ocpp.distributed_connection_manager import distributed_connection_manager
from app.core.logging_config import get_logger
from app.core.exceptions import ChargerNotConnectedException

logger = get_logger("ocpp_csms")


class MessageRouter:
    """跨服务器消息路由器
    
    支持场景：
    1. 充电桩连接到服务器A
    2. API请求到达服务器B
    3. 服务器B通过消息路由转发到服务器A
    4. 服务器A将消息发送给充电桩
    """
    
    @staticmethod
    async def send_to_charger(
        charger_id: str,
        action: str,
        payload: Dict[str, Any],
        timeout: float = 5.0
    ) -> Dict[str, Any]:
        """发送消息到充电桩（支持跨服务器）"""
        manager = distributed_connection_manager
        
        # 检查是否在本服务器连接
        if manager.is_connected_locally(charger_id):
            # 本地连接，直接发送
            return await MessageRouter._send_local(charger_id, action, payload, timeout)
        
        # 检查是否在其他服务器连接
        server_id = manager.get_connection_server(charger_id)
        if server_id:
            # 在其他服务器，通过消息队列转发
            return await MessageRouter._send_remote(charger_id, action, payload, server_id, timeout)
        
        # 未连接
        raise ChargerNotConnectedException(charger_id)
    
    @staticmethod
    async def _send_local(
        charger_id: str,
        action: str,
        payload: Dict[str, Any],
        timeout: float
    ) -> Dict[str, Any]:
        """发送到本地连接的充电桩"""
        from app.ocpp.message_sender import message_sender
        
        # 使用本地消息发送器
        return await message_sender.send_call(charger_id, action, payload, timeout)
    
    @staticmethod
    async def _send_remote(
        charger_id: str,
        action: str,
        payload: Dict[str, Any],
        server_id: str,
        timeout: float
    ) -> Dict[str, Any]:
        """通过消息队列发送到远程服务器"""
        import uuid
        from datetime import datetime, timezone
        
        manager = distributed_connection_manager
        message_id = str(uuid.uuid4())
        
        # 创建消息
        message = {
            "message_id": message_id,
            "charger_id": charger_id,
            "target_server": server_id,
            "action": action,
            "payload": payload,
            "from_server": manager.server_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timeout": timeout,
        }
        
        # 写入可靠 Stream；消费者重启后可从 pending 消息继续处理。
        manager.redis_client.xadd(
            manager.ROUTE_STREAM,
            {"message": json.dumps(message)},
            maxlen=100000,
            approximate=True,
        )
        
        # 等待响应（通过Redis键值对）
        response_key = f"ocpp:response:{message_id}"
        
        try:
            # 轮询等待响应（最多timeout秒）
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                response = manager.redis_client.get(response_key)
                if response:
                    response_data = json.loads(response)
                    manager.redis_client.delete(response_key)  # 清理
                    return response_data
                await asyncio.sleep(0.1)  # 等待100ms后重试
            
            # 超时
            manager.redis_client.delete(response_key)
            return {
                "success": False,
                "error": "Timeout waiting for remote response"
            }
        except Exception as e:
            logger.error(f"远程消息路由失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    async def handle_routed_message_async(charger_id: str, message: dict):
        """在 FastAPI 主事件循环中处理来自其他服务器的路由消息。"""
        from app.ocpp.message_sender import message_sender
        
        action = message.get("action")
        payload = message.get("payload")
        message_id = message.get("message_id")
        timeout = message.get("timeout", 5.0)
        
        try:
            result = await message_sender.send_call(charger_id, action, payload, timeout)
        except Exception as e:
            logger.error(f"处理路由消息失败: {e}", exc_info=True)
            result = {"success": False, "error": str(e)}

        response_key = f"ocpp:response:{message_id}"
        distributed_connection_manager.redis_client.setex(
            response_key,
            int(timeout) + 1,
            json.dumps(result),
        )

    @staticmethod
    def handle_routed_message(charger_id: str, message: dict, loop=None):
        """兼容同步调用方；跨线程时把任务投递到 FastAPI 主事件循环。"""
        target_loop = loop
        if target_loop is None:
            try:
                target_loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.error("无法处理 OCPP 路由消息：缺少运行中的 asyncio loop")
                return
        if target_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                MessageRouter.handle_routed_message_async(charger_id, message),
                target_loop,
            )


# 全局消息路由器实例
message_router = MessageRouter()
