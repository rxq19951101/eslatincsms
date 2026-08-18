#
# 数据库模型 - 重构后的表结构
# 清晰的职责分离：站点/桩/枪/会话/结算分层
#

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    Date, DateTime, Text, ForeignKey, ForeignKeyConstraint, JSON, Index,
    Numeric, UniqueConstraint, CheckConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator
from fastapi.encoders import jsonable_encoder
import uuid
from app.database.base import Base


class UUIDSafeJSON(TypeDecorator):
    """Portable JSON storage that normalizes UUID/Decimal/datetime values."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        json_type = JSONB() if dialect.name == "postgresql" else JSON()
        return dialect.type_descriptor(json_type)

    def process_bind_param(self, value, dialect):
        return None if value is None else jsonable_encoder(value)


PortableJSON = UUIDSafeJSON()


def _business_number(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _map_legacy_business_id(kwargs: dict, field: str) -> None:
    """Keep constructor compatibility without using business values as PKs."""
    legacy_id = kwargs.get("id")
    if legacy_id is None:
        return
    try:
        uuid.UUID(str(legacy_id))
    except (TypeError, ValueError, AttributeError):
        kwargs.pop("id")
        kwargs.setdefault(field, str(legacy_id))


# ==================== 站点和资产层 ====================

class Site(Base):
    """充电站点表
    存储站点级别的信息：地理位置、地址、运营信息
    """
    __tablename__ = "sites"

    def __init__(self, **kwargs):
        # Transitional constructor compatibility for scripts/tests that used the
        # former public string key as ``id``. Relationships still receive UUIDs.
        legacy_id = kwargs.get("id")
        if legacy_id is not None:
            try:
                uuid.UUID(str(legacy_id))
            except (TypeError, ValueError, AttributeError):
                kwargs.pop("id")
                kwargs.setdefault("site_code", str(legacy_id))
        super().__init__(**kwargs)
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    # Stable public reference kept separate from the internal relationship key.
    site_code = Column(String(100), nullable=False, unique=True, default=lambda: f"site_{uuid.uuid4().hex[:16]}", index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
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
    tenant = relationship("Tenant")
    charge_points = relationship("ChargePoint", back_populates="site", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('id', 'tenant_id', name='uq_sites_id_tenant'),
        Index('idx_sites_location', 'latitude', 'longitude'),
        Index('idx_sites_tenant_id', 'tenant_id'),
        CheckConstraint(
            "site_code ~ '^site_[0-9a-f]{16}$'",
            name="ck_sites_code_format",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("length(name) BETWEEN 2 AND 120", name="ck_sites_name_length"),
        CheckConstraint("length(address) BETWEEN 5 AND 300", name="ck_sites_address_length"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_sites_latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_sites_longitude_range"),
        CheckConstraint("NOT (latitude = 0 AND longitude = 0)", name="ck_sites_nonzero_coordinates"),
        CheckConstraint("operating_hours IS NULL OR length(operating_hours) <= 500", name="ck_sites_operating_hours_length"),
    )


class ChargePoint(Base):
    """充电桩资产表
    存储充电桩的资产信息：厂商、型号、序列号、固件等
    不存储实时状态和定价信息
    """
    __tablename__ = "charge_points"

    def __init__(self, **kwargs):
        legacy_id = kwargs.get("id")
        if legacy_id is not None:
            try:
                uuid.UUID(str(legacy_id))
            except (TypeError, ValueError, AttributeError):
                kwargs.pop("id")
                kwargs.setdefault("ocpp_identity", str(legacy_id))
        super().__init__(**kwargs)
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    # OCPP identity is controlled by the charger and must never be a relation key.
    ocpp_identity = Column(String(64), nullable=False, unique=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False, index=True)

    # Driver-facing labels are independent from the internal UUID and OCPP
    # identity. The Python default keeps legacy ORM creation paths working;
    # provisioning APIs should always accept an explicit site label.
    display_code = Column(
        String(16),
        nullable=False,
        default=lambda: f"CP-{uuid.uuid4().hex[:8].upper()}",
    )
    display_name = Column(String(80), nullable=True)
    location_hint = Column(String(160), nullable=True)
    
    # 资产信息
    vendor = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    serial_number = Column(String(100), nullable=True, unique=True, index=True)
    firmware_version = Column(String(50), nullable=True)
    # Per-device OCPP credential. Only the SHA-256 digest of the high-entropy
    # secret is persisted; the raw secret is returned once during provisioning.
    ocpp_auth_secret_hash = Column(String(64), nullable=True)
    
    # 技术规格
    max_power_kw = Column(Float, nullable=True)  # 最大功率
    
    # 关联设备（MQTT设备）
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True, index=True)
    device_serial_number = Column(String(100), nullable=True, index=True)
    
    # 运营状态
    is_active = Column(Boolean, default=True)
    commissioning_status = Column(String(20), nullable=False, default="draft")
    acceptance_report = Column(PortableJSON, nullable=True)
    last_acceptance_at = Column(DateTime(timezone=True), nullable=True)
    commissioned_at = Column(DateTime(timezone=True), nullable=True)
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    tenant = relationship("Tenant")
    site = relationship("Site", back_populates="charge_points")
    device = relationship("Device", foreign_keys=[device_id], back_populates="charge_points")
    evses = relationship("EVSE", back_populates="charge_point", cascade="all, delete-orphan")
    evse_statuses = relationship("EVSEStatus", back_populates="charge_point", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_charge_points_site', 'site_id'),
        Index('idx_charge_points_device', 'device_serial_number'),
        Index('idx_charge_points_tenant_id', 'tenant_id'),
        UniqueConstraint('site_id', 'display_code', name='uq_charge_points_site_display_code'),
        CheckConstraint("length(ocpp_identity) BETWEEN 1 AND 64", name="ck_charge_points_ocpp_identity_length"),
        CheckConstraint("length(display_code) BETWEEN 1 AND 16", name="ck_charge_points_display_code_length"),
        CheckConstraint(
            "display_code ~ '^[A-Z][A-Z0-9-]{0,15}$'",
            name="ck_charge_points_display_code_format",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "ocpp_identity ~ '^[A-Za-z0-9._:-]{1,64}$'",
            name="ck_charge_points_ocpp_identity_format",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "commissioning_status IN ('draft', 'testing', 'ready', 'commissioned', 'suspended')",
            name="ck_charge_points_commissioning_status",
        ),
    )


class EVSE(Base):
    """EVSE/连接器表（枪口）
    一个充电桩可以有多个EVSE（多枪）
    """
    __tablename__ = "evses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id"), nullable=False, index=True)
    evse_id = Column(Integer, nullable=False)  # OCPP中的evse_id
    
    # EVSE信息
    connector_type = Column(String(50), default="Type2")  # 连接器类型（从 charge_points 下放）
    max_power_kw = Column(Float, nullable=True)  # 该EVSE的最大功率
    physical_reference = Column(String(64), nullable=True)  # 现场可见的枪口/车位编号
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    tenant = relationship("Tenant")
    charge_point = relationship("ChargePoint", back_populates="evses")
    evse_status = relationship("EVSEStatus", back_populates="evse", uselist=False, cascade="all, delete-orphan")
    charging_sessions = relationship("ChargingSession", back_populates="evse", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_evses_charge_point', 'charge_point_id'),
        Index('idx_evses_charge_point_evse', 'charge_point_id', 'evse_id', unique=True),
        UniqueConstraint('charge_point_id', 'physical_reference', name='uq_evses_charge_point_physical_reference'),
        Index('idx_evses_tenant_id', 'tenant_id'),
        CheckConstraint("max_power_kw IS NULL OR max_power_kw > 0", name="ck_evses_max_power_positive"),
    )


class EVSEStatus(Base):
    """EVSE实时状态快照表
    存储每个EVSE的当前状态（用于快速查询）
    """
    __tablename__ = "evse_status"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    evse_id = Column(UUID(as_uuid=True), ForeignKey("evses.id"), nullable=False, unique=True, index=True)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id"), nullable=False, index=True)
    
    # 状态信息
    status = Column(String(50), default="Unknown", nullable=False)  # Available, Charging, Offline, Faulted, Unavailable
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # 当前会话信息（如果有）
    current_session_id = Column(UUID(as_uuid=True), ForeignKey("charging_sessions.id"), nullable=True, index=True)
    
    # 元数据
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    tenant = relationship("Tenant")
    evse = relationship("EVSE", back_populates="evse_status")
    charge_point = relationship("ChargePoint", back_populates="evse_statuses")
    current_session = relationship("ChargingSession", foreign_keys=[current_session_id])
    
    __table_args__ = (
        Index('idx_evse_status_charge_point', 'charge_point_id'),
        Index('idx_evse_status_status', 'status'),
        Index('idx_evse_status_last_seen', 'last_seen'),
        Index('idx_evse_status_tenant_id', 'tenant_id'),
    )


# ==================== 设备认证层 ====================

class Device(Base):
    """设备表
    存储设备SN号和MQTT认证信息
    每个设备独立存储master_secret（加密）
    """
    __tablename__ = "devices"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    # 设备序列号是外部业务标识，不参与内部关系主键。
    serial_number = Column(String(100), nullable=False, unique=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
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
    tenant = relationship("Tenant")
    charge_points = relationship("ChargePoint", foreign_keys="ChargePoint.device_id", back_populates="device")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'serial_number', name='unique_tenant_serial_number'),
        Index('idx_devices_type_code', 'type_code'),
        Index('idx_devices_mqtt_client_id', 'mqtt_client_id'),
        Index('idx_devices_mqtt_username', 'mqtt_username'),
        Index('idx_devices_tenant_id', 'tenant_id'),
    )


# ==================== 充电会话层 ====================

class ChargingSession(Base):
    """充电会话表（协议事实层）
    替代原来的transactions，只存储OCPP协议层面的信息
    不存储计费信息（计费在invoice层）
    """
    __tablename__ = "charging_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    evse_id = Column(UUID(as_uuid=True), ForeignKey("evses.id"), nullable=False, index=True)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id"), nullable=False, index=True)
    
    # OCPP协议信息
    transaction_id = Column(Integer, nullable=False, index=True)  # OCPP transaction_id
    id_tag = Column(String(100), nullable=False, index=True)  # RFID标签
    user_id = Column(String(100), nullable=True, index=True)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # 时间信息
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    
    # 计量信息（原始数据）
    meter_start = Column(Integer, default=0)  # 起始计量值(Wh)
    meter_stop = Column(Integer, nullable=True)  # 结束计量值(Wh)
    
    # 状态
    status = Column(String(50), default="ongoing")  # ongoing, completed, cancelled
    
    # 支付相关
    payment_status = Column(String(50), nullable=True, default="pending")  # pending, paid, unpaid
    payment_order_id = Column(UUID(as_uuid=True), ForeignKey("payment_orders.id"), nullable=True, index=True)
    payment_deadline_at = Column(DateTime(timezone=True), nullable=True)  # 支付截止时间
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    tenant = relationship("Tenant")
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
        Index('idx_charging_sessions_tenant_id', 'tenant_id'),
        CheckConstraint(
            "status IN ('ongoing', 'completed', 'cancelled')",
            name='ck_charging_sessions_status'
        ),
        UniqueConstraint('id', 'tenant_id', name='uq_charging_sessions_id_tenant'),
    )


class MeterValue(Base):
    """计量值记录表
    存储充电过程中的实时计量数据
    """
    __tablename__ = "meter_values"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("charging_sessions.id"), nullable=False, index=True)
    
    connector_id = Column(Integer, nullable=True)
    # 入站 OCPP 消息的稳定幂等键；允许为空以兼容没有消息 UUID 的旧设备。
    idempotency_key = Column(String(255), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # 计量数据
    value = Column(Integer, nullable=False)  # 主要值（Wh）
    sampled_value = Column(PortableJSON, nullable=True)  # 完整采样值数据（JSON格式）
    
    # 关系
    tenant = relationship("Tenant")
    session = relationship("ChargingSession", back_populates="meter_values")
    
    __table_args__ = (
        Index('idx_meter_values_timestamp', 'timestamp'),
        Index('idx_meter_values_session', 'session_id'),
        Index('idx_meter_values_tenant_id', 'tenant_id'),
        UniqueConstraint('session_id', 'idempotency_key', name='uq_meter_values_session_idempotency'),
    )


class OCPPMessageEvent(Base):
    """OCPP 入站消息去重记录。

    message_key 由传输层消息 ID 或规范化请求体生成。记录和领域写入使用同一事务，
    因而断线重连/重放时可以安全返回幂等结果。
    """
    __tablename__ = "ocpp_message_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id"), nullable=False, index=True)
    action = Column(String(100), nullable=False)
    # OCPP CALL UniqueId is the authoritative replay key. ``message_key`` is
    # retained for direct service calls/tests which do not enter via WebSocket.
    unique_id = Column(String(255), nullable=True)
    message_key = Column(String(255), nullable=False)
    payload = Column(PortableJSON, nullable=False)
    response_payload = Column(PortableJSON, nullable=True)
    response_message_type = Column(Integer, nullable=True)  # 3=CALLRESULT, 4=CALLERROR
    processing_status = Column(String(20), nullable=False, default="processing")
    outcome = Column(String(50), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    tenant = relationship("Tenant")
    charge_point = relationship("ChargePoint")

    __table_args__ = (
        UniqueConstraint('tenant_id', 'charge_point_id', 'action', 'message_key', name='uq_ocpp_message_event_key'),
        UniqueConstraint('tenant_id', 'charge_point_id', 'unique_id', name='uq_ocpp_message_event_unique_id'),
        Index('idx_ocpp_message_events_cp_action', 'charge_point_id', 'action'),
        Index('idx_ocpp_message_events_unique_id', 'unique_id'),
    )


class OutboxEvent(Base):
    """事务 Outbox：领域状态变更和待发送设备命令的可靠事件记录。"""
    __tablename__ = "outbox_events"

    def __init__(self, **kwargs):
        # Preserve existing tenant-scoped call sites while making delivery scope
        # explicit. Platform events must always provide their scope explicitly.
        tenant_id = kwargs.get("tenant_id")
        if kwargs.get("scope_type") is None and tenant_id is not None:
            kwargs["scope_type"] = "tenant"
        if kwargs.get("scope_ref") is None and tenant_id is not None:
            kwargs["scope_ref"] = f"tenant:{tenant_id}"
        super().__init__(**kwargs)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True, index=True)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    aggregate_type = Column(String(100), nullable=False)
    aggregate_id = Column(String(100), nullable=False)
    event_type = Column(String(100), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    payload = Column(PortableJSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    tenant = relationship("Tenant")

    __table_args__ = (
        UniqueConstraint('scope_type', 'scope_ref', 'idempotency_key', name='uq_outbox_scope_idempotency'),
        CheckConstraint(
            "(scope_type = 'platform' AND tenant_id IS NULL AND scope_ref = 'platform:eslatin') OR "
            "(scope_type = 'tenant' AND tenant_id IS NOT NULL AND length(scope_ref) = 43 "
            "AND substr(scope_ref, 1, 7) = 'tenant:' "
            "AND substr(scope_ref, 16, 1) = '-' AND substr(scope_ref, 21, 1) = '-' "
            "AND substr(scope_ref, 26, 1) = '-' AND substr(scope_ref, 31, 1) = '-' "
            "AND replace(substr(scope_ref, 8), '-', '') = replace(CAST(tenant_id AS VARCHAR), '-', ''))",
            name='ck_outbox_scope_ownership',
        ),
        Index('idx_outbox_pending', 'status', 'available_at'),
        Index('idx_outbox_aggregate', 'aggregate_type', 'aggregate_id'),
        Index('idx_outbox_scope_status_available', 'scope_type', 'scope_ref', 'status', 'available_at'),
    )


# ==================== 业务订单层 ====================

class Order(Base):
    """订单表（业务层）
    只存储业务层面的信息：用户意图、预授权、优惠、支付状态
    不存储计费信息（计费在invoice层）
    """
    __tablename__ = "orders"

    def __init__(self, **kwargs):
        _map_legacy_business_id(kwargs, "order_number")
        super().__init__(**kwargs)
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_number = Column(String(100), nullable=False, unique=True, index=True, default=lambda: _business_number("order"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("charging_sessions.id"), nullable=True, index=True)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id"), nullable=False, index=True)
    
    # 用户信息
    user_id = Column(String(100), nullable=True, index=True)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True, index=True)
    id_tag = Column(String(100), nullable=False)
    
    # 时间信息
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=True)  # 实际开始时间（可能晚于创建时间）
    end_time = Column(DateTime(timezone=True), nullable=True)
    
    # 业务状态
    status = Column(String(50), default="pending")  # pending, authorized, ongoing, completed, cancelled, failed
    
    # 预授权/优惠信息（JSON格式）
    pre_authorization = Column(PortableJSON, nullable=True)  # 预授权金额等
    discounts = Column(PortableJSON, nullable=True)  # 优惠信息
    
    # 元数据
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    tenant = relationship("Tenant")
    session = relationship("ChargingSession")
    charge_point = relationship("ChargePoint")
    invoices = relationship("Invoice", back_populates="order", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_orders_status', 'status'),
        Index('idx_orders_user_id', 'user_id'),
        Index('idx_orders_created_at', 'created_at'),
        Index('idx_orders_tenant_id', 'tenant_id'),
    )


# ==================== 定价和结算层 ====================

class Tariff(Base):
    """定价规则表
    存储定价规则（站点、时段、活动等）
    """
    __tablename__ = "tariffs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True, index=True)  # 站点级别定价
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id"), nullable=True, index=True)  # 桩级别定价
    
    # 定价规则
    name = Column(String(200), nullable=False)  # 定价规则名称
    base_price_per_kwh = Column(Numeric(10, 2), nullable=False)  # 基础电价
    service_fee = Column(Numeric(10, 2), default=0)  # 服务费
    
    # 时段定价（JSON格式存储复杂规则）
    time_based_rules = Column(PortableJSON, nullable=True)  # 时段定价规则
    
    # 有效期
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    
    # 状态
    is_active = Column(Boolean, default=True)
    
    # 元数据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    tenant = relationship("Tenant")
    site = relationship("Site")
    charge_point = relationship("ChargePoint")
    pricing_snapshots = relationship("PricingSnapshot", back_populates="tariff", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_tariffs_site', 'site_id'),
        Index('idx_tariffs_charge_point', 'charge_point_id'),
        Index('idx_tariffs_valid', 'valid_from', 'valid_until'),
        Index('idx_tariffs_tenant_id', 'tenant_id'),
        CheckConstraint('base_price_per_kwh >= 0', name='ck_tariffs_base_price_nonnegative'),
        CheckConstraint('service_fee >= 0', name='ck_tariffs_service_fee_nonnegative'),
    )


class PricingSnapshot(Base):
    """定价快照表
    在订单/会话创建时固化当时的定价信息
    用于可追溯的结算
    """
    __tablename__ = "pricing_snapshots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    tariff_id = Column(UUID(as_uuid=True), ForeignKey("tariffs.id"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("charging_sessions.id"), nullable=True, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True, index=True)
    
    # 快照的定价信息
    price_per_kwh = Column(Numeric(10, 2), nullable=False)
    service_fee = Column(Numeric(10, 2), default=0)
    snapshot_data = Column(PortableJSON, nullable=True)  # 完整的定价规则快照
    
    # 快照时间
    snapshot_time = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # 关系
    tenant = relationship("Tenant")
    tariff = relationship("Tariff", back_populates="pricing_snapshots")
    session = relationship("ChargingSession")
    order = relationship("Order")
    
    __table_args__ = (
        Index('idx_pricing_snapshots_session', 'session_id'),
        Index('idx_pricing_snapshots_order', 'order_id'),
        Index('idx_pricing_snapshots_tenant_id', 'tenant_id'),
        CheckConstraint('price_per_kwh >= 0', name='ck_pricing_snapshots_price_nonnegative'),
        CheckConstraint('service_fee >= 0', name='ck_pricing_snapshots_service_fee_nonnegative'),
    )


class Invoice(Base):
    """发票/账单表（结算权威）
    存储最终结算信息，所有计费字段的权威来源
    """
    __tablename__ = "invoices"

    def __init__(self, **kwargs):
        _map_legacy_business_id(kwargs, "invoice_number")
        super().__init__(**kwargs)
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    invoice_number = Column(String(100), nullable=False, unique=True, index=True, default=lambda: _business_number("invoice"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("charging_sessions.id"), nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True, index=True)
    pricing_snapshot_id = Column(UUID(as_uuid=True), ForeignKey("pricing_snapshots.id"), nullable=False, index=True)
    
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
    tenant = relationship("Tenant")
    session = relationship("ChargingSession", back_populates="invoices")
    order = relationship("Order", back_populates="invoices")
    pricing_snapshot = relationship("PricingSnapshot")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_invoices_status', 'status'),
        Index('idx_invoices_session', 'session_id'),
        Index('idx_invoices_order', 'order_id'),
        Index('idx_invoices_issued_at', 'issued_at'),
        Index('idx_invoices_tenant_id', 'tenant_id'),
        UniqueConstraint('session_id', name='uq_invoices_session'),
        UniqueConstraint('id', 'tenant_id', name='uq_invoices_id_tenant'),
        UniqueConstraint('id', 'session_id', 'tenant_id', name='uq_invoices_id_session_tenant'),
    )


class Payment(Base):
    """支付流水表
    存储所有支付记录
    """
    __tablename__ = "payments"

    def __init__(self, **kwargs):
        _map_legacy_business_id(kwargs, "payment_number")
        super().__init__(**kwargs)
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    payment_number = Column(String(100), nullable=False, unique=True, index=True, default=lambda: _business_number("payment"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    
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
    tenant = relationship("Tenant")
    invoice = relationship("Invoice", back_populates="payments")
    
    __table_args__ = (
        Index('idx_payments_status', 'status'),
        Index('idx_payments_invoice', 'invoice_id'),
        Index('idx_payments_transaction_id', 'transaction_id'),
        Index('idx_payments_tenant_id', 'tenant_id'),
    )


class AppWalletTransaction(Base):
    """平台钱包流水（爆改测试版）

    - 余额权威字段：AppUser.balance（平台统一钱包）
    - operator_tenant_id：本次消费/业务归属的运营商租户，用于对账/分账
    """
    __tablename__ = "app_wallet_transactions"

    def __init__(self, **kwargs):
        _map_legacy_business_id(kwargs, "transaction_number")
        super().__init__(**kwargs)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    transaction_number = Column(String(100), nullable=False, unique=True, index=True, default=lambda: _business_number("wallet"))
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_order_id = Column(UUID(as_uuid=True), ForeignKey("payment_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)

    operator_tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id"), nullable=True, index=True)

    # amount > 0 入账（top_up），amount < 0 扣费（charge）
    type = Column(String(50), nullable=False)  # top_up / charge
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(Text, nullable=True)
    idempotency_key = Column(String(255), nullable=True, index=True)
    adjusted_by_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    app_user = relationship("AppUser")
    invoice = relationship("Invoice")
    operator_tenant = relationship("Tenant")
    charge_point = relationship("ChargePoint")

    __table_args__ = (
        Index("idx_app_wallet_tx_user", "app_user_id", "created_at"),
        Index("idx_app_wallet_tx_operator_tenant", "operator_tenant_id"),
        Index("idx_app_wallet_tx_charge_point", "charge_point_id"),
        UniqueConstraint("payment_order_id", "type", name="uq_app_wallet_tx_payment_type"),
        UniqueConstraint("app_user_id", "idempotency_key", name="uq_app_wallet_tx_user_idempotency"),
        CheckConstraint("amount <> 0", name="ck_app_wallet_tx_amount_nonzero"),
    )


class QrToken(Base):
    """二维码 token 映射（爆改测试版）

    二维码 payload 只包含不可猜测 token（例如：qr:<token>），后端解析 token 得到：
    - operator_tenant_id（运营商租户）
    - charge_point_id（充电桩）
    - connector_id（枪口/EVSE 编号）
    """
    __tablename__ = "qr_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    token = Column(String(128), nullable=False, unique=True, index=True)
    operator_tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id", ondelete="CASCADE"), nullable=False, index=True)
    connector_id = Column(Integer, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    operator_tenant = relationship("Tenant")
    charge_point = relationship("ChargePoint")

    __table_args__ = (
        UniqueConstraint("charge_point_id", "connector_id", name="unique_qr_token_cp_connector"),
        Index("idx_qr_tokens_operator_tenant", "operator_tenant_id"),
        Index("idx_qr_tokens_charge_point", "charge_point_id"),
    )


# ==================== 支付层（Wompi）====================

class PaymentOrder(Base):
    """支付订单表（支持 Wompi 和 Mercado Pago）
    
    订单金额和币种一旦创建就不可变，用于防止串单/篡改
    """
    __tablename__ = "payment_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 订单信息（不可变）
    type = Column(String(50), nullable=False)  # top_up 或 charging
    amount = Column(Numeric(10, 2), nullable=False)  # 不可变，创建后禁止修改
    currency = Column(String(3), nullable=False, default="COP")  # 不可变，创建后禁止修改
    
    # 支付提供商
    payment_provider = Column(String(50), nullable=False, default="wompi", index=True)  # 'wompi' 或 'mercadopago'
    idempotency_key = Column(String(255), nullable=True, index=True)
    
    # Wompi 相关（保留用于兼容）
    reference = Column(String(128), nullable=True, unique=True, index=True)  # 唯一参考号，格式：ESL-YYYYMMDD-{6位随机字符}
    integrity_signature = Column(String(512), nullable=True)  # 完整性签名
    wompi_transaction_id = Column(String(255), nullable=True)  # Wompi 交易ID
    
    # Mercado Pago 相关
    external_reference = Column(String(128), nullable=True, unique=True, index=True)  # Mercado Pago 外部参考号
    mercadopago_payment_id = Column(String(255), nullable=True)  # Mercado Pago payment.id
    
    # 状态（只能向终态推进，不允许回退）
    status = Column(String(50), nullable=False, default="created")  # created, processing, approved, declined, voided, error, expired, refunded
    
    # URL 和时间
    redirect_url = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)  # 订单过期时间（必须设置）
    payment_deadline_at = Column(DateTime(timezone=True), nullable=True)  # 支付截止时间（充电支付场景）
    
    # 元数据（JSONB）
    order_metadata = Column("metadata", PortableJSON, nullable=True)  # 存储额外信息，如充电 session_id、charge_point_id、site_id（映射到数据库的metadata字段）
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    paid_at = Column(DateTime(timezone=True), nullable=True)  # 支付完成时间
    
    app_user = relationship("AppUser", backref="payment_orders")
    charging_sessions = relationship("ChargingSession", backref="payment_order")
    
    __table_args__ = (
        Index("idx_payment_orders_user", "app_user_id", "created_at"),
        Index("idx_payment_orders_status", "status"),
        Index("idx_payment_orders_type", "type"),
        Index("idx_payment_orders_provider", "payment_provider"),
        UniqueConstraint("app_user_id", "idempotency_key", name="uq_payment_orders_user_idempotency"),
        UniqueConstraint("wompi_transaction_id", name="uq_payment_orders_wompi_transaction_id"),
        UniqueConstraint("mercadopago_payment_id", name="uq_payment_orders_mercadopago_payment_id"),
        CheckConstraint('amount > 0', name='ck_payment_orders_amount_positive'),
        CheckConstraint(
            "status IN ('created', 'processing', 'approved', 'declined', 'voided', 'error', 'expired', 'refunded')",
            name='ck_payment_orders_status'
        ),
    )


class PaymentWebhookEvent(Base):
    """Webhook 事件记录表（用于幂等性控制）
    
    确保同一个 transaction_id + event_id 只处理一次
    支持 Wompi 和 Mercado Pago
    """
    __tablename__ = "payment_webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    payment_order_id = Column(UUID(as_uuid=True), ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 支付提供商
    payment_provider = Column(String(50), nullable=False, index=True)  # 'wompi' 或 'mercadopago'
    
    # Wompi 相关（保留用于兼容）
    wompi_transaction_id = Column(String(255), nullable=True, index=True)
    wompi_event_id = Column(String(255), nullable=True)  # Wompi 事件ID
    
    # 通用字段（用于 Mercado Pago 和其他提供商）
    payment_provider_id = Column(String(255), nullable=True, index=True)  # 通用支付提供商 ID（如 MP 的 payment.id）
    event_id = Column(String(255), nullable=True)  # 通用事件 ID（如 MP 的 notification.id）
    
    event_type = Column(String(100), nullable=True)  # transaction.updated, payment.created, payment.updated 等
    
    payload = Column(PortableJSON, nullable=True)  # 存储原始 webhook 数据
    
    processed = Column(Boolean, nullable=False, default=False)  # 是否已处理
    processed_at = Column(DateTime(timezone=True), nullable=True)  # 处理时间
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    payment_order = relationship("PaymentOrder", backref="webhook_events")
    
    __table_args__ = (
        UniqueConstraint("wompi_transaction_id", "wompi_event_id", name="unique_webhook_event_wompi"),
        UniqueConstraint("payment_provider", "payment_provider_id", "event_id", name="unique_webhook_event_generic"),
        Index("idx_webhook_events_order", "payment_order_id"),
        Index("idx_webhook_events_processed", "processed"),
        Index("idx_webhook_events_provider", "payment_provider"),
    )


# ==================== PAY-MP-002 typed financial facts ====================

class RiskPolicyVersion(Base):
    """Immutable D-204-B policy snapshot used by risk sessions."""
    __tablename__ = "risk_policy_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_version = Column(String(100), nullable=False, unique=True)
    schema_version = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="active")
    effective_at = Column(DateTime(timezone=True), nullable=False)
    approved_reference = Column(String(255), nullable=False)
    session_amount_cop = Column(Numeric(18, 2), nullable=False)
    session_energy_kwh = Column(Numeric(18, 3), nullable=False)
    session_duration_minutes = Column(Integer, nullable=False)
    user_open_cop = Column(Numeric(18, 2), nullable=False)
    site_window_cop = Column(Numeric(18, 2), nullable=False)
    platform_window_cop = Column(Numeric(18, 2), nullable=False)
    meter_degraded_after_seconds = Column(Integer, nullable=False)
    meter_stop_after_seconds = Column(Integer, nullable=False)
    offline_unknown_amount_cop = Column(Numeric(18, 2), nullable=False)
    offline_unknown_duration_seconds = Column(Integer, nullable=False)
    remote_stop_first_attempt_seconds = Column(Integer, nullable=False)
    remote_stop_max_attempts = Column(Integer, nullable=False)
    stop_transaction_timeout_seconds = Column(Integer, nullable=False)
    recovery_check_after_seconds = Column(Integer, nullable=False)
    final_resolution_after_seconds = Column(Integer, nullable=False)
    aggregate_window_kind = Column(String(20), nullable=False, default="rolling")
    aggregate_window_seconds = Column(Integer, nullable=False, default=86400)
    time_basis = Column(String(30), nullable=False, default="utc_timestamp")
    calendar_midnight_reset = Column(Boolean, nullable=False, default=False)
    included_exposure = Column(PortableJSON, nullable=False, default=lambda: ["active_reservations", "unresolved_exposure"])
    excluded_exposure = Column(PortableJSON, nullable=False, default=lambda: ["released_exposure", "settled_exposure"])
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint("status IN ('active', 'retired')", name="ck_risk_policy_status"),
        CheckConstraint("schema_version >= 1", name="ck_risk_policy_schema_version"),
        CheckConstraint("session_amount_cop > 0 AND session_energy_kwh > 0 AND session_duration_minutes > 0", name="ck_risk_policy_session_limits"),
        CheckConstraint("user_open_cop > 0 AND site_window_cop > 0 AND platform_window_cop > 0", name="ck_risk_policy_exposure_limits"),
        CheckConstraint("meter_degraded_after_seconds > 0 AND meter_stop_after_seconds > meter_degraded_after_seconds", name="ck_risk_policy_meter_sla"),
        CheckConstraint("offline_unknown_amount_cop > 0 AND offline_unknown_duration_seconds > 0", name="ck_risk_policy_unknown_buffer"),
        CheckConstraint("remote_stop_first_attempt_seconds > 0 AND remote_stop_max_attempts BETWEEN 1 AND 3", name="ck_risk_policy_stop_attempts"),
        CheckConstraint("stop_transaction_timeout_seconds > 0 AND recovery_check_after_seconds > 0 AND final_resolution_after_seconds > 0", name="ck_risk_policy_recovery_sla"),
        CheckConstraint("aggregate_window_kind = 'rolling' AND aggregate_window_seconds = 86400 AND time_basis = 'utc_timestamp' AND calendar_midnight_reset = false", name="ck_risk_policy_window"),
        Index("idx_risk_policy_effective", "status", "effective_at"),
    )


class RiskExposureBalance(Base):
    """Rebuildable lock/index row; RiskLedgerEntry remains the authority."""
    __tablename__ = "risk_exposure_balances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(255), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=True)
    policy_version_id = Column(UUID(as_uuid=True), ForeignKey("risk_policy_versions.id", ondelete="RESTRICT"), nullable=False)
    current_exposure_cop = Column(Numeric(18, 2), nullable=False, default=0)
    window_started_at = Column(DateTime(timezone=True), nullable=False)
    window_ends_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("scope_type", "scope_ref", "policy_version_id", name="uq_risk_exposure_scope_policy"),
        CheckConstraint("scope_type IN ('user', 'site', 'platform')", name="ck_risk_exposure_scope_type"),
        CheckConstraint("current_exposure_cop >= 0 AND version >= 1", name="ck_risk_exposure_values"),
        Index("idx_risk_exposure_scope", "scope_type", "scope_ref"),
    )


class RiskReservation(Base):
    """Lifecycle projection for one charging session/pinned policy."""
    __tablename__ = "risk_reservations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id", ondelete="RESTRICT"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("charging_sessions.id", ondelete="RESTRICT"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=True)
    policy_version_id = Column(UUID(as_uuid=True), ForeignKey("risk_policy_versions.id", ondelete="RESTRICT"), nullable=False)
    policy_version = Column(String(100), nullable=False)
    state = Column(String(40), nullable=False, default="reserved")
    reserved_cop = Column(Numeric(18, 2), nullable=False)
    consumed_cop = Column(Numeric(18, 2), nullable=False, default=0)
    unresolved_cop = Column(Numeric(18, 2), nullable=False, default=0)
    reserved_energy_kwh = Column(Numeric(18, 3), nullable=False)
    consumed_energy_kwh = Column(Numeric(18, 3), nullable=False, default=0)
    elapsed_minutes = Column(Numeric(18, 2), nullable=False, default=0)
    last_meter_wh = Column(Integer, nullable=True)
    last_meter_at = Column(DateTime(timezone=True), nullable=True)
    meter_freshness = Column(String(20), nullable=False, default="unknown")
    unknown_started_at = Column(DateTime(timezone=True), nullable=True)
    unknown_cop = Column(Numeric(18, 2), nullable=False, default=0)
    physical_stop_confirmed = Column(Boolean, nullable=False, default=False)
    final_invoice_confirmed = Column(Boolean, nullable=False, default=False)
    provider_resolved = Column(Boolean, nullable=False, default=False)
    idempotency_key = Column(String(255), nullable=False)
    request_fingerprint = Column(String(128), nullable=False)
    source_event_id = Column(String(255), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("session_id", "policy_version_id", name="uq_risk_reservation_session_policy"),
        UniqueConstraint("id", "tenant_id", name="uq_risk_reservation_id_tenant"),
        CheckConstraint("state IN ('reserved', 'consuming', 'stop_requested', 'physical_stop_pending', 'settlement_pending', 'release_pending', 'released', 'unresolved', 'resolving')", name="ck_risk_reservation_state"),
        CheckConstraint("reserved_cop > 0 AND consumed_cop >= 0 AND unresolved_cop >= 0 AND consumed_cop <= reserved_cop", name="ck_risk_reservation_money"),
        CheckConstraint("reserved_energy_kwh > 0 AND consumed_energy_kwh >= 0 AND consumed_energy_kwh <= reserved_energy_kwh AND elapsed_minutes >= 0", name="ck_risk_reservation_usage"),
        CheckConstraint("meter_freshness IN ('fresh', 'degraded', 'stale', 'unknown')", name="ck_risk_reservation_meter_freshness"),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_risk_reservation_versions"),
        Index("idx_risk_reservation_scope_state", "site_id", "state", "created_at"),
        Index("idx_risk_reservation_user_state", "app_user_id", "state"),
        Index("idx_risk_reservation_platform_window", "created_at", "state"),
    )


class RiskLedgerEntry(Base):
    """Append-only risk action fact; never update or delete."""
    __tablename__ = "risk_ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(255), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("charging_sessions.id", ondelete="RESTRICT"), nullable=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=True)
    policy_version_id = Column(UUID(as_uuid=True), ForeignKey("risk_policy_versions.id", ondelete="RESTRICT"), nullable=False)
    policy_version = Column(String(100), nullable=False)
    action = Column(String(20), nullable=False)
    amount_cop = Column(Numeric(18, 2), nullable=False, default=0)
    delta_cop = Column(Numeric(18, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="COP")
    energy_kwh = Column(Numeric(18, 3), nullable=False, default=0)
    duration_minutes = Column(Numeric(18, 2), nullable=False, default=0)
    source_event_id = Column(String(255), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    before_balance_cop = Column(Numeric(18, 2), nullable=False, default=0)
    after_balance_cop = Column(Numeric(18, 2), nullable=False, default=0)
    data_quality = Column(String(20), nullable=False, default="authoritative")
    reason_code = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        UniqueConstraint("scope_type", "scope_ref", "action", "source_event_id", name="uq_risk_ledger_scope_action_source"),
        UniqueConstraint("scope_type", "scope_ref", "idempotency_key", name="uq_risk_ledger_scope_idempotency"),
        CheckConstraint("scope_type IN ('user', 'site', 'platform')", name="ck_risk_ledger_scope_type"),
        CheckConstraint("action IN ('reserve', 'consume', 'release', 'unresolved', 'correction')", name="ck_risk_ledger_action"),
        CheckConstraint("amount_cop >= 0 AND delta_cop >= 0 AND energy_kwh >= 0 AND duration_minutes >= 0", name="ck_risk_ledger_values"),
        CheckConstraint("currency = 'COP'", name="ck_risk_ledger_currency"),
        CheckConstraint("data_quality IN ('authoritative', 'degraded', 'unknown')", name="ck_risk_ledger_quality"),
        Index("idx_risk_ledger_session_action", "session_id", "action", "created_at"),
        Index("idx_risk_ledger_scope_created", "scope_type", "scope_ref", "created_at"),
    )


class RiskStopAction(Base):
    """Durable RemoteStop command lifecycle; Accepted is not physical stop."""
    __tablename__ = "risk_stop_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    reservation_id = Column(UUID(as_uuid=True), ForeignKey("risk_reservations.id", ondelete="RESTRICT"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("charging_sessions.id", ondelete="RESTRICT"), nullable=False)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id", ondelete="RESTRICT"), nullable=False)
    policy_version_id = Column(UUID(as_uuid=True), ForeignKey("risk_policy_versions.id", ondelete="RESTRICT"), nullable=False)
    transaction_id = Column(Integer, nullable=False)
    status = Column(String(40), nullable=False, default="queued")
    reason_code = Column(String(100), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    max_automatic_attempts = Column(Integer, nullable=False, default=3)
    first_attempt_due_at = Column(DateTime(timezone=True), nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    stop_transaction_due_at = Column(DateTime(timezone=True), nullable=False)
    physical_stop_confirmed = Column(Boolean, nullable=False, default=False)
    command_id = Column(String(255), nullable=False)
    last_error = Column(String(255), nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("reservation_id", "reason_code", name="uq_risk_stop_reservation_reason"),
        UniqueConstraint("command_id", name="uq_risk_stop_command"),
        CheckConstraint("status IN ('queued', 'sending', 'accepted_pending_physical_stop', 'retry_scheduled', 'confirmed', 'physical_stop_failed', 'unresolved')", name="ck_risk_stop_status"),
        CheckConstraint("attempts >= 0 AND max_automatic_attempts BETWEEN 1 AND 3", name="ck_risk_stop_attempts"),
        CheckConstraint("version >= 1", name="ck_risk_stop_version"),
        Index("idx_risk_stop_due", "status", "first_attempt_due_at", "stop_transaction_due_at"),
    )


class ProviderResolution(Base):
    """One canonical Provider operation/query convergence record."""
    __tablename__ = "provider_resolutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    reservation_id = Column(UUID(as_uuid=True), ForeignKey("risk_reservations.id", ondelete="RESTRICT"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("charging_sessions.id", ondelete="RESTRICT"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=True)
    provider = Column(String(50), nullable=False)
    provider_operation_key = Column(String(255), nullable=False)
    provider_reference = Column(String(255), nullable=True)
    status = Column(String(40), nullable=False, default="pending")
    unknown_since = Column(DateTime(timezone=True), nullable=True)
    final_due_at = Column(DateTime(timezone=True), nullable=False)
    next_check_at = Column(DateTime(timezone=True), nullable=True)
    duplicate_create_blocked = Column(Boolean, nullable=False, default=True)
    last_error_code = Column(String(100), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("provider", "provider_operation_key", name="uq_provider_resolution_operation"),
        UniqueConstraint("reservation_id", name="uq_provider_resolution_reservation"),
        CheckConstraint("status IN ('not_required', 'pending', 'checking', 'resolved_approved', 'resolved_rejected', 'terminal_unresolved')", name="ck_provider_resolution_status"),
        CheckConstraint("version >= 1", name="ck_provider_resolution_version"),
        Index("idx_provider_resolution_due", "status", "next_check_at", "final_due_at"),
    )

class RecoveryAttempt(Base):
    """Immutable request identity and canonical state for one invoice recovery."""
    __tablename__ = "recovery_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), nullable=False)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    method = Column(String(20), nullable=False)
    provider = Column(String(50), nullable=True)
    provider_account_ref = Column(String(100), nullable=True)
    provider_operation_key = Column(String(255), nullable=True)
    provider_payment_ref = Column(String(255), nullable=True)
    target_amount = Column(Numeric(18, 2), nullable=False)
    allocated_amount = Column(Numeric(18, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="COP")
    status = Column(String(30), nullable=False, default="created")
    reason_code = Column(String(100), nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    request_fingerprint = Column(String(128), nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(
            ["invoice_id", "session_id", "tenant_id"],
            ["invoices.id", "invoices.session_id", "invoices.tenant_id"],
            name="fk_recovery_attempt_invoice_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("app_user_id", "idempotency_key", name="uq_recovery_attempt_user_idempotency"),
        UniqueConstraint("invoice_id", "attempt_number", name="uq_recovery_attempt_invoice_number"),
        UniqueConstraint("provider", "provider_operation_key", name="uq_recovery_attempt_provider_operation"),
        UniqueConstraint("id", "invoice_id", "tenant_id", name="uq_recovery_attempt_id_invoice_tenant"),
        CheckConstraint("attempt_number > 0", name="ck_recovery_attempt_number_positive"),
        CheckConstraint("target_amount > 0", name="ck_recovery_attempt_target_positive"),
        CheckConstraint("allocated_amount >= 0 AND allocated_amount <= target_amount", name="ck_recovery_attempt_allocated_range"),
        CheckConstraint("currency = 'COP'", name="ck_recovery_attempt_currency"),
        CheckConstraint("method IN ('wallet', 'new_card', 'saved_card')", name="ck_recovery_attempt_method"),
        CheckConstraint(
            "status IN ('created', 'processing', 'action_required', 'provider_approved', 'allocated', "
            "'declined', 'failed', 'cancelled', 'expired', 'duplicate_approved', 'unknown')",
            name="ck_recovery_attempt_status",
        ),
        CheckConstraint("schema_version >= 1 AND version >= 1", name="ck_recovery_attempt_versions"),
        Index("idx_recovery_attempt_tenant_status", "tenant_id", "status", "updated_at"),
        Index("idx_recovery_attempt_invoice_status", "invoice_id", "status"),
        Index("idx_recovery_attempt_user_created", "app_user_id", "created_at"),
        Index("idx_recovery_attempt_provider_ref", "provider", "provider_payment_ref"),
    )


class PaymentAllocation(Base):
    """Single invoice settlement winner; append/reverse rather than overwrite."""
    __tablename__ = "payment_allocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), nullable=False)
    recovery_attempt_id = Column(UUID(as_uuid=True), nullable=False)
    payment_order_id = Column(UUID(as_uuid=True), ForeignKey("payment_orders.id", ondelete="RESTRICT"), nullable=True)
    wallet_transaction_id = Column(UUID(as_uuid=True), ForeignKey("app_wallet_transactions.id", ondelete="RESTRICT"), nullable=True)
    method = Column(String(20), nullable=False)
    provider = Column(String(50), nullable=True)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="COP")
    status = Column(String(20), nullable=False, default="pending")
    winner_version = Column(Integer, nullable=False, default=1)
    reversal_reason = Column(String(100), nullable=True)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    committed_at = Column(DateTime(timezone=True), nullable=True)
    reversed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(
            ["recovery_attempt_id", "invoice_id", "tenant_id"],
            ["recovery_attempts.id", "recovery_attempts.invoice_id", "recovery_attempts.tenant_id"],
            name="fk_payment_allocation_attempt_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("recovery_attempt_id", name="uq_payment_allocation_recovery_attempt"),
        UniqueConstraint("id", "tenant_id", name="uq_payment_allocation_id_tenant"),
        UniqueConstraint("id", "invoice_id", "tenant_id", name="uq_payment_allocation_id_invoice_tenant"),
        CheckConstraint("amount > 0", name="ck_payment_allocation_amount_positive"),
        CheckConstraint("currency = 'COP'", name="ck_payment_allocation_currency"),
        CheckConstraint("method IN ('wallet', 'new_card', 'saved_card')", name="ck_payment_allocation_method"),
        CheckConstraint("status IN ('pending', 'committed', 'reversed', 'failed', 'needs_review')", name="ck_payment_allocation_status"),
        CheckConstraint("winner_version >= 1 AND schema_version >= 1", name="ck_payment_allocation_versions"),
        Index(
            "uq_payment_allocation_committed_invoice",
            "invoice_id",
            unique=True,
            postgresql_where=text("status = 'committed'"),
            sqlite_where=text("status = 'committed'"),
        ),
        Index("idx_payment_allocation_tenant_status", "tenant_id", "status", "updated_at"),
    )


class FinancialEligibilityDecision(Base):
    """Rebuildable platform-level D1 decision snapshot; not a risk ledger."""
    __tablename__ = "financial_eligibility_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    operation = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    reason_codes = Column(PortableJSON, nullable=False, default=list)
    blocking_resources = Column(PortableJSON, nullable=False, default=list)
    version = Column(Integer, nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    evaluated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("app_user_id", "operation", name="uq_financial_eligibility_user_operation"),
        CheckConstraint("operation = 'paid_charging_admission'", name="ck_financial_eligibility_operation"),
        CheckConstraint("status IN ('eligible', 'blocked', 'recheck_required', 'unknown')", name="ck_financial_eligibility_status"),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_financial_eligibility_versions"),
        Index("idx_financial_eligibility_status_evaluated", "status", "evaluated_at"),
    )


class RefundCase(Base):
    __tablename__ = "refund_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_reference = Column(String(100), nullable=False, unique=True, default=lambda: _business_number("refund"))
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), nullable=False)
    payment_allocation_id = Column(UUID(as_uuid=True), nullable=False)
    requested_amount = Column(Numeric(18, 2), nullable=False)
    approved_amount = Column(Numeric(18, 2), nullable=False, default=0)
    refunded_amount = Column(Numeric(18, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="COP")
    reason_code = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False, default="submitted")
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(
            ["payment_allocation_id", "invoice_id", "tenant_id"],
            ["payment_allocations.id", "payment_allocations.invoice_id", "payment_allocations.tenant_id"],
            name="fk_refund_case_allocation_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_refund_case_id_tenant"),
        CheckConstraint("requested_amount > 0", name="ck_refund_case_requested_positive"),
        CheckConstraint("approved_amount >= 0 AND approved_amount <= requested_amount", name="ck_refund_case_approved_range"),
        CheckConstraint("refunded_amount >= 0 AND refunded_amount <= approved_amount", name="ck_refund_case_refunded_range"),
        CheckConstraint("currency = 'COP'", name="ck_refund_case_currency"),
        CheckConstraint(
            "status IN ('submitted', 'under_review', 'approved', 'provider_processing', 'partially_refunded', "
            "'refunded', 'rejected', 'manual_review', 'unknown')",
            name="ck_refund_case_status",
        ),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_refund_case_versions"),
        Index("idx_refund_case_tenant_status", "tenant_id", "status", "updated_at"),
        Index("idx_refund_case_invoice_created", "invoice_id", "created_at"),
    )


class RefundApproval(Base):
    __tablename__ = "refund_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    refund_case_id = Column(UUID(as_uuid=True), nullable=False)
    initiator_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False)
    approver_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    requested_amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="COP")
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    decided_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(["refund_case_id", "tenant_id"], ["refund_cases.id", "refund_cases.tenant_id"], name="fk_refund_approval_case_owner", ondelete="RESTRICT"),
        CheckConstraint("requested_amount > 0", name="ck_refund_approval_amount_positive"),
        CheckConstraint("currency = 'COP'", name="ck_refund_approval_currency"),
        CheckConstraint("status IN ('not_required', 'pending', 'approved', 'rejected', 'expired', 'unknown')", name="ck_refund_approval_status"),
        CheckConstraint("approver_admin_id IS NULL OR approver_admin_id <> initiator_admin_id", name="ck_refund_approval_distinct_actors"),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_refund_approval_versions"),
        Index("idx_refund_approval_case_status", "refund_case_id", "status"),
    )


class RefundAttempt(Base):
    __tablename__ = "refund_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    refund_case_id = Column(UUID(as_uuid=True), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    provider = Column(String(50), nullable=False)
    provider_account_ref = Column(String(100), nullable=False)
    provider_operation_key = Column(String(255), nullable=False)
    provider_refund_ref = Column(String(255), nullable=True)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="COP")
    status = Column(String(30), nullable=False, default="processing")
    reason_code = Column(String(100), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(["refund_case_id", "tenant_id"], ["refund_cases.id", "refund_cases.tenant_id"], name="fk_refund_attempt_case_owner", ondelete="RESTRICT"),
        UniqueConstraint("refund_case_id", "attempt_number", name="uq_refund_attempt_case_number"),
        UniqueConstraint("provider", "provider_operation_key", name="uq_refund_attempt_provider_operation"),
        CheckConstraint("attempt_number > 0 AND amount > 0", name="ck_refund_attempt_positive"),
        CheckConstraint("currency = 'COP'", name="ck_refund_attempt_currency"),
        CheckConstraint("status IN ('processing', 'partially_refunded', 'refunded', 'failed', 'manual_review', 'unknown')", name="ck_refund_attempt_status"),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_refund_attempt_versions"),
        Index("idx_refund_attempt_case_status", "refund_case_id", "status"),
    )


class ChargebackCase(Base):
    __tablename__ = "chargeback_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_reference = Column(String(100), nullable=False, unique=True, default=lambda: _business_number("chargeback"))
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), nullable=False)
    payment_allocation_id = Column(UUID(as_uuid=True), nullable=False)
    provider = Column(String(50), nullable=False)
    provider_account_ref = Column(String(100), nullable=False)
    provider_dispute_ref = Column(String(255), nullable=False)
    disputed_amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="COP")
    status = Column(String(20), nullable=False, default="received")
    reason_code = Column(String(100), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(
            ["payment_allocation_id", "invoice_id", "tenant_id"],
            ["payment_allocations.id", "payment_allocations.invoice_id", "payment_allocations.tenant_id"],
            name="fk_chargeback_case_allocation_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("provider", "provider_dispute_ref", name="uq_chargeback_provider_dispute"),
        UniqueConstraint("id", "tenant_id", name="uq_chargeback_case_id_tenant"),
        CheckConstraint("disputed_amount > 0", name="ck_chargeback_amount_positive"),
        CheckConstraint("currency = 'COP'", name="ck_chargeback_currency"),
        CheckConstraint("status IN ('received', 'under_review', 'hold', 'representment', 'won', 'lost', 'reversed', 'unknown')", name="ck_chargeback_status"),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_chargeback_versions"),
        Index("idx_chargeback_tenant_status", "tenant_id", "status", "updated_at"),
    )


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True)
    provider = Column(String(50), nullable=False)
    provider_account_ref = Column(String(100), nullable=False)
    business_date = Column(Date, nullable=False)
    run_type = Column(String(20), nullable=False, default="continuous")
    source_checksum = Column(String(128), nullable=False)
    cutoff_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    source_watermarks = Column(PortableJSON, nullable=False, default=dict)
    status = Column(String(40), nullable=False, default="created")
    item_count = Column(Integer, nullable=False, default=0)
    matched_count = Column(Integer, nullable=False, default=0)
    exception_count = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("provider", "provider_account_ref", "business_date", "source_checksum", name="uq_reconciliation_run_source"),
        UniqueConstraint("id", "scope_type", "scope_ref", name="uq_reconciliation_run_scope"),
        CheckConstraint(
            "(scope_type = 'platform' AND tenant_id IS NULL AND scope_ref = 'platform:eslatin') OR "
            "(scope_type = 'tenant' AND tenant_id IS NOT NULL AND length(scope_ref) = 43 "
            "AND substr(scope_ref, 1, 7) = 'tenant:' "
            "AND substr(scope_ref, 16, 1) = '-' AND substr(scope_ref, 21, 1) = '-' "
            "AND substr(scope_ref, 26, 1) = '-' AND substr(scope_ref, 31, 1) = '-' "
            "AND replace(substr(scope_ref, 8), '-', '') = replace(CAST(tenant_id AS VARCHAR), '-', ''))",
            name="ck_reconciliation_run_scope",
        ),
        CheckConstraint("status IN ('created', 'running', 'completed', 'completed_with_exceptions', 'failed', 'unknown')", name="ck_reconciliation_run_status"),
        CheckConstraint("run_type IN ('continuous', 'daily')", name="ck_reconciliation_run_type"),
        CheckConstraint("item_count >= 0 AND matched_count >= 0 AND exception_count >= 0", name="ck_reconciliation_run_counts"),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_reconciliation_run_versions"),
        Index("idx_reconciliation_run_business_status", "business_date", "status", "provider"),
    )


class ReconciliationItem(Base):
    __tablename__ = "reconciliation_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reconciliation_run_id = Column(UUID(as_uuid=True), nullable=False)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True)
    provider = Column(String(50), nullable=False)
    source_reference = Column(String(255), nullable=False)
    # Nullable keeps legacy BE-203 diagnostic rows insert-compatible; every
    # BE-208-created item always supplies the canonical reference explicitly.
    canonical_reference = Column(String(255), nullable=True)
    source_type = Column(String(20), nullable=False, default="provider")
    eslatin_reference = Column(String(255), nullable=True)
    provider_reference = Column(String(255), nullable=True)
    funds_reference = Column(String(255), nullable=True)
    merchant_reference = Column(String(255), nullable=True)
    payment_allocation_id = Column(UUID(as_uuid=True), ForeignKey("payment_allocations.id", ondelete="RESTRICT"), nullable=True)
    expected_amount = Column(Numeric(18, 2), nullable=True)
    observed_amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    provider_amount = Column(Numeric(18, 2), nullable=True)
    funds_amount = Column(Numeric(18, 2), nullable=True)
    fee_amount = Column(Numeric(18, 2), nullable=True)
    refund_amount = Column(Numeric(18, 2), nullable=True)
    hold_amount = Column(Numeric(18, 2), nullable=True)
    release_amount = Column(Numeric(18, 2), nullable=True)
    funds_status = Column(String(30), nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    mismatch_code = Column(String(100), nullable=True)
    conflict_code = Column(String(100), nullable=True)
    source_fingerprint = Column(String(128), nullable=False)
    source_cursor = Column(String(255), nullable=True)
    source_watermark = Column(String(255), nullable=True)
    lease_owner = Column(String(100), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=5)
    dead_lettered_at = Column(DateTime(timezone=True), nullable=True)
    replay_count = Column(Integer, nullable=False, default=0)
    last_error_code = Column(String(100), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(
            ["reconciliation_run_id", "scope_type", "scope_ref"],
            ["reconciliation_runs.id", "reconciliation_runs.scope_type", "reconciliation_runs.scope_ref"],
            name="fk_reconciliation_item_run_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["payment_allocation_id", "tenant_id"],
            ["payment_allocations.id", "payment_allocations.tenant_id"],
            name="fk_reconciliation_item_allocation_owner",
            ondelete="RESTRICT",
            match="SIMPLE",
        ),
        UniqueConstraint("provider", "source_reference", "source_fingerprint", name="uq_reconciliation_item_source_fact"),
        UniqueConstraint("reconciliation_run_id", "canonical_reference", name="uq_reconciliation_item_canonical_reference"),
        UniqueConstraint("id", "reconciliation_run_id", name="uq_reconciliation_item_id_run"),
        CheckConstraint("expected_amount IS NULL OR expected_amount >= 0", name="ck_reconciliation_item_expected_nonnegative"),
        CheckConstraint("observed_amount >= 0", name="ck_reconciliation_item_observed_nonnegative"),
        CheckConstraint("currency = 'COP'", name="ck_reconciliation_item_currency"),
        CheckConstraint("source_type IN ('eslatin', 'provider', 'funds', 'canonical')", name="ck_reconciliation_item_source_type"),
        CheckConstraint("fee_amount IS NULL OR fee_amount >= 0", name="ck_reconciliation_item_fee_nonnegative"),
        CheckConstraint("refund_amount IS NULL OR refund_amount >= 0", name="ck_reconciliation_item_refund_nonnegative"),
        CheckConstraint("hold_amount IS NULL OR hold_amount >= 0", name="ck_reconciliation_item_hold_nonnegative"),
        CheckConstraint("release_amount IS NULL OR release_amount >= 0", name="ck_reconciliation_item_release_nonnegative"),
        CheckConstraint("retry_count >= 0 AND max_retries >= 0 AND replay_count >= 0", name="ck_reconciliation_item_retry_counts"),
        CheckConstraint("status IN ('matched', 'pending', 'mismatch', 'manual_review', 'temporarily_accepted', 'closed', 'unknown')", name="ck_reconciliation_item_status"),
        CheckConstraint(
            "(scope_type = 'platform' AND tenant_id IS NULL AND scope_ref = 'platform:eslatin') OR "
            "(scope_type = 'tenant' AND tenant_id IS NOT NULL AND length(scope_ref) = 43 "
            "AND substr(scope_ref, 1, 7) = 'tenant:' "
            "AND substr(scope_ref, 16, 1) = '-' AND substr(scope_ref, 21, 1) = '-' "
            "AND substr(scope_ref, 26, 1) = '-' AND substr(scope_ref, 31, 1) = '-' "
            "AND replace(substr(scope_ref, 8), '-', '') = replace(CAST(tenant_id AS VARCHAR), '-', ''))",
            name="ck_reconciliation_item_scope",
        ),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_reconciliation_item_versions"),
        Index("idx_reconciliation_item_run_status", "reconciliation_run_id", "status"),
        Index("idx_reconciliation_item_tenant_status", "tenant_id", "status"),
    )


class ReconciliationException(Base):
    __tablename__ = "reconciliation_exceptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reconciliation_run_id = Column(UUID(as_uuid=True), nullable=False)
    reconciliation_item_id = Column(UUID(as_uuid=True), nullable=False)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True)
    status = Column(String(30), nullable=False, default="manual_review")
    reason_code = Column(String(100), nullable=False)
    difference_type = Column(String(50), nullable=True)
    difference_amount = Column(Numeric(18, 2), nullable=True)
    owner_ref = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=False, default="blocking")
    due_at = Column(DateTime(timezone=True), nullable=True)
    escalation = Column(String(100), nullable=True)
    resolution_code = Column(String(100), nullable=True)
    resolution_reason = Column(String(1000), nullable=True)
    request_idempotency_key = Column(String(255), nullable=True)
    decision_idempotency_key = Column(String(255), nullable=True)
    resolution_idempotency_key = Column(String(255), nullable=True)
    initiator_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=True)
    approver_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    temporarily_accepted_until = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(["reconciliation_item_id", "reconciliation_run_id"], ["reconciliation_items.id", "reconciliation_items.reconciliation_run_id"], name="fk_reconciliation_exception_item_run", ondelete="RESTRICT"),
        ForeignKeyConstraint(["reconciliation_run_id", "scope_type", "scope_ref"], ["reconciliation_runs.id", "reconciliation_runs.scope_type", "reconciliation_runs.scope_ref"], name="fk_reconciliation_exception_run_scope", ondelete="RESTRICT"),
        UniqueConstraint("reconciliation_item_id", name="uq_reconciliation_exception_item"),
        CheckConstraint("status IN ('matched', 'pending', 'mismatch', 'manual_review', 'temporarily_accepted', 'closed', 'unknown')", name="ck_reconciliation_exception_status"),
        CheckConstraint("severity IN ('blocking', 'warning')", name="ck_reconciliation_exception_severity"),
        CheckConstraint("difference_amount IS NULL OR difference_amount >= 0", name="ck_reconciliation_exception_difference_nonnegative"),
        CheckConstraint(
            "(scope_type = 'platform' AND tenant_id IS NULL AND scope_ref = 'platform:eslatin') OR "
            "(scope_type = 'tenant' AND tenant_id IS NOT NULL AND length(scope_ref) = 43 "
            "AND substr(scope_ref, 1, 7) = 'tenant:' "
            "AND substr(scope_ref, 16, 1) = '-' AND substr(scope_ref, 21, 1) = '-' "
            "AND substr(scope_ref, 26, 1) = '-' AND substr(scope_ref, 31, 1) = '-' "
            "AND replace(substr(scope_ref, 8), '-', '') = replace(CAST(tenant_id AS VARCHAR), '-', ''))",
            name="ck_reconciliation_exception_scope",
        ),
        CheckConstraint("approver_admin_id IS NULL OR initiator_admin_id IS NULL OR approver_admin_id <> initiator_admin_id", name="ck_reconciliation_exception_distinct_actors"),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_reconciliation_exception_versions"),
        Index("idx_reconciliation_exception_status_expiry", "status", "temporarily_accepted_until"),
    )


class ReconciliationSourceFact(Base):
    """Bounded canonical fact received from EsLatin, a Provider, or funds."""

    __tablename__ = "reconciliation_source_facts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True, index=True)
    provider = Column(String(50), nullable=False)
    provider_account_ref = Column(String(100), nullable=False)
    source_type = Column(String(20), nullable=False)
    source_reference = Column(String(255), nullable=False)
    canonical_reference = Column(String(255), nullable=False)
    merchant_reference = Column(String(255), nullable=True)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="COP")
    fee_amount = Column(Numeric(18, 2), nullable=False, default=0)
    refund_amount = Column(Numeric(18, 2), nullable=False, default=0)
    hold_amount = Column(Numeric(18, 2), nullable=False, default=0)
    release_amount = Column(Numeric(18, 2), nullable=False, default=0)
    funds_status = Column(String(30), nullable=True)
    source_event_id = Column(String(255), nullable=True)
    source_cursor = Column(String(255), nullable=True)
    source_watermark = Column(String(255), nullable=True)
    source_fingerprint = Column(String(128), nullable=False)
    dedupe_key = Column(String(255), nullable=False)
    conflict_code = Column(String(100), nullable=True)
    status = Column(String(30), nullable=False, default="accepted")
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        UniqueConstraint("provider", "source_type", "source_reference", "source_fingerprint", name="uq_recon_source_fact_fingerprint"),
        UniqueConstraint("provider", "source_type", "dedupe_key", name="uq_recon_source_fact_dedupe"),
        CheckConstraint("source_type IN ('eslatin', 'provider', 'funds')", name="ck_recon_source_fact_type"),
        CheckConstraint("currency = 'COP'", name="ck_recon_source_fact_currency"),
        CheckConstraint("amount >= 0 AND fee_amount >= 0 AND refund_amount >= 0 AND hold_amount >= 0 AND release_amount >= 0", name="ck_recon_source_fact_amounts"),
        CheckConstraint("status IN ('accepted', 'duplicate', 'conflict', 'dead_letter', 'unknown')", name="ck_recon_source_fact_status"),
        Index("idx_recon_source_fact_match", "scope_type", "scope_ref", "canonical_reference", "source_type"),
        Index("idx_recon_source_fact_watermark", "source_type", "source_cursor", "created_at"),
    )


class ReconciliationSourceWatermark(Base):
    """Per-scope/source checkpoint; never represents a financial outcome."""

    __tablename__ = "reconciliation_source_watermarks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True)
    provider = Column(String(50), nullable=False)
    source_type = Column(String(20), nullable=False)
    watermark = Column(String(255), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    lease_owner = Column(String(100), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    dead_lettered_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("scope_type", "scope_ref", "provider", "source_type", name="uq_recon_source_watermark"),
        CheckConstraint("source_type IN ('eslatin', 'provider', 'funds')", name="ck_recon_source_watermark_type"),
        CheckConstraint("version >= 1 AND retry_count >= 0", name="ck_recon_source_watermark_versions"),
        Index("idx_recon_source_watermark_lease", "lease_expires_at", "source_type"),
    )


class ReconciliationWorkItem(Base):
    """Bounded reconciliation work with lease, retry and dead-letter state."""

    __tablename__ = "reconciliation_work_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True)
    source_fact_id = Column(UUID(as_uuid=True), ForeignKey("reconciliation_source_facts.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String(30), nullable=False, default="queued")
    lease_owner = Column(String(100), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=5)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    last_error_code = Column(String(100), nullable=True)
    dead_lettered_at = Column(DateTime(timezone=True), nullable=True)
    replay_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("source_fact_id", name="uq_recon_work_source_fact"),
        CheckConstraint("status IN ('queued', 'leased', 'completed', 'retryable', 'dead_letter')", name="ck_recon_work_status"),
        CheckConstraint("retry_count >= 0 AND max_retries >= 0 AND replay_count >= 0", name="ck_recon_work_counts"),
        Index("idx_recon_work_claim", "status", "next_attempt_at", "lease_expires_at"),
    )


class ReconciliationExport(Base):
    """Bounded, one-time Admin CSV export resource."""

    __tablename__ = "reconciliation_exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reconciliation_run_id = Column(UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="RESTRICT"), nullable=False)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True)
    status = Column(String(20), nullable=False, default="queued")
    format = Column(String(10), nullable=False, default="csv")
    filters = Column(PortableJSON, nullable=False, default=dict)
    content = Column(Text, nullable=True)
    row_count = Column(Integer, nullable=False, default=0)
    max_rows = Column(Integer, nullable=False, default=10000)
    download_path = Column(String(255), nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    audit_reference = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("scope_type", "scope_ref", "idempotency_key", name="uq_recon_export_scope_idempotency"),
        CheckConstraint("format = 'csv'", name="ck_recon_export_format"),
        CheckConstraint("status IN ('queued', 'generating', 'ready', 'downloaded', 'failed', 'expired')", name="ck_recon_export_status"),
        CheckConstraint("row_count >= 0 AND max_rows > 0 AND row_count <= max_rows", name="ck_recon_export_rows"),
        CheckConstraint("version >= 1", name="ck_recon_export_version"),
        Index("idx_recon_export_scope_status", "scope_type", "scope_ref", "status", "created_at"),
    )


class RuntimeRailControl(Base):
    """Dual-axis runtime availability control. This is not a risk threshold."""
    __tablename__ = "runtime_rail_controls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    axis = Column(String(30), nullable=False)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True)
    site_id = Column(UUID(as_uuid=True), nullable=True)
    provider = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="open")
    reason = Column(Text, nullable=True)
    reason_code = Column(String(100), nullable=True)
    incident_reference = Column(String(255), nullable=True)
    closed_by_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=True)
    reopened_by_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=True)
    health_check_reference = Column(String(255), nullable=True)
    health_check_status = Column(String(20), nullable=True)
    effective_at = Column(DateTime(timezone=True), nullable=True)
    close_idempotency_key = Column(String(255), nullable=True)
    close_request_fingerprint = Column(String(64), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    reopened_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(
            ["site_id", "tenant_id"],
            ["sites.id", "sites.tenant_id"],
            name="fk_runtime_rail_site_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_runtime_rail_control_id_tenant"),
        UniqueConstraint("axis", "scope_type", "scope_ref", name="uq_runtime_rail_axis_scope"),
        CheckConstraint("axis IN ('paid_admission', 'payment_creation')", name="ck_runtime_rail_axis"),
        CheckConstraint("status IN ('open', 'closed', 'unknown')", name="ck_runtime_rail_status"),
        CheckConstraint(
            "(scope_type = 'platform' AND scope_ref = 'platform:eslatin' AND tenant_id IS NULL AND site_id IS NULL AND provider IS NULL) OR "
            "(scope_type = 'provider' AND scope_ref = 'provider:' || provider AND tenant_id IS NULL AND site_id IS NULL AND provider IS NOT NULL) OR "
            "(scope_type = 'tenant' AND length(scope_ref) = 43 AND substr(scope_ref, 1, 7) = 'tenant:' "
            "AND replace(substr(scope_ref, 8), '-', '') = replace(CAST(tenant_id AS VARCHAR), '-', '') "
            "AND tenant_id IS NOT NULL AND site_id IS NULL AND provider IS NULL) OR "
            "(scope_type = 'site' AND length(scope_ref) = 41 AND substr(scope_ref, 1, 5) = 'site:' "
            "AND replace(substr(scope_ref, 6), '-', '') = replace(CAST(site_id AS VARCHAR), '-', '') "
            "AND tenant_id IS NOT NULL AND site_id IS NOT NULL AND provider IS NULL)",
            name="ck_runtime_rail_scope",
        ),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_runtime_rail_versions"),
        Index("idx_runtime_rail_status_axis", "status", "axis", "scope_type"),
    )


class RailHealthCheck(Base):
    """Provider-neutral, server-recorded health evidence for rail recovery."""
    __tablename__ = "rail_health_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference = Column(String(255), nullable=False, unique=True)
    axis = Column(String(30), nullable=False)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)
    checked_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    safe_metadata = Column(PortableJSON, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint("axis IN ('paid_admission', 'payment_creation')", name="ck_rail_health_axis"),
        CheckConstraint("scope_type IN ('platform', 'provider', 'tenant', 'site')", name="ck_rail_health_scope_type"),
        CheckConstraint("status IN ('passed', 'failed', 'unknown')", name="ck_rail_health_status"),
        Index("idx_rail_health_scope_status", "scope_type", "scope_ref", "status", "checked_at"),
    )


class RailReopenRequest(Base):
    """Two-person reopen intent; the control remains closed until approval."""
    __tablename__ = "rail_reopen_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    control_id = Column(UUID(as_uuid=True), ForeignKey("runtime_rail_controls.id", ondelete="RESTRICT"), nullable=False)
    axis = Column(String(30), nullable=False)
    scope_type = Column(String(20), nullable=False)
    scope_ref = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="requested")
    reason = Column(Text, nullable=False)
    initiator_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False)
    approver_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=True)
    health_check_reference = Column(String(255), nullable=False)
    health_check_status = Column(String(20), nullable=False, default="unknown")
    control_status = Column(String(20), nullable=False, default="closed")
    expected_control_version = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    idempotency_key = Column(String(255), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    audit_reference = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_idempotency_key = Column(String(255), nullable=True)
    decision_fingerprint = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("control_id", "idempotency_key", name="uq_rail_reopen_control_idempotency"),
        CheckConstraint("axis IN ('paid_admission', 'payment_creation')", name="ck_rail_reopen_axis"),
        CheckConstraint("scope_type IN ('platform', 'provider', 'tenant', 'site')", name="ck_rail_reopen_scope_type"),
        CheckConstraint("status IN ('requested', 'approved', 'rejected', 'expired')", name="ck_rail_reopen_status"),
        CheckConstraint("health_check_status IN ('passed', 'failed', 'unknown')", name="ck_rail_reopen_health_status"),
        CheckConstraint("control_status IN ('open', 'closed', 'unknown')", name="ck_rail_reopen_control_status"),
        CheckConstraint("version >= 1 AND schema_version >= 1 AND expected_control_version >= 1", name="ck_rail_reopen_versions"),
        Index("idx_rail_reopen_status_scope", "status", "scope_type", "scope_ref", "created_at"),
    )


class SupportCase(Base):
    __tablename__ = "support_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_reference = Column(String(100), nullable=False, unique=True, default=lambda: _business_number("support"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("charging_sessions.id", ondelete="RESTRICT"), nullable=True)
    payment_order_id = Column(UUID(as_uuid=True), ForeignKey("payment_orders.id", ondelete="RESTRICT"), nullable=True)
    refund_case_id = Column(UUID(as_uuid=True), ForeignKey("refund_cases.id", ondelete="RESTRICT"), nullable=True)
    chargeback_case_id = Column(UUID(as_uuid=True), ForeignKey("chargeback_cases.id", ondelete="RESTRICT"), nullable=True)
    rail_control_id = Column(UUID(as_uuid=True), ForeignKey("runtime_rail_controls.id", ondelete="RESTRICT"), nullable=True)
    category = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="open")
    priority = Column(String(20), nullable=False, default="normal")
    assigned_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    first_response_target_at = Column(DateTime(timezone=True), nullable=True)
    decision_target_at = Column(DateTime(timezone=True), nullable=True)
    first_responded_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(
            ["invoice_id", "tenant_id"],
            ["invoices.id", "invoices.tenant_id"],
            name="fk_support_case_invoice_owner",
            ondelete="RESTRICT",
            match="SIMPLE",
        ),
        ForeignKeyConstraint(
            ["session_id", "tenant_id"],
            ["charging_sessions.id", "charging_sessions.tenant_id"],
            name="fk_support_case_session_owner",
            ondelete="RESTRICT",
            match="SIMPLE",
        ),
        ForeignKeyConstraint(
            ["refund_case_id", "tenant_id"],
            ["refund_cases.id", "refund_cases.tenant_id"],
            name="fk_support_case_refund_owner",
            ondelete="RESTRICT",
            match="SIMPLE",
        ),
        ForeignKeyConstraint(
            ["chargeback_case_id", "tenant_id"],
            ["chargeback_cases.id", "chargeback_cases.tenant_id"],
            name="fk_support_case_chargeback_owner",
            ondelete="RESTRICT",
            match="SIMPLE",
        ),
        ForeignKeyConstraint(
            ["rail_control_id", "tenant_id"],
            ["runtime_rail_controls.id", "runtime_rail_controls.tenant_id"],
            name="fk_support_case_rail_owner",
            ondelete="RESTRICT",
            match="SIMPLE",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_support_case_id_tenant"),
        CheckConstraint("category IN ('unpaid', 'payment_failed', 'duplicate_charge', 'refund_delayed', 'chargeback', 'cannot_stop', 'amount_mismatch', 'other')", name="ck_support_case_category"),
        CheckConstraint("status IN ('open', 'acknowledged', 'in_progress', 'waiting_user', 'resolved', 'closed', 'unknown')", name="ck_support_case_status"),
        CheckConstraint("priority IN ('normal', 'urgent')", name="ck_support_case_priority"),
        CheckConstraint("version >= 1 AND schema_version >= 1", name="ck_support_case_versions"),
        Index("idx_support_case_tenant_status", "tenant_id", "status", "updated_at"),
        Index("idx_support_case_user_created", "app_user_id", "created_at"),
    )


class SupportCaseEvent(Base):
    """Append-only support timeline fact."""
    __tablename__ = "support_case_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    support_case_id = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=True)
    actor_type = Column(String(20), nullable=False)
    actor_ref = Column(String(100), nullable=False)
    visibility = Column(String(20), nullable=False)
    reason_code = Column(String(100), nullable=True)
    note = Column(Text, nullable=True)
    schema_version = Column(Integer, nullable=False, default=1)
    audit_reference = Column(String(255), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        ForeignKeyConstraint(["support_case_id", "tenant_id"], ["support_cases.id", "support_cases.tenant_id"], name="fk_support_case_event_owner", ondelete="RESTRICT"),
        CheckConstraint("actor_type IN ('app_user', 'admin', 'system')", name="ck_support_case_event_actor"),
        CheckConstraint("visibility IN ('internal', 'user')", name="ck_support_case_event_visibility"),
        CheckConstraint("schema_version >= 1", name="ck_support_case_event_schema_version"),
        Index("idx_support_case_event_case_time", "support_case_id", "occurred_at"),
    )


# ==================== 事件和日志层 ====================

class DeviceEvent(Base):
    """设备事件表（统一事件流）
    合并原来的heartbeat_history、status_history、ocpp_error_logs
    """
    __tablename__ = "device_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True, index=True)
    device_serial_number = Column(String(100), nullable=True, index=True)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id"), nullable=True, index=True)
    evse_id = Column(UUID(as_uuid=True), ForeignKey("evses.id"), nullable=True, index=True)
    
    # 事件信息
    event_type = Column(String(50), nullable=False, index=True)  # heartbeat, status_change, error, boot, disconnect, etc.
    event_data = Column(PortableJSON, nullable=True)  # 事件数据（JSON格式）
    
    # 状态相关（如果是status_change事件）
    status = Column(String(50), nullable=True)  # 新状态
    previous_status = Column(String(50), nullable=True)  # 之前的状态
    
    # 错误相关（如果是error事件）
    error_code = Column(String(100), nullable=True)
    error_description = Column(Text, nullable=True)
    
    # 协议消息相关（如果是protocol事件）
    protocol_action = Column(String(100), nullable=True)  # OCPP action
    message_direction = Column(String(20), nullable=True)  # incoming, outgoing
    request_payload = Column(PortableJSON, nullable=True)
    response_payload = Column(PortableJSON, nullable=True)
    
    # 时间戳
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    # 关系
    tenant = relationship("Tenant")
    device = relationship("Device")
    charge_point = relationship("ChargePoint")
    evse = relationship("EVSE")
    
    __table_args__ = (
        Index('idx_device_events_type', 'event_type'),
        Index('idx_device_events_timestamp', 'timestamp'),
        Index('idx_device_events_device_timestamp', 'device_serial_number', 'timestamp'),
        Index('idx_device_events_charge_point_timestamp', 'charge_point_id', 'timestamp'),
        Index('idx_device_events_tenant_id', 'tenant_id'),
    )


# ==================== 配置层 ====================

class DeviceConfig(Base):
    """设备配置表（通信相关）
    存储MQTT、OCPP、心跳等通信配置
    """
    __tablename__ = "device_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False, index=True)
    device_serial_number = Column(String(100), nullable=False, index=True)
    
    config_key = Column(String(100), nullable=False)  # 配置键
    config_value = Column(Text, nullable=True)  # 配置值
    value_type = Column(String(20), default="string")  # string, int, bool, json
    
    # 版本控制
    version = Column(Integer, default=1)
    updated_by = Column(String(100), nullable=True)  # 更新人
    
    # 元数据
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    tenant = relationship("Tenant")
    device = relationship("Device")
    
    __table_args__ = (
        Index('idx_device_configs_device_key', 'device_id', 'config_key', unique=True),
        Index('idx_device_configs_tenant_id', 'tenant_id'),
    )


class ChargePointConfig(Base):
    """充电桩配置表（资产相关）
    存储限功率、开放时间、告警阈值等资产配置
    """
    __tablename__ = "charge_point_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id"), nullable=False, index=True)
    
    config_key = Column(String(100), nullable=False)  # 配置键
    config_value = Column(Text, nullable=True)  # 配置值
    value_type = Column(String(20), default="string")  # string, int, bool, json
    
    # 版本控制
    version = Column(Integer, default=1)
    updated_by = Column(String(100), nullable=True)  # 更新人
    
    # 元数据
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    tenant = relationship("Tenant")
    charge_point = relationship("ChargePoint")
    
    __table_args__ = (
        Index('idx_charge_point_configs_cp_key', 'charge_point_id', 'config_key', unique=True),
        Index('idx_charge_point_configs_tenant_id', 'tenant_id'),
    )


# ==================== 业务支持表 ====================

class SupportMessage(Base):
    """客服消息表
    保持不变
    """
    __tablename__ = "support_messages"

    def __init__(self, **kwargs):
        _map_legacy_business_id(kwargs, "message_number")
        super().__init__(**kwargs)
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    message_number = Column(String(100), nullable=False, unique=True, index=True, default=lambda: _business_number("message"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(100), nullable=True, index=True)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True, index=True)
    username = Column(String(100), nullable=False)
    
    message = Column(Text, nullable=False)
    reply = Column(Text, nullable=True)
    
    status = Column(String(50), default="pending")  # pending, replied
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    replied_at = Column(DateTime(timezone=True), nullable=True)
    
    tenant = relationship("Tenant")
    
    __table_args__ = (
        Index('idx_messages_status', 'status'),
        Index('idx_messages_user_id', 'user_id'),
        Index('idx_messages_created_at', 'created_at'),
        Index('idx_support_messages_tenant_id', 'tenant_id'),
    )


# ==================== 多租户核心表 ====================

class Tenant(Base):
    """租户表"""
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(200), nullable=False)
    domain = Column(String(200), unique=True, nullable=True)
    status = Column(String(50), nullable=False, default="active")  # active, suspended, deleted
    subscription_plan = Column(String(50), nullable=False, default="free")  # free, basic, premium, enterprise
    max_charge_points = Column(Integer, default=10)
    max_users = Column(Integer, default=100)
    settings = Column(PortableJSON, default=dict)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index('idx_tenants_domain', 'domain'),
        Index('idx_tenants_status', 'status'),
        CheckConstraint(
            "subscription_plan IN ('free', 'pro', 'enterprise')",
            name="ck_tenants_subscription_plan",
        ),
    )


class AdminUser(Base):
    """管理员用户表"""
    __tablename__ = "admin_users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    email = Column(String(200), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_super_admin = Column(Boolean, nullable=False, default=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    memberships = relationship("TenantMembership", back_populates="admin_user", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_admin_users_email', 'email'),
        Index('idx_admin_users_username', 'username'),
    )


class AppUser(Base):
    """平台级终端用户（爆改测试版）

    目标：
    - App 用户不再绑定单一 tenant，可跨多个运营商(tenant)充电。
    - 钱包余额为平台统一钱包（见 AppWalletTransaction）。

    说明：
    - AppUser 是唯一的 App 用户模型，不绑定单一运营商租户。
    """
    __tablename__ = "app_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    email = Column(String(200), nullable=False, unique=True, index=True)
    phone = Column(String(50), nullable=True, unique=True, index=True)
    full_name = Column(String(200), nullable=True)

    password_hash = Column(String(255), nullable=False)
    email_verified = Column(Boolean, default=False)
    email_verification_code_hash = Column(String(64), nullable=True)
    email_verification_token_hash = Column(String(64), nullable=True)
    email_verification_expires_at = Column(DateTime(timezone=True), nullable=True)
    email_verification_sent_at = Column(DateTime(timezone=True), nullable=True)
    password_reset_token_hash = Column(String(64), nullable=True, index=True)
    password_reset_expires_at = Column(DateTime(timezone=True), nullable=True)
    password_reset_requested_at = Column(DateTime(timezone=True), nullable=True)

    balance = Column(Numeric(10, 2), nullable=False, default=0)
    has_unpaid_charges = Column(Boolean, default=False, nullable=False)
    status = Column(String(50), nullable=False, default="active")  # active, suspended, deleted
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_app_users_email", "email"),
        Index("idx_app_users_phone", "phone"),
    )


class AppUserFavoriteSite(Base):
    """Platform App user's saved public charging site."""

    __tablename__ = "app_user_favorite_sites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    app_user = relationship("AppUser")
    site = relationship("Site")

    __table_args__ = (
        UniqueConstraint(
            "app_user_id",
            "site_id",
            name="uq_app_user_favorite_site",
        ),
        Index("idx_app_user_favorite_sites_user_created", "app_user_id", "created_at"),
    )


