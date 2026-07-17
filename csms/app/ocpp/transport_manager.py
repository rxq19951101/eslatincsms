"""WebSocket-only OCPP transport manager."""

import logging
from typing import Dict, Any, Optional, List

from .transport import TransportAdapter, TransportType, WebSocketAdapter

logger = logging.getLogger("ocpp_csms")


class TransportManager:
    def __init__(self):
        self.adapters: Dict[TransportType, TransportAdapter] = {}
        self._initialized = False

    async def initialize(self, enabled_transports: Optional[List[TransportType]] = None):
        if self._initialized:
            return
        # 保留参数以兼容旧调用，但运行时只允许 WebSocket。
        if enabled_transports and any(t != TransportType.WEBSOCKET for t in enabled_transports):
            logger.warning("忽略非 WebSocket 传输配置，系统已固定为 WebSocket-only")
        adapter = WebSocketAdapter()
        await adapter.start()
        self.adapters = {TransportType.WEBSOCKET: adapter}
        self._initialized = True
        logger.info("仅 WebSocket 传输已启用")

    async def shutdown(self):
        for transport_type, adapter in list(self.adapters.items()):
            try:
                await adapter.stop()
            except Exception:
                logger.exception("停止 WebSocket 传输失败")
        self.adapters.clear()
        self._initialized = False

    def set_message_handler(self, handler):
        for adapter in self.adapters.values():
            adapter.set_message_handler(handler)

    async def send_message(self, charge_point_id: str, action: str, payload: Dict[str, Any],
                           preferred_transport: Optional[TransportType] = None,
                           timeout: float = 5.0) -> Dict[str, Any]:
        adapter = self.adapters.get(TransportType.WEBSOCKET)
        if not adapter or not adapter.is_connected(charge_point_id):
            raise ConnectionError(f"充电桩 {charge_point_id} 未通过 WebSocket 连接")
        return await adapter.send_message(charge_point_id, action, payload, timeout)

    def is_connected(self, charge_point_id: str) -> bool:
        adapter = self.adapters.get(TransportType.WEBSOCKET)
        return bool(adapter and adapter.is_connected(charge_point_id))

    def get_connection_type(self, charge_point_id: str) -> Optional[TransportType]:
        return TransportType.WEBSOCKET if self.is_connected(charge_point_id) else None

    def get_adapter(self, transport_type: TransportType) -> Optional[TransportAdapter]:
        return self.adapters.get(transport_type)


transport_manager = TransportManager()
