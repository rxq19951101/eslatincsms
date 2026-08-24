from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class DevicePhase(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    BOOTED = "BOOTED"
    AUTHORIZED = "AUTHORIZED"
    CHARGING = "CHARGING"
    FAULTED = "FAULTED"


@dataclass
class DeviceState:
    phase: DevicePhase = DevicePhase.DISCONNECTED
    authorized_id_tag: Optional[str] = None
    transactions: Dict[int, int] = field(default_factory=dict)

    def connect(self) -> None:
        self.phase = DevicePhase.CONNECTED

    def boot(self, accepted: bool) -> None:
        if not accepted:
            raise RuntimeError("BootNotification was rejected")
        self.phase = DevicePhase.BOOTED

    def authorize(self, id_tag: str, accepted: bool) -> None:
        self.authorized_id_tag = id_tag if accepted else None
        self.phase = DevicePhase.AUTHORIZED if accepted else DevicePhase.BOOTED

    def start(self, connector_id: int, transaction_id: int, id_tag: str) -> None:
        if self.phase != DevicePhase.AUTHORIZED or self.authorized_id_tag != id_tag:
            raise RuntimeError("StartTransaction requires a successful Authorize")
        if connector_id in self.transactions:
            raise RuntimeError("connector already has an active transaction")
        self.transactions[connector_id] = transaction_id
        self.phase = DevicePhase.CHARGING

    def stop(self, connector_id: int) -> int:
        if connector_id not in self.transactions:
            raise RuntimeError("StopTransaction requires an active transaction")
        transaction_id = self.transactions.pop(connector_id)
        self.phase = DevicePhase.BOOTED if not self.transactions else DevicePhase.CHARGING
        return transaction_id

    def fault(self) -> None:
        self.phase = DevicePhase.FAULTED

    def disconnect(self) -> None:
        self.phase = DevicePhase.DISCONNECTED
        self.authorized_id_tag = None