class AppUserPaymentMethod(Base):
    """终端用户保存的支付方式（Mercado Pago Customers/Cards 等回填；当前可为空表）"""

    __tablename__ = "app_user_payment_methods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True)

    provider = Column(String(32), nullable=False)  # mercadopago | wompi | ...
    mp_customer_id = Column(String(128), nullable=True)
    mp_card_id = Column(String(128), nullable=True)
    payment_method_brand = Column(String(64), nullable=True)
    last_four = Column(String(4), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_app_user_payment_methods_user", "app_user_id"),
    )


class TenantMembership(Base):
    """租户成员关系表"""
    __tablename__ = "tenant_memberships"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    admin_user_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True)
    is_primary = Column(Boolean, nullable=False, default=False)  # 是否为主租户（默认租户）
    status = Column(String(50), nullable=False, default="active")  # active, suspended
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    tenant = relationship("Tenant")
    admin_user = relationship("AdminUser", back_populates="memberships")
    roles = relationship("TenantMembershipRole", back_populates="membership", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'admin_user_id', name='unique_tenant_admin_user'),
        Index('idx_tenant_memberships_tenant_id', 'tenant_id'),
        Index('idx_tenant_memberships_admin_user_id', 'admin_user_id'),
        Index('idx_tenant_memberships_primary', 'admin_user_id', 'is_primary'),
    )


