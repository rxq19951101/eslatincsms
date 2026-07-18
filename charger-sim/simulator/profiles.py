from __future__ import annotations

from dataclasses import dataclass
import re


OCPP_IDENTITY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


@dataclass(frozen=True)
class MeteringProfile:
    """
    计量/实时数据生成配置（简化版）
    - energy_active_import_register: Wh 递增
    - power_active_import: kW（用于推导电流/电量增长速度）
    """

    connector_id: int
    power_kw: float = 7.0
    voltage_v: float = 220.0
    current_a: float = 16.0
    soc_start: float = 20.0
    soc_end: float = 90.0
    meter_values_interval_sec: int = 5


@dataclass(frozen=True)
class ChargePointProfile:
    """
    充电桩连接身份与 BootNotification 信息。

    ``charge_point_id`` 是 WebSocket/OCPP identity。``serial_number`` 是
    BootNotification 的 chargePointSerialNumber；未显式配置时才回退为 identity。
    """

    charge_point_id: str
    vendor: str = "EsLatin"
    model: str = "EsLatin-Sim-1.0"
    firmware_version: str = "1.0.0"
    serial_number: str | None = None
    heartbeat_interval_sec: int = 30
    # 支付模拟配置
    enable_payment_simulation: bool = True
    payment_delay_seconds: int = 5
    payment_amount: float | None = None  # None 表示使用默认值（10000 COP）
    payment_test_card: str = "visa_approved"
    backend_api_url: str | None = None  # 后端 API URL
    backend_api_token: str | None = None  # 后端 API 认证 token

    def __post_init__(self) -> None:
        if not OCPP_IDENTITY_RE.fullmatch(self.charge_point_id):
            raise ValueError(
                "OCPP identity must be 1-64 ASCII letters, digits, '.', '_', ':' or '-'"
            )
        if self.serial_number is not None and not self.serial_number.strip():
            raise ValueError("BootNotification serial number must not be blank")

    @property
    def ocpp_identity(self) -> str:
        """Canonical name for the WebSocket/OCPP identity."""
        return self.charge_point_id

    @property
    def boot_serial_number(self) -> str:
        """Serial sent in BootNotification, defaulting to the OCPP identity."""
        return self.serial_number if self.serial_number is not None else self.ocpp_identity
