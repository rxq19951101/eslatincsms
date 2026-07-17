from enum import Enum


class ChargingSessionStatus(str, Enum):
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS = {
    ChargingSessionStatus.ONGOING: {
        ChargingSessionStatus.COMPLETED,
        ChargingSessionStatus.CANCELLED,
    },
    ChargingSessionStatus.COMPLETED: set(),
    ChargingSessionStatus.CANCELLED: set(),
}


def validate_transition(current: str, target: str) -> None:
    """校验充电会话状态迁移；终态重复写入由调用方作为幂等操作处理。"""
    current_status = ChargingSessionStatus(current)
    target_status = ChargingSessionStatus(target)
    if current_status == target_status:
        return
    if target_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise ValueError(f"Invalid charging session transition: {current} -> {target}")
