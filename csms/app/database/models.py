#
# 数据库模型 - 重构后的表结构
# 清晰的职责分离：站点/桩/枪/会话/结算分层
#

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, 
    DateTime, Text, ForeignKey, JSON, Index, Numeric
)
from sqlalchemy.orm import relationship
from app.database.base import Base


# ==================== 站点和资产层 ====================

class Site(Base):
    """充电站点表
    存储站点级别的信息：地理位置、地址、运营信息
    """
    __tablename__ = "sites"
    
    id = Column(String(100), primary_key=True, index=True)
    name = Column(String(200), nullable=False)  # 站点名称
    address = Column(Text, nullable=False)  # 详细地址
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    
    # 运营信息
    is_active = Column(Boolean, default=True)
    operating_hours = Column(Text, nullable=True)  # 营业时间（JSON或文本）
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    charge_points = relationship("ChargePoint", back_populates="site", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_sites_location', 'latitude', 'longitude'),
    )


class ChargePoint(Base):
    """充电桩资产表
    存储充电桩的资产信息：厂商、型号、序列号、固件等
    不存储实时状态和定价信息
    """
    __tablename__ = "charge_points"
    
    id = Column(String(100), primary_key=True, index=True)
    site_id = Column(String(100), ForeignKey("sites.id"), nullable=False, index=True)
    
    # 资产信息
    vendor = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    serial_number = Column(String(100), nullable=True, unique=True, index=True)
    firmware_version = Column(String(50), nullable=True)
    
    # 技术规格
    max_power_kw = Column(Float, nullable=True)  # 最大功率
    
    # 关联设备（MQTT设备）
    device_serial_number = Column(String(100), ForeignKey("devices.serial_number"), nullable=True, index=True)
    
    # 运营状态
    is_active = Column(Boolean, default=True)
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    site = relationship("Site", back_populates="charge_points")
    device = relationship("Device", foreign_keys=[device_serial_number], back_populates="charge_points")
    evses = relationship("EVSE", back_populates="charge_point", cascade="all, delete-orphan")
    evse_statuses = relationship("EVSEStatus", back_populates="charge_point", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_charge_points_site', 'site_id'),
        Index('idx_charge_points_device', 'device_serial_number'),
    )


class EVSE(Base):
    """EVSE/连接器表（枪口）
    一个充电桩可以有多个EVSE（多枪）
    """
    __tablename__ = "evses"
    
    id = Column(Integer, primary_key=True, index=True)
    charge_point_id = Column(String(100), ForeignKey("charge_points.id"), nullable=False, index=True)
    evse_id = Column(Integer, nullable=False)  # OCPP中的evse_id
    
    # EVSE信息
    connector_type = Column(String(50), default="Type2")  # 连接器类型（从 charge_points 下放）
    max_power_kw = Column(Float, nullable=True)  # 该EVSE的最大功率
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    charge_point = relationship("ChargePoint", back_populates="evses")
    evse_status = relationship("EVSEStatus", back_populates="evse", uselist=False, cascade="all, delete-orphan")
    charging_sessions = relationship("ChargingSession", back_populates="evse", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_evses_charge_point', 'charge_point_id'),
        Index('idx_evses_charge_point_evse', 'charge_point_id', 'evse_id', unique=True),
    )


class EVSEStatus(Base):
    """EVSE实时状态快照表
    存储每个EVSE的当前状态（用于快速查询）
    """
    __tablename__ = "evse_status"
    
    id = Column(Integer, primary_key=True, index=True)
    evse_id = Column(Integer, ForeignKey("evses.id"), nullable=False, unique=True, index=True)
    charge_point_id = Column(String(100), ForeignKey("charge_points.id"), nullable=False, index=True)
    
    # 状态信息
    status = Column(String(50), default="Unknown", nullable=False)  # Available, Charging, Offline, Faulted, Unavailable
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # 当前会话信息（如果有）
    current_session_id = Column(Integer, ForeignKey("charging_sessions.id"), nullable=True, index=True)
    
    # 元数据
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    evse = relationship("EVSE", back_populates="evse_status")
    charge_point = relationship("ChargePoint", back_populates="evse_statuses")
    current_session = relationship("ChargingSession", foreign_keys=[current_session_id])
    
    __table_args__ = (
        Index('idx_evse_status_charge_point', 'charge_point_id'),
        Index('idx_evse_status_status', 'status'),
        Index('idx_evse_status_last_seen', 'last_seen'),
    )


# ==================== 设备认证层 ====================

