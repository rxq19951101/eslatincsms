from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from protocol.ocpp16.frames import build_call


def duplicate_frames(action: str, payload: Dict[str, Any], unique_id: str) -> List[List[Any]]:
    frame = build_call(action, payload, unique_id=unique_id)
    return [list(frame), list(frame)]


def meter_before_start_frame(connector_id: int = 1, unique_id: Optional[str] = None) -> List[Any]:
    return build_call(
        "MeterValues",
        {
            "connectorId": connector_id,
            "transactionId": 999999,
            "meterValue": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampledValue": [{"value": "1", "measurand": "Energy.Active.Import.Register", "unit": "Wh"}],
                }
            ],
        },
        unique_id=unique_id,
    )


def stop_before_start_frame(unique_id: Optional[str] = None) -> List[Any]:
    return build_call(
        "StopTransaction",
        {
            "transactionId": 999999,
            "meterStop": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": "Other",
        },
        unique_id=unique_id,
    )
