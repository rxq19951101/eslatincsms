from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class MeteringState:
    meter_wh: int = 0
    soc: float = 20.0


def now() -> str:
    # OCPP expects ISO 8601 with timezone; ocpp lib accepts datetime too,
    # but we keep ISO string for consistency across our own payloads.
    return datetime.now(timezone.utc).isoformat()


def advance_meter(
    state: MeteringState,
    interval_sec: int,
    power_kw: float,
    soc_end: float,
) -> None:
    """
    - meterWh 增长：power(kW) * (sec/3600) * 1000
    - soc 线性增长到 soc_end（演示用途）
    """
    delta_wh = int(max(0.0, power_kw) * (interval_sec / 3600.0) * 1000.0)
    state.meter_wh += max(0, delta_wh)
    if state.soc < soc_end:
        state.soc = min(soc_end, state.soc + max(0.1, (soc_end - state.soc) * 0.02))