class Device(Base):
    """设备表
    存储设备SN号和MQTT认证信息
    每个设备独立存储master_secret（加密）
    """
    __tablename__ = "devices"
    
    # 设备SN号（主键）
    serial_number = Column(String(100), primary_key=True, index=True)
    
    # 设备类型代码（用于MQTT topic和client_id，如 "zcf", "tesla", "abb"）
    type_code = Column(String(50), nullable=False, index=True, default="default")  # 设备类型代码
    
    # MQTT认证信息
    mqtt_client_id = Column(String(200), nullable=False, unique=True, index=True)  # {type_code}&{serial_number}
    mqtt_username = Column(String(100), nullable=False, unique=True, index=True)  # {serial_number}
    
    # 安全：每个设备独立存储加密的master secret
    master_secret_encrypted = Column(Text, nullable=False)  # 加密存储的master secret
    encryption_algorithm = Column(String(50), default="AES-256-GCM")  # 加密算法
    
    # 设备状态
    is_active = Column(Boolean, default=True)
    last_connected = Column(DateTime(timezone=True), nullable=True)
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    charge_points = relationship("ChargePoint", foreign_keys="ChargePoint.device_serial_number", back_populates="device")
    
    __table_args__ = (
        Index('idx_devices_type_code', 'type_code'),
        Index('idx_devices_mqtt_client_id', 'mqtt_client_id'),
        Index('idx_devices_mqtt_username', 'mqtt_username'),
    )


# ==================== 充电会话层 ====================

class ChargingSession(Base):
    """充电会话表（协议事实层）
    替代原来的transactions，只存储OCPP协议层面的信息
    不存储计费信息（计费在invoice层）
    """
    __tablename__ = "charging_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    evse_id = Column(Integer, ForeignKey("evses.id"), nullable=False, index=True)
    charge_point_id = Column(String(100), ForeignKey("charge_points.id"), nullable=False, index=True)
    
    # OCPP协议信息
    transaction_id = Column(Integer, nullable=False, index=True)  # OCPP transaction_id
    id_tag = Column(String(100), nullable=False, index=True)  # RFID标签
    user_id = Column(String(100), nullable=True, index=True)  # 用户ID（可选）
    
    # 时间信息
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    
    # 计量信息（原始数据）
    meter_start = Column(Integer, default=0)  # 起始计量值(Wh)
    meter_stop = Column(Integer, nullable=True)  # 结束计量值(Wh)
    
    # 状态
    status = Column(String(50), default="ongoing")  # ongoing, completed, cancelled
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    evse = relationship("EVSE", back_populates="charging_sessions")
    charge_point = relationship("ChargePoint")
    meter_values = relationship("MeterValue", back_populates="session", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="session", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_sessions_status', 'status'),
        Index('idx_sessions_id_tag', 'id_tag'),
        Index('idx_sessions_start_time', 'start_time'),
        Index('idx_sessions_charge_point', 'charge_point_id'),
        Index('idx_sessions_transaction_unique', 'charge_point_id', 'evse_id', 'transaction_id', unique=True),
    )


class MeterValue(Base):
    """计量值记录表
    存储充电过程中的实时计量数据
    """
    __tablename__ = "meter_values"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("charging_sessions.id"), nullable=False, index=True)
    
    connector_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # 计量数据
    value = Column(Integer, nullable=False)  # 主要值（Wh）
    sampled_value = Column(JSON, nullable=True)  # 完整采样值数据（JSON格式）
    
    # 关系
    session = relationship("ChargingSession", back_populates="meter_values")
    
    __table_args__ = (
        Index('idx_meter_values_timestamp', 'timestamp'),
        Index('idx_meter_values_session', 'session_id'),
    )


# ==================== 业务订单层 ====================

class Order(Base):
    """订单表（业务层）
    只存储业务层面的信息：用户意图、预授权、优惠、支付状态
    不存储计费信息（计费在invoice层）
    """
    __tablename__ = "orders"
    
    id = Column(String(100), primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("charging_sessions.id"), nullable=True, index=True)
    charge_point_id = Column(String(100), ForeignKey("charge_points.id"), nullable=False, index=True)
    
    # 用户信息
    user_id = Column(String(100), nullable=False, index=True)
    id_tag = Column(String(100), nullable=False)
    
    # 时间信息
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=True)  # 实际开始时间（可能晚于创建时间）
    end_time = Column(DateTime(timezone=True), nullable=True)
    
    # 业务状态
    status = Column(String(50), default="pending")  # pending, authorized, ongoing, completed, cancelled, failed
    
    # 预授权/优惠信息（JSON格式）
    pre_authorization = Column(JSON, nullable=True)  # 预授权金额等
    discounts = Column(JSON, nullable=True)  # 优惠信息
    
    # 元数据
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    session = relationship("ChargingSession")
    charge_point = relationship("ChargePoint")
    invoices = relationship("Invoice", back_populates="order", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_orders_status', 'status'),
        Index('idx_orders_user_id', 'user_id'),
        Index('idx_orders_created_at', 'created_at'),
    )


