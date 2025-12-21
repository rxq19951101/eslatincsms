#
# 数据库模块
# 包含数据模型、数据库连接、仓储模式等
#

# 先导入models以定义Base
from app.database.models import (
    Base,
    # 新表结构
    Site, ChargePoint, EVSE, EVSEStatus,
    DeviceType, Device,
    ChargingSession, MeterValue,
    Order, Invoice, Payment,
    Tariff, PricingSnapshot,
    DeviceEvent,
    DeviceConfig, ChargePointConfig,
    SupportMessage,
)

# 然后导入base（需要Base已定义）
from app.database.base import engine, SessionLocal, get_db, init_db, check_db_health
from sqlalchemy.orm import Session

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "Session",  # SQLAlchemy Session 类型
    "get_db",
    "init_db",
    "check_db_health",
    # 新表结构
    "Site",
    "ChargePoint",
    "EVSE",
    "EVSEStatus",
    "DeviceType",
    "Device",
    "ChargingSession",
    "MeterValue",
    "Order",
    "Invoice",
    "Payment",
    "Tariff",
    "PricingSnapshot",
    "DeviceEvent",
    "DeviceConfig",
    "ChargePointConfig",
    "SupportMessage",
]
