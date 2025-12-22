#
# ID生成工具
# 为各种实体生成唯一ID
#

import uuid
from datetime import datetime, timezone
from typing import Optional


def generate_uuid() -> str:
    """生成UUID字符串（去掉连字符）"""
    return uuid.uuid4().hex


def generate_short_uuid() -> str:
    """生成短UUID（前16位）"""
    return uuid.uuid4().hex[:16]


def generate_timestamp_id(prefix: str = "") -> str:
    """生成基于时间戳的ID（格式：prefix_YYYYMMDDHHMMSS_microseconds）"""
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d%H%M%S")
    microseconds = now.microsecond
    if prefix:
        return f"{prefix}_{timestamp}_{microseconds:06d}"
    return f"{timestamp}_{microseconds:06d}"


def generate_site_id(name: Optional[str] = None) -> str:
    """生成站点ID（格式：site_<short_uuid>）"""
    if name:
        # 如果提供了名称，使用名称的简化版本
        name_part = "".join(c for c in name.lower() if c.isalnum())[:10]
        return f"site_{name_part}_{generate_short_uuid()}"
    return f"site_{generate_short_uuid()}"


def generate_charge_point_id(serial_number: Optional[str] = None, vendor: Optional[str] = None) -> str:
    """生成充电桩ID（格式：cp_<serial_number>_<short_uuid> 或 cp_<short_uuid>）
    
    注意：即使提供了序列号，也会添加UUID后缀以确保唯一性，避免序列号冲突
    """
    short_uuid = generate_short_uuid()
    if serial_number:
        # 如果提供了序列号，使用序列号+UUID后缀确保唯一性
        # 限制序列号长度，避免ID过长
        serial_part = serial_number[:20] if len(serial_number) > 20 else serial_number
        return f"cp_{serial_part}_{short_uuid}"
    if vendor:
        # 如果提供了厂商，使用厂商前缀+UUID
        vendor_part = "".join(c for c in vendor.lower() if c.isalnum())[:5]
        return f"cp_{vendor_part}_{short_uuid}"
    return f"cp_{short_uuid}"


def generate_order_id(charge_point_id: Optional[str] = None, transaction_id: Optional[int] = None) -> str:
    """生成订单ID（格式：order_<charge_point_id>_<transaction_id> 或 order_<timestamp>）"""
    if charge_point_id and transaction_id:
        # 使用充电桩ID和交易ID
        cp_part = charge_point_id.replace("cp_", "")[:10]
        return f"order_{cp_part}_{transaction_id}"
    # 使用时间戳
    return f"order_{generate_timestamp_id()}"


def generate_invoice_id(order_id: Optional[str] = None) -> str:
    """生成发票ID（格式：inv_<order_id> 或 inv_<timestamp>）"""
    if order_id:
        return f"inv_{order_id.replace('order_', '')}"
    return f"inv_{generate_timestamp_id()}"


def generate_payment_id(invoice_id: Optional[str] = None) -> str:
    """生成支付ID（格式：pay_<invoice_id> 或 pay_<timestamp>）"""
    if invoice_id:
        return f"pay_{invoice_id.replace('inv_', '')}"
    return f"pay_{generate_timestamp_id()}"