# ==================== 定价和结算层 ====================

class Tariff(Base):
    """定价规则表
    存储定价规则（站点、时段、活动等）
    """
    __tablename__ = "tariffs"
    
    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(String(100), ForeignKey("sites.id"), nullable=True, index=True)  # 站点级别定价
    charge_point_id = Column(String(100), ForeignKey("charge_points.id"), nullable=True, index=True)  # 桩级别定价
    
    # 定价规则
    name = Column(String(200), nullable=False)  # 定价规则名称
    base_price_per_kwh = Column(Numeric(10, 2), nullable=False)  # 基础电价
    service_fee = Column(Numeric(10, 2), default=0)  # 服务费
    
    # 时段定价（JSON格式存储复杂规则）
    time_based_rules = Column(JSON, nullable=True)  # 时段定价规则
    
    # 有效期
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    
    # 状态
    is_active = Column(Boolean, default=True)
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    site = relationship("Site")
    charge_point = relationship("ChargePoint")
    pricing_snapshots = relationship("PricingSnapshot", back_populates="tariff", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_tariffs_site', 'site_id'),
        Index('idx_tariffs_charge_point', 'charge_point_id'),
        Index('idx_tariffs_valid', 'valid_from', 'valid_until'),
    )


class PricingSnapshot(Base):
    """定价快照表
    在订单/会话创建时固化当时的定价信息
    用于可追溯的结算
    """
    __tablename__ = "pricing_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("charging_sessions.id"), nullable=True, index=True)
    order_id = Column(String(100), ForeignKey("orders.id"), nullable=True, index=True)
    
    # 快照的定价信息
    price_per_kwh = Column(Numeric(10, 2), nullable=False)
    service_fee = Column(Numeric(10, 2), default=0)
    snapshot_data = Column(JSON, nullable=True)  # 完整的定价规则快照
    
    # 快照时间
    snapshot_time = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # 关系
    tariff = relationship("Tariff", back_populates="pricing_snapshots")
    session = relationship("ChargingSession")
    order = relationship("Order")
    
    __table_args__ = (
        Index('idx_pricing_snapshots_session', 'session_id'),
        Index('idx_pricing_snapshots_order', 'order_id'),
    )


class Invoice(Base):
    """发票/账单表（结算权威）
    存储最终结算信息，所有计费字段的权威来源
    """
    __tablename__ = "invoices"
    
    id = Column(String(100), primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("charging_sessions.id"), nullable=False, index=True)
    order_id = Column(String(100), ForeignKey("orders.id"), nullable=True, index=True)
    pricing_snapshot_id = Column(Integer, ForeignKey("pricing_snapshots.id"), nullable=False, index=True)
    
    # 计费信息（权威数据）
    energy_kwh = Column(Numeric(10, 3), nullable=False)  # 电量（kWh）
    duration_minutes = Column(Numeric(10, 2), nullable=False)  # 时长（分钟）
    charging_rate_kw = Column(Numeric(10, 2), nullable=True)  # 充电功率（kW）
    
    # 费用计算
    energy_cost = Column(Numeric(10, 2), nullable=False)  # 电费
    service_fee = Column(Numeric(10, 2), default=0)  # 服务费
    total_amount = Column(Numeric(10, 2), nullable=False)  # 总金额（权威）
    
    # 状态
    status = Column(String(50), default="pending")  # pending, paid, cancelled, refunded
    
    # 时间信息
    issued_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    session = relationship("ChargingSession", back_populates="invoices")
    order = relationship("Order", back_populates="invoices")
    pricing_snapshot = relationship("PricingSnapshot")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_invoices_status', 'status'),
        Index('idx_invoices_session', 'session_id'),
        Index('idx_invoices_order', 'order_id'),
        Index('idx_invoices_issued_at', 'issued_at'),
    )


