from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StepResult:
    run_id: str
    scenario_id: str
    step_id: str
    actor: str
    action: str
    start: str
    end: str
    duration_seconds: float
    outcome: str
    trace_id: str = ""
    attempts: int = 1
    result: Any = None
    error: Optional[str] = None


@dataclass
class RunResult:
    run_id: str
    scenario_id: str
    start: str
    end: str
    outcome: str
    steps: List[StepResult] = field(default_factory=list)
    reports: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["steps"] = [asdict(step) for step in self.steps]
        return data
