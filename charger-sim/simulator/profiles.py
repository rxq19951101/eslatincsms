from __future__ import annotations

from dataclasses import dataclass


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
    充电桩基本信息（用于 BootNotification）
    """

    charge_point_id: str
    vendor: str = "EsLatin"
    model: str = "EsLatin-Sim-1.0"
    firmware_version: str = "1.0.0"
    serial_number: str | None = None  # 默认与 charge_point_id 一致（避免后端"改名"）
    heartbeat_interval_sec: int = 30
    # 支付模拟配置
    enable_payment_simulation: bool = True
    payment_delay_seconds: int = 5
    payment_amount: float | None = None  # None 表示使用默认值（10000 COP）
    payment_test_card: str = "visa_approved"
    backend_api_url: str | None = None  # 后端 API URL
    backend_api_token: str | None = None  # 后端 API 认证 token

