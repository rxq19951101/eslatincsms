"""Removed legacy OCPP route.

The only registered OCPP endpoint is ``app.main.canonical_ocpp_ws`` at
``/ocpp?id=<ocpp_identity>``. This compatibility symbol deliberately refuses
connections so another module cannot accidentally re-enable dict frames or the
former non-standard greeting.
"""

from fastapi import Query, WebSocket


async def ocpp_websocket_route(
    websocket: WebSocket, id: str = Query(..., description="OCPP identity")
) -> None:
    await websocket.close(code=1008, reason="Use canonical /ocpp?id= endpoint")
