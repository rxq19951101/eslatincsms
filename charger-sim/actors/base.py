from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ActorResult:
    status: Any = "ok"
    body: Any = field(default_factory=dict)
    request: Any = None
    response: Any = None
    frame: Any = None
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "body": self.body,
            "request": self.request,
            "response": self.response,
            "frame": self.frame,
            "trace_id": self.trace_id,
        }


class BaseActor:
    def __init__(self, name: str, config: Dict[str, Any], run_id: str):
        self.name = name
        self.config = config
        self.run_id = run_id

    async def execute(self, action: str, params: Dict[str, Any], step_id: str) -> ActorResult:
        raise NotImplementedError

    async def close(self) -> None:
        return None
