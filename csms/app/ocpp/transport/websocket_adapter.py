"""Generation-fenced OCPP 1.6J WebSocket transport."""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import WebSocket

from .base import TransportAdapter, TransportType

logger = logging.getLogger("ocpp_csms")


@dataclass(frozen=True)
class ConnectionEntry:
    websocket: WebSocket
    generation: str


@dataclass
class PendingResponse:
    future: asyncio.Future
    charge_point_id: str
    generation: str


class WebSocketAdapter(TransportAdapter):
    def __init__(self):
        super().__init__(TransportType.WEBSOCKET)
        self._connections: Dict[str, ConnectionEntry] = {}
        self._pending_responses: Dict[str, PendingResponse] = {}

    async def start(self) -> None:
        logger.info("WebSocket transport initialized")

    async def stop(self) -> None:
        for entry in list(self._connections.values()):
            try:
                await entry.websocket.close()
            except Exception:
                pass
        for pending in self._pending_responses.values():
            if not pending.future.done():
                pending.future.cancel()
        self._connections.clear()
        self._pending_responses.clear()

    async def register_connection(
        self,
        charge_point_id: str,
        websocket: WebSocket,
        generation: Optional[str] = None,
    ) -> str:
        generation = generation or uuid.uuid4().hex
        previous = self._connections.get(charge_point_id)
        self._connections[charge_point_id] = ConnectionEntry(websocket, generation)
        if previous and previous.generation != generation:
            self._cancel_pending(charge_point_id, previous.generation)
        logger.info(
            "[%s] WebSocket registered generation=%s", charge_point_id, generation
        )
        return generation

    async def unregister_connection(
        self,
        charge_point_id: str,
        generation: Optional[str] = None,
        websocket: Optional[WebSocket] = None,
    ) -> bool:
        entry = self._connections.get(charge_point_id)
        if not entry:
            return False
        if generation is not None and entry.generation != generation:
            return False
        if websocket is not None and entry.websocket is not websocket:
            return False
        del self._connections[charge_point_id]
        self._cancel_pending(charge_point_id, entry.generation)
        logger.info(
            "[%s] WebSocket unregistered generation=%s",
            charge_point_id,
            entry.generation,
        )
        return True

    def _cancel_pending(self, charge_point_id: str, generation: str) -> None:
        keys = [
            key
            for key, pending in self._pending_responses.items()
            if pending.charge_point_id == charge_point_id
            and pending.generation == generation
        ]
        for key in keys:
            pending = self._pending_responses.pop(key)
            if not pending.future.done():
                pending.future.cancel()

    async def send_message(
        self,
        charge_point_id: str,
        action: str,
        payload: Dict[str, Any],
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        entry = self._connections.get(charge_point_id)
        if not entry:
            raise ConnectionError(
                f"Charger {charge_point_id} is not connected via WebSocket"
            )

        unique_id = f"csms_{uuid.uuid4().hex[:16]}"
        future = asyncio.get_running_loop().create_future()
        self._pending_responses[unique_id] = PendingResponse(
            future=future,
            charge_point_id=charge_point_id,
            generation=entry.generation,
        )
        try:
            await entry.websocket.send_text(json.dumps([2, unique_id, action, payload]))
            response = await asyncio.wait_for(future, timeout=timeout)
            if isinstance(response, dict) and response.get("success") is False:
                raise ConnectionError(
                    f"Charge point returned CALLERROR: {response.get('error', 'UnknownError')}"
                )
            return response.get("data", response) if isinstance(response, dict) else response
        except asyncio.TimeoutError as exc:
            raise ConnectionError(f"Waiting for {action} response timed out") from exc
        finally:
            self._pending_responses.pop(unique_id, None)

    def handle_response(
        self,
        unique_id: str,
        response_data: Dict[str, Any],
        *,
        charge_point_id: Optional[str] = None,
        generation: Optional[str] = None,
    ) -> bool:
        pending = self._pending_responses.get(unique_id)
        if not pending:
            logger.warning("Unexpected OCPP response UniqueId=%s", unique_id)
            return False
        if charge_point_id is not None and pending.charge_point_id != charge_point_id:
            return False
        if generation is not None and pending.generation != generation:
            return False
        self._pending_responses.pop(unique_id, None)
        if not pending.future.done():
            pending.future.set_result(response_data)
        return True

    def is_connected(self, charge_point_id: str) -> bool:
        return charge_point_id in self._connections

    def get_generation(self, charge_point_id: str) -> Optional[str]:
        entry = self._connections.get(charge_point_id)
        return entry.generation if entry else None
