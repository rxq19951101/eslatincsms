"""
二维码生成服务
用于在创建充电桩时自动生成二维码（每个connector一个）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import qrcode
from qrcode.image.pil import PilImage

from app.core.logging_config import get_logger

logger = get_logger(__name__)


def build_qr_payload(charge_point_id: str, connector_id: int, payload_format: str = "hash") -> str:
    """
    构建二维码内容
    
    Args:
        charge_point_id: 充电桩ID
        connector_id: 连接器ID
        payload_format: 格式（hash|query|json），默认hash格式与移动端兼容
    
    Returns:
        二维码内容字符串
    """
    if payload_format == "hash":
        return f"{charge_point_id}#{connector_id}"
    if payload_format == "query":
        return f"{charge_point_id}?connector={connector_id}"
    if payload_format == "json":
        return f'{{"chargePointId":"{charge_point_id}","connectorId":{connector_id}}}'
    raise ValueError(f"Unsupported payload_format={payload_format}")


def generate_qr_code(
    charge_point_id: str,
    connector_id: int,
    output_dir: Path,
    payload_format: str = "hash"
) -> Path:
    """
    生成二维码PNG文件
    
    Args:
        charge_point_id: 充电桩ID
        connector_id: 连接器ID
        output_dir: 输出目录
        payload_format: 二维码内容格式（默认hash）
    
    Returns:
        生成的二维码文件路径
    """
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 构建二维码内容
    payload = build_qr_payload(charge_point_id, connector_id, payload_format)
    
    # 生成二维码图片
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    
    img: PilImage = qr.make_image(fill_color="black", back_color="white")
    
    # 保存文件
    filename = f"{charge_point_id}_connector_{connector_id}.png"
    file_path = output_dir / filename
    img.save(str(file_path))
    
    logger.info(f"二维码已生成: {file_path} (内容: {payload})")
    return file_path


def get_qr_code_path(charge_point_id: str, connector_id: int, base_dir: Path) -> Path:
    """
    获取二维码文件路径（不生成，仅返回路径）
    
    Args:
        charge_point_id: 充电桩ID
        connector_id: 连接器ID
        base_dir: 二维码存储基础目录
    
    Returns:
        二维码文件路径
    """
    filename = f"{charge_point_id}_connector_{connector_id}.png"
    return base_dir / filename


def get_qr_code_url(charge_point_id: str, connector_id: int, base_url: str = "/static/qr") -> str:
    """
    获取二维码访问URL
    
    Args:
        charge_point_id: 充电桩ID
        connector_id: 连接器ID
        base_url: 静态文件基础URL
    
    Returns:
        二维码访问URL
    """
    filename = f"{charge_point_id}_connector_{connector_id}.png"
    return f"{base_url}/{filename}"


def get_qr_storage_dir() -> Path:
    """
    获取二维码存储目录
    
    Returns:
        二维码存储目录路径
    """
    # 默认存储在项目根目录的 static/qr/ 目录
    # 如果设置了环境变量 QR_STORAGE_DIR，则使用该目录
    qr_dir = os.getenv("QR_STORAGE_DIR")
    if qr_dir:
        return Path(qr_dir)
    
    # 获取项目根目录（csms目录）
    current_file = Path(__file__)
    csms_dir = current_file.parent.parent.parent  # csms/app/services/qr_service.py -> csms/
    return csms_dir / "static" / "qr"
