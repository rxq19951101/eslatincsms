"""
二维码生成服务
用于在创建充电桩时自动生成二维码（每个connector一个）
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional

import qrcode
from qrcode.image.pil import PilImage
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.models import ChargePoint, QrToken

logger = get_logger(__name__)


def build_qr_payload(token: str) -> str:
    """构建二维码内容（爆改测试版：token-only）

    二维码只包含不可猜测 token，App 扫码后把 token 发回后端解析得到：
    - operator_tenant_id
    - charge_point_id
    - connector_id
    """
    return f"qr:{token}"


def ensure_qr_token(db: Session, charge_point_id: str, connector_id: int) -> QrToken:
    """为指定桩/枪口确保存在一个可用 token（幂等）"""
    cp = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
    if not cp:
        raise ValueError(f"ChargePoint not found: {charge_point_id}")

    existing = (
        db.query(QrToken)
        .filter(
            QrToken.charge_point_id == charge_point_id,
            QrToken.connector_id == connector_id,
            QrToken.revoked_at.is_(None),
        )
        .first()
    )
    if existing:
        return existing

    # token 可能极小概率碰撞，冲突则重试
    for _ in range(5):
        token = secrets.token_urlsafe(32)  # 通常 ~43 chars
        rec = QrToken(
            token=token,
            operator_tenant_id=cp.tenant_id,
            charge_point_id=charge_point_id,
            connector_id=connector_id,
        )
        try:
            db.add(rec)
            db.commit()
            db.refresh(rec)
            return rec
        except IntegrityError:
            db.rollback()
            continue

    raise RuntimeError("Failed to allocate unique qr token after retries")


def resolve_qr_token(db: Session, token: str) -> QrToken:
    """解析 token -> QrToken 记录（爆改测试版）"""
    rec = db.query(QrToken).filter(QrToken.token == token, QrToken.revoked_at.is_(None)).first()
    if not rec:
        raise ValueError("Invalid or revoked qr token")
    return rec


def generate_qr_code(
    db: Session,
    charge_point_id: str,
    connector_id: int,
    output_dir: Path,
) -> Path:
    """
    生成二维码PNG文件
    
    Args:
        db: 数据库会话（用于写入/读取 qr_tokens）
        charge_point_id: 充电桩ID
        connector_id: 连接器ID
        output_dir: 输出目录
    
    Returns:
        生成的二维码文件路径
    """
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 确保 token 存在，并用 token 构建二维码内容
    token_rec = ensure_qr_token(db, charge_point_id, connector_id)
    payload = build_qr_payload(token_rec.token)
    
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
    
    logger.info(
        f"二维码已生成: {file_path} (cp={charge_point_id} connector={connector_id} token={token_rec.token})"
    )
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
