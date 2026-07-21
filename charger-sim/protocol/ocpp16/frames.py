from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional


CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4


def build_call(action: str, payload: Dict[str, Any], unique_id: Optional[str] = None) -> List[Any]:
    if not action or not isinstance(action, str):
        raise ValueError("OCPP action must be a non-empty string")
    if not isinstance(payload, dict):
        raise ValueError("OCPP payload must be an object")
    return [CALL, unique_id or str(uuid.uuid4()), action, payload]


def validate_frame(frame: Any) -> List[Any]:
    if not isinstance(frame, list) or not frame:
        raise ValueError("OCPP 1.6J frame must be a JSON array")
    if frame[0] == CALL and len(frame) == 4 and isinstance(frame[1], str) and isinstance(frame[2], str) and isinstance(frame[3], dict):
        return frame
    if frame[0] == CALL_RESULT and len(frame) == 3 and isinstance(frame[1], str) and isinstance(frame[2], dict):
        return frame
    if frame[0] == CALL_ERROR and len(frame) == 5 and isinstance(frame[1], str):
        return frame
    raise ValueError("Invalid OCPP 1.6J array frame")


def encode_frame(frame: Any) -> str:
    return json.dumps(validate_frame(frame), separators=(",", ":"))


def decode_frame(raw: str) -> List[Any]:
    parsed = json.loads(raw)
    return validate_frame(parsed)
