#
# OCPP连接管理
# 管理充电桩WebSocket连接
#

from dataclasses import dataclass
from typing import Dict, Optional
from fastapi import WebSocket
import logging
import uuid

logger = logging.getLogger("ocpp_csms")


@dataclass(frozen=True)
class ConnectionEntry:
    websocket: WebSocket
    generation: str


class ConnectionManager:
    """OCPP WebSocket连接管理器"""
    
    def __init__(self):
        self._connections: Dict[str, ConnectionEntry] = {}
    
    def connect(self, charger_id: str, websocket: WebSocket, generation: Optional[str] = None) -> str:
        """注册连接"""
        generation = generation or uuid.uuid4().hex
        self._connections[charger_id] = ConnectionEntry(websocket, generation)
        logger.info(f"[{charger_id}] WebSocket连接已注册 generation={generation}")
        return generation
    
    def disconnect(
        self,
        charger_id: str,
        generation: Optional[str] = None,
        websocket: Optional[WebSocket] = None,
    ) -> bool:
        """Only the active generation may unregister itself."""
        entry = self._connections.get(charger_id)
        if not entry:
            return False
        if generation is not None and entry.generation != generation:
            return False
        if websocket is not None and entry.websocket is not websocket:
            return False
        del self._connections[charger_id]
        logger.info(f"[{charger_id}] WebSocket连接已断开 generation={entry.generation}")
        return True
    
    def get_connection(self, charger_id: str) -> Optional[WebSocket]:
        """获取连接"""
        entry = self._connections.get(charger_id)
        return entry.websocket if entry else None

    def get_generation(self, charger_id: str) -> Optional[str]:
        entry = self._connections.get(charger_id)
        return entry.generation if entry else None
    
    def is_connected(self, charger_id: str) -> bool:
        """检查是否连接"""
        return charger_id in self._connections
    
    def get_all_charger_ids(self) -> list:
        """获取所有已连接的充电桩ID"""
        return list(self._connections.keys())
    
    def count(self) -> int:
        """获取连接数"""
        return len(self._connections)


# 全局连接管理器实例
connection_manager = ConnectionManager()