class Role(Base):
    """角色表"""
    __tablename__ = "roles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)  # NULL表示系统角色
    name = Column(String(100), nullable=False)
    permissions = Column(PortableJSON, nullable=False, default=list)  # 权限列表
    description = Column(Text, nullable=True)
    scope = Column(String(50), nullable=False, default="tenant")  # system / tenant
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    tenant = relationship("Tenant")
    membership_roles = relationship("TenantMembershipRole", back_populates="role")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='unique_tenant_role_name'),
        Index('idx_roles_tenant_id', 'tenant_id'),
        Index('idx_roles_scope', 'scope'),
    )


class TenantMembershipRole(Base):
    """成员角色关系表"""
    __tablename__ = "tenant_membership_roles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    membership_id = Column(UUID(as_uuid=True), ForeignKey("tenant_memberships.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    membership = relationship("TenantMembership", back_populates="roles")
    role = relationship("Role", back_populates="membership_roles")
    
    __table_args__ = (
        UniqueConstraint('membership_id', 'role_id', name='uq_tenant_membership_role'),
        Index('idx_tenant_membership_roles_membership_id', 'membership_id'),
        Index('idx_tenant_membership_roles_role_id', 'role_id'),
    )


# ==================== 告警监控表 ====================

class Alert(Base):
    """告警表"""
    __tablename__ = "alerts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    charge_point_id = Column(UUID(as_uuid=True), ForeignKey("charge_points.id", ondelete="SET NULL"), nullable=True, index=True)
    evse_id = Column(UUID(as_uuid=True), ForeignKey("evses.id", ondelete="SET NULL"), nullable=True, index=True)
    alert_type = Column(String(50), nullable=False)  # offline, faulted, overcurrent, overvoltage, temperature, etc.
    # Stable key for tenant-scoped automatic alert deduplication. Manual alerts
    # leave it NULL, so their existing behavior is unchanged.
    dedupe_key = Column(String(255), nullable=True)
    severity = Column(String(50), nullable=False)  # critical, warning, info
    status = Column(String(50), nullable=False, default="pending")  # pending, acknowledged, resolved
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    alert_metadata = Column(PortableJSON, default=dict)  # 使用 alert_metadata 避免与 SQLAlchemy 保留字冲突
    acknowledged_by = Column(UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    tenant = relationship("Tenant")
    charge_point = relationship("ChargePoint")
    evse = relationship("EVSE")
    acknowledged_by_user = relationship("AdminUser", foreign_keys=[acknowledged_by])
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'dedupe_key', name='uq_alerts_tenant_dedupe_key'),
        Index('idx_alerts_tenant_id', 'tenant_id'),
        Index('idx_alerts_charge_point_id', 'charge_point_id'),
        Index('idx_alerts_status', 'status'),
        Index('idx_alerts_severity', 'severity'),
        Index('idx_alerts_created_at', 'created_at'),
    )


