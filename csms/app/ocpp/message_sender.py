"""WebSocket-only OCPP message sender."""

import asyncio
from typing import Dict, Any
from fastapi import HTTPException
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")


class OCPPMessageSender:
    @staticmethod
    async def send_call(charger_id: str, action: str, payload: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
        from app.ocpp.transport_manager import transport_manager, TransportType
        if not transport_manager.is_connected(charger_id):
            raise HTTPException(status_code=404, detail=f"Charger {charger_id} is not connected via WebSocket")
        try:
            result = await transport_manager.send_message(
                charger_id, action, payload,
                preferred_transport=TransportType.WEBSOCKET,
                timeout=timeout,
            )
            return {"success": True, "data": result, "transport": "WebSocket"}
        except ConnectionError as exc:
            logger.error("WebSocket OCPP send failed: charger=%s action=%s error=%s", charger_id, action, exc)
            if isinstance(exc.__cause__, asyncio.TimeoutError) or "timed out" in str(exc).lower():
                timeout_error = HTTPException(
                    status_code=504,
                    detail=f"Timed out waiting for {action} response",
                )
                timeout_error.error_code = "OCPP_RESPONSE_TIMEOUT"
                raise timeout_error from exc
            raise HTTPException(status_code=502, detail="WebSocket OCPP request failed") from exc
        except Exception as exc:
            logger.error("WebSocket OCPP send failed: charger=%s action=%s error=%s", charger_id, action, exc)
            raise HTTPException(status_code=502, detail="WebSocket OCPP request failed") from exc


message_sender = OCPPMessageSender()