class Payment(Base):
    """支付流水表
    存储所有支付记录
    """
    __tablename__ = "payments"
    
    id = Column(String(100), primary_key=True, index=True)
    invoice_id = Column(String(100), ForeignKey("invoices.id"), nullable=False, index=True)
    
    # 支付信息
    amount = Column(Numeric(10, 2), nullable=False)  # 支付金额
    payment_method = Column(String(50), nullable=False)  # 支付方式
    payment_provider = Column(String(100), nullable=True)  # 支付提供商
    transaction_id = Column(String(200), nullable=True, unique=True, index=True)  # 第三方交易ID
    
    # 状态
    status = Column(String(50), default="pending")  # pending, completed, failed, refunded
    
    # 时间信息
    initiated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    invoice = relationship("Invoice", back_populates="payments")
    
    __table_args__ = (
        Index('idx_payments_status', 'status'),
        Index('idx_payments_invoice', 'invoice_id'),
        Index('idx_payments_transaction_id', 'transaction_id'),
    )


# ==================== 事件和日志层 ====================

class DeviceEvent(Base):
    """设备事件表（统一事件流）
    合并原来的heartbeat_history、status_history、ocpp_error_logs
    """
    __tablename__ = "device_events"
    
    id = Column(Integer, primary_key=True, index=True)
    device_serial_number = Column(String(100), ForeignKey("devices.serial_number"), nullable=True, index=True)
    charge_point_id = Column(String(100), ForeignKey("charge_points.id"), nullable=True, index=True)
    evse_id = Column(Integer, ForeignKey("evses.id"), nullable=True, index=True)
    
    # 事件信息
    event_type = Column(String(50), nullable=False, index=True)  # heartbeat, status_change, error, boot, disconnect, etc.
    event_data = Column(JSON, nullable=True)  # 事件数据（JSON格式）
    
    # 状态相关（如果是status_change事件）
    status = Column(String(50), nullable=True)  # 新状态
    previous_status = Column(String(50), nullable=True)  # 之前的状态
    
    # 错误相关（如果是error事件）
    error_code = Column(String(100), nullable=True)
    error_description = Column(Text, nullable=True)
    
    # 协议消息相关（如果是protocol事件）
    protocol_action = Column(String(100), nullable=True)  # OCPP action
    message_direction = Column(String(20), nullable=True)  # incoming, outgoing
    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    
    # 时间戳
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    # 关系
    device = relationship("Device")
    charge_point = relationship("ChargePoint")
    evse = relationship("EVSE")
    
    __table_args__ = (
        Index('idx_device_events_type', 'event_type'),
        Index('idx_device_events_timestamp', 'timestamp'),
        Index('idx_device_events_device_timestamp', 'device_serial_number', 'timestamp'),
        Index('idx_device_events_charge_point_timestamp', 'charge_point_id', 'timestamp'),
    )


# ==================== 配置层 ====================

class DeviceConfig(Base):
    """设备配置表（通信相关）
    存储MQTT、OCPP、心跳等通信配置
    """
    __tablename__ = "device_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    device_serial_number = Column(String(100), ForeignKey("devices.serial_number"), nullable=False, index=True)
    
    config_key = Column(String(100), nullable=False)  # 配置键
    config_value = Column(Text, nullable=True)  # 配置值
    value_type = Column(String(20), default="string")  # string, int, bool, json
    
    # 版本控制
    version = Column(Integer, default=1)
    updated_by = Column(String(100), nullable=True)  # 更新人
    
    # 元数据
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    device = relationship("Device")
    
    __table_args__ = (
        Index('idx_device_configs_device_key', 'device_serial_number', 'config_key', unique=True),
    )


class ChargePointConfig(Base):
    """充电桩配置表（资产相关）
    存储限功率、开放时间、告警阈值等资产配置
    """
    __tablename__ = "charge_point_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    charge_point_id = Column(String(100), ForeignKey("charge_points.id"), nullable=False, index=True)
    
    config_key = Column(String(100), nullable=False)  # 配置键
    config_value = Column(Text, nullable=True)  # 配置值
    value_type = Column(String(20), default="string")  # string, int, bool, json
    
    # 版本控制
    version = Column(Integer, default=1)
    updated_by = Column(String(100), nullable=True)  # 更新人
    
    # 元数据
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    charge_point = relationship("ChargePoint")
    
    __table_args__ = (
        Index('idx_charge_point_configs_cp_key', 'charge_point_id', 'config_key', unique=True),
    )


# ==================== 业务支持表 ====================

class SupportMessage(Base):
    """客服消息表
    保持不变
    """
    __tablename__ = "support_messages"
    
    id = Column(String(100), primary_key=True, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    username = Column(String(100), nullable=False)
    
    message = Column(Text, nullable=False)
    reply = Column(Text, nullable=True)
    
    status = Column(String(50), default="pending")  # pending, replied
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    replied_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index('idx_messages_status', 'status'),
        Index('idx_messages_user_id', 'user_id'),
        Index('idx_messages_created_at', 'created_at'),
    )
