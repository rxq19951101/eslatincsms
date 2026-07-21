"""Compatibility wrapper for the authoritative OCPP message service.

Legacy callers may still import ``OCPPHandler``; all behavior now delegates to
the same UUID/UniqueId-aware service used by the canonical WebSocket endpoint.
"""

from typing import Any, Dict, Optional

from app.services.ocpp_message_handler import OCPPMessageHandler


class OCPPHandler:
    def __init__(self, db=None):
        self.db = db
        self._handler = OCPPMessageHandler()

    async def handle_message(
        self,
        charger_id: str,
        action: str,
        payload: Dict[str, Any],
        *,
        unique_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        connector_id = payload.get("connectorId", 1)
        if connector_id == 0:
            connector_id = 1
        return await self._handler.handle_message(
            charge_point_id=charger_id,
            action=action,
            payload=payload,
            evse_id=connector_id,
            message_unique_id=unique_id,
        )