class AlertRule(Base):
    """告警规则表"""
    __tablename__ = "alert_rules"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    alert_type = Column(String(50), nullable=False)
    conditions = Column(PortableJSON, nullable=False)  # 条件配置
    severity = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    tenant = relationship("Tenant")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='unique_tenant_alert_rule_name'),
        Index('idx_alert_rules_tenant_id', 'tenant_id'),
        Index('idx_alert_rules_is_enabled', 'is_enabled'),
    )


# ==================== 系统配置表 ====================

class SystemConfig(Base):
    """系统配置表"""
    __tablename__ = "system_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)  # NULL表示全局配置
    config_key = Column(String(200), nullable=False)
    config_value = Column(Text, nullable=True)
    value_type = Column(String(20), nullable=False, default="string")  # string, int, bool, json
    description = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    tenant = relationship("Tenant")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'config_key', name='unique_tenant_config_key'),
        Index('idx_system_configs_tenant_id_key', 'tenant_id', 'config_key'),
    )


# ==================== Token 管理表 ====================

class RefreshToken(Base):
    """刷新Token表"""
    __tablename__ = "refresh_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    jti = Column(String(100), nullable=False, unique=True, index=True)  # JWT ID
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # admin_user_id 或 app_user_id
    user_type = Column(String(20), nullable=False)  # admin / app_user
    token_hash = Column(String(255), nullable=False)  # refresh token的哈希值
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    device_info = Column(PortableJSON, nullable=True)  # 设备信息
    ip_address = Column(String(50), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index('idx_refresh_tokens_jti', 'jti'),
        Index('idx_refresh_tokens_user_id', 'user_id', 'user_type'),
        Index('idx_refresh_tokens_expires_at', 'expires_at'),
    )


# ==================== 审计日志表 ====================

class AuditLog(Base):
    """审计日志表"""
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # admin_user_id 或 app_user_id
    actor_type = Column(String(20), nullable=False)  # admin / app_user / system
    action = Column(String(100), nullable=False, index=True)  # create, update, delete, login, etc.
    resource_type = Column(String(100), nullable=True, index=True)  # charge_point, order, user, etc.
    resource_id = Column(String(100), nullable=True, index=True)  # 资源ID
    before_data = Column(PortableJSON, nullable=True)  # 变更前数据
    after_data = Column(PortableJSON, nullable=True)  # 变更后数据
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    audit_metadata = Column("metadata", PortableJSON, default=dict)  # 映射到数据库的metadata字段

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    tenant = relationship("Tenant")
    
    __table_args__ = (
        Index('idx_audit_logs_tenant_id', 'tenant_id'),
        Index('idx_audit_logs_actor', 'actor_id', 'actor_type'),
        Index('idx_audit_logs_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_logs_action', 'action'),
        Index('idx_audit_logs_created_at', 'created_at'),
    )
