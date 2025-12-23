#
# HTTP 传输适配器
# 支持 OCPP 消息通过 HTTP POST 传输
#

import json
import logging
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException
from .base import TransportAdapter, TransportType

logger = logging.getLogger("ocpp_csms")


class HTTPAdapter(TransportAdapter):
    """HTTP 传输适配器
    
    支持 OCPP 消息通过 HTTP POST 传输
    端点格式: POST /ocpp/{charger_id}
    """
    
    def __init__(self):
        super().__init__(TransportType.HTTP)
        self._charger_sessions: Dict[str, Dict[str, Any]] = {}
        self._pending_requests: Dict[str, Dict[str, Any]] = {}
    
    async def start(self) -> None:
        """启动 HTTP 服务（由 FastAPI 管理，这里只做初始化）"""
        logger.info("HTTP 传输适配器已初始化")
    
    async def stop(self) -> None:
        """停止 HTTP 服务"""
        self._charger_sessions.clear()
        self._pending_requests.clear()
        logger.info("HTTP 传输适配器已停止")
    
    async def send_message(
        self,
        charge_point_id: str,
        action: str,
        payload: Dict[str, Any],
        timeout: float = 5.0
    ) -> Dict[str, Any]:
        """发送消息到充电桩（HTTP 模式下需要充电桩主动轮询）"""
        # HTTP 是请求-响应模式，CSMS 无法主动推送
        # 需要将消息存储，等待充电桩轮询获取
        request_id = f"{charge_point_id}_{action}_{id(payload)}"
        
        # 存储待发送的消息
        if charge_point_id not in self._pending_requests:
            self._pending_requests[charge_point_id] = {}
        
        self._pending_requests[charge_point_id][request_id] = {
            "action": action,
            "payload": payload,
            "timestamp": None,
        }
        
        logger.info(f"[{charge_point_id}] HTTP 消息已排队: {action}")
        
        # 返回排队确认
        return {
            "success": True,
            "message": "Message queued, waiting for charger to poll",
            "request_id": request_id
        }
    
    def is_connected(self, charge_point_id: str) -> bool:
        """检查充电桩是否已连接（HTTP 模式下基于最近请求时间）"""
        if charge_point_id in self._charger_sessions:
            # 检查会话是否过期（例如 5 分钟内没有请求）
            session = self._charger_sessions[charge_point_id]
            # 这里可以添加时间检查逻辑
            return True
        return False
    
    async def handle_http_request(
        self,
        charge_point_id: str,
        request: Request
    ) -> Dict[str, Any]:
        """处理 HTTP 请求
        
        充电桩通过 POST 发送 OCPP 消息
        同时可以 GET 获取待处理的 CSMS 消息
        """
        if request.method == "POST":
            # 充电桩发送消息
            try:
                body = await request.json()
                
                # 支持两种格式：
                # 1. OCPP 1.6 标准格式: [MessageType, UniqueId, Action, Payload]
                # 2. 简化格式: {"action": "...", "payload": {...}}
                unique_id = None
                is_ocpp_standard_format = False
                
                if isinstance(body, list) and len(body) >= 4:
                    # OCPP 1.6 标准格式
                    message_type = body[0]
                    if message_type != 2:  # 必须是 CALL
                        logger.error(f"[{charge_point_id}] 无效的 MessageType: {message_type}, 期望 2 (CALL)")
                        return {
                            "error": [4, "", "ProtocolError", "Invalid MessageType"]
                        }
                    
                    unique_id = body[1]
                    action = body[2]
                    payload = body[3] if isinstance(body[3], dict) else {}
                    is_ocpp_standard_format = True
                    
                    logger.info(f"[{charge_point_id}] <- HTTP OCPP {action} (标准格式, UniqueId={unique_id})")
                elif isinstance(body, dict):
                    # 简化格式
                    action = body.get("action", "")
                    payload = body.get("payload", {})
                    
                    logger.info(f"[{charge_point_id}] <- HTTP OCPP {action} (简化格式)")
                else:
                    logger.error(f"[{charge_point_id}] 无效的消息格式: {type(body)}")
                    return {"error": "Invalid message format"}
                
                # 更新会话
                self._charger_sessions[charge_point_id] = {
                    "last_seen": None,  # 可以添加时间戳
                    "transport": "http"
                }
                
                # 处理消息
                response = await self.handle_incoming_message(charge_point_id, action, payload)
                
                # 根据请求格式决定响应格式
                if is_ocpp_standard_format and unique_id:
                    if "errorCode" in response or "error" in response or response.get("status") == "Rejected":
                        # CALLERROR: [4, UniqueId, ErrorCode, ErrorDescription, ErrorDetails(可选)]
                        error_code = response.get("errorCode", "InternalError")
                        error_description = response.get("errorDescription", response.get("error", "Unknown error"))
                        error_details = response.get("errorDetails")
                        
                        if error_details:
                            ocpp_response = [4, unique_id, error_code, error_description, error_details]
                        else:
                            ocpp_response = [4, unique_id, error_code, error_description]
                    else:
                        # CALLRESULT: [3, UniqueId, Payload]
                        ocpp_response = [3, unique_id, response]
                    
                    response_data = {"response": ocpp_response}
                else:
                    response_data = {"response": response}
                
                # 检查是否有待发送的消息
                pending = self._get_pending_message(charge_point_id)
                if pending:
                    response_data["pending"] = pending
                
                return response_data
                
            except Exception as e:
                logger.error(f"[{charge_point_id}] HTTP 请求处理错误: {e}", exc_info=True)
                raise HTTPException(status_code=400, detail=str(e))
        
        elif request.method == "GET":
            # 充电桩轮询获取待处理消息
            pending = self._get_pending_message(charge_point_id)
            return {"pending": pending}
        
        else:
            raise HTTPException(status_code=405, detail="Method not allowed")
    
    def _get_pending_message(self, charge_point_id: str) -> Optional[Dict[str, Any]]:
        """获取待发送的消息（使用 OCPP 标准格式）"""
        if charge_point_id in self._pending_requests:
            requests = self._pending_requests[charge_point_id]
            if requests:
                # 返回第一个待处理的消息
                request_id, message = next(iter(requests.items()))
                del requests[request_id]
                
                # 使用 OCPP 1.6 标准格式: [2, UniqueId, Action, Payload]
                import uuid
                unique_id = f"csms_{uuid.uuid4().hex[:16]}"
                return [2, unique_id, message["action"], message["payload"]]
        return None

