from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Iterable, Optional


@dataclass
class MeteringState:
    meter_wh: int = 0
    soc: float = 20.0


def now() -> str:
    # OCPP expects ISO 8601 with timezone; ocpp lib accepts datetime too,
    # but we keep ISO string for consistency across our own payloads.
    return datetime.now(timezone.utc).isoformat()


def allocate_shared_power_kw(
    requested_power_kw: dict[int, float],
    active_connector_ids: Iterable[int],
    shared_power_limit_kw: float,
) -> dict[int, float]:
    """Fairly allocate one charger's shared power limit among active connectors.

    Each connector is capped by its requested power. Connectors whose request is
    below the current equal share take only that request, and the remainder is
    redistributed among the other active connectors.
    """
    if not math.isfinite(shared_power_limit_kw) or shared_power_limit_kw <= 0:
        raise ValueError("shared_power_limit_kw must be a finite number greater than 0")

    allocations = {connector_id: 0.0 for connector_id in requested_power_kw}
    active = {
        connector_id
        for connector_id in active_connector_ids
        if connector_id in requested_power_kw
    }
    requests: dict[int, float] = {}
    for connector_id in active:
        requested = requested_power_kw[connector_id]
        if not math.isfinite(requested):
            raise ValueError("requested connector power must be finite")
        requests[connector_id] = max(0.0, requested)

    remaining = set(active)
    remaining_power = shared_power_limit_kw
    while remaining:
        equal_share = remaining_power / len(remaining)
        capped = {
            connector_id
            for connector_id in remaining
            if requests[connector_id] <= equal_share
        }
        if not capped:
            for connector_id in remaining:
                allocations[connector_id] = equal_share
            break
        for connector_id in capped:
            allocation = requests[connector_id]
            allocations[connector_id] = allocation
            remaining_power -= allocation
        remaining.difference_update(capped)

    return allocations


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
