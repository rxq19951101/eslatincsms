#
# 设备管理API
# 用于设备录入、查询、密码生成等
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database import get_db
from app.database.models import Device
from app.services.charge_point_service import ChargePointService
from app.core.mqtt_auth import MQTTAuthService
from app.core.crypto import derive_password, decrypt_master_secret
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求模型 ====================

class CreateDeviceRequest(BaseModel):
    """创建设备请求"""
    serial_number: str = Field(..., description="设备序列号（必须是15位）", min_length=15, max_length=15)
    vendor: Optional[str] = Field(None, description="设备厂商（用于推断设备类型）")
    device_type_code: Optional[str] = Field(None, description="设备类型代码（如：zcf, tesla, abb）")


class DeviceResponse(BaseModel):
    """设备响应"""
    serial_number: str
    device_type_code: str
    device_type_name: str
    mqtt_client_id: str
    mqtt_username: str
    mqtt_password: str  # 派生密码
    is_active: bool
    last_connected: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class DeviceListResponse(BaseModel):
    """设备列表响应"""
    devices: List[DeviceResponse]
    total: int


# ==================== API端点 ====================

@router.post("", response_model=DeviceResponse, status_code=201, summary="录入设备")
def create_device(
    req: CreateDeviceRequest,
    db: Session = Depends(get_db)
):
    """
    录入新设备
    
    设备必须在使用MQTT传输前录入系统，用于MQTT认证。
    
    **认证信息**：
    - MQTT客户端ID: `{type_code}&{serial_number}`
    - MQTT用户名: `{serial_number}`
    - MQTT密码: 通过HMAC从master_secret派生（12位）
    
    **设备类型推断**：
    - 如果提供 `device_type_code`，直接使用
    - 否则根据 `vendor` 自动推断（如：Schneider Electric → schneider）
    - 如果都无法推断，使用默认类型
    """
    # 验证序列号长度
    if len(req.serial_number) != 15:
        raise HTTPException(
            status_code=400,
            detail=f"设备序列号必须是15位，当前为{len(req.serial_number)}位"
        )
    
    # 检查设备是否已存在
    existing_device = db.query(Device).filter(
        Device.serial_number == req.serial_number
    ).first()
    
    if existing_device:
        raise HTTPException(
            status_code=400,
            detail=f"设备 {req.serial_number} 已存在"
        )
    
    # 确定设备类型代码
    vendor = req.vendor
    if req.device_type_code:
        # 如果提供了设备类型代码，直接使用
        type_code = req.device_type_code
    else:
        # 使用服务层的逻辑推断设备类型代码
        type_code = ChargePointService.infer_type_code(vendor)
    
    # 创建设备
    device = ChargePointService.get_or_create_device(
        db=db,
        device_serial_number=req.serial_number,
        vendor=vendor,
        type_code=type_code
    )
    
    if not device:
        raise HTTPException(
            status_code=500,
            detail="设备创建失败"
        )
    
    # 获取派生密码（用于返回给用户）
    try:
        master_secret = decrypt_master_secret(device.master_secret_encrypted)
        mqtt_password = derive_password(master_secret, req.serial_number)
    except Exception as e:
        logger.error(f"获取设备密码失败: {e}", exc_info=True)
        mqtt_password = "N/A"
    
    return DeviceResponse(
        serial_number=device.serial_number,
        device_type_code=device.type_code,
        device_type_name=device.type_code,  # 使用type_code作为名称
        mqtt_client_id=device.mqtt_client_id,
        mqtt_username=device.mqtt_username,
        mqtt_password=mqtt_password,
        is_active=device.is_active,
        last_connected=device.last_connected.isoformat() if device.last_connected else None,
        created_at=device.created_at.isoformat()
    )


@router.get("", response_model=DeviceListResponse, summary="获取设备列表")
def list_devices(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回记录数"),
    device_type_code: Optional[str] = Query(None, description="按设备类型筛选"),
    is_active: Optional[bool] = Query(None, description="按激活状态筛选"),
    db: Session = Depends(get_db)
):
    """获取设备列表"""
    query = db.query(Device)
    
    # 筛选条件
    if device_type_code:
        query = query.filter(Device.type_code == device_type_code)
    
    if is_active is not None:
        query = query.filter(Device.is_active == is_active)
    
    # 总数
    total = query.count()
    
    # 分页
    devices = query.offset(skip).limit(limit).all()
    
    # 构建响应
    device_responses = []
    for device in devices:
        # 获取派生密码
        try:
            master_secret = decrypt_master_secret(device.master_secret_encrypted)
            mqtt_password = derive_password(master_secret, device.serial_number)
        except Exception as e:
            logger.error(f"获取设备密码失败: {e}", exc_info=True)
            mqtt_password = "N/A"
        
        device_responses.append(DeviceResponse(
            serial_number=device.serial_number,
            device_type_code=device.type_code,
            device_type_name=device.type_code,  # 使用type_code作为名称
            mqtt_client_id=device.mqtt_client_id,
            mqtt_username=device.mqtt_username,
            mqtt_password=mqtt_password,
            is_active=device.is_active,
            last_connected=device.last_connected.isoformat() if device.last_connected else None,
            created_at=device.created_at.isoformat()
        ))
    
    return DeviceListResponse(devices=device_responses, total=total)


@router.get("/{serial_number}", response_model=DeviceResponse, summary="获取设备详情")
def get_device(
    serial_number: str,
    db: Session = Depends(get_db)
):
    """获取设备详情（包含MQTT认证信息）"""
    device = db.query(Device).filter(
        Device.serial_number == serial_number
    ).first()
    
    if not device:
        raise HTTPException(
            status_code=404,
            detail=f"设备 {serial_number} 不存在"
        )
    
    # 获取派生密码
    try:
        master_secret = decrypt_master_secret(device.master_secret_encrypted)
        mqtt_password = derive_password(master_secret, serial_number)
    except Exception as e:
        logger.error(f"获取设备密码失败: {e}", exc_info=True)
        mqtt_password = "N/A"
    
    return DeviceResponse(
        serial_number=device.serial_number,
        device_type_code=device.type_code,
        device_type_name=device.type_code,  # 使用type_code作为名称
        mqtt_client_id=device.mqtt_client_id,
        mqtt_username=device.mqtt_username,
        mqtt_password=mqtt_password,
        is_active=device.is_active,
        last_connected=device.last_connected.isoformat() if device.last_connected else None,
        created_at=device.created_at.isoformat()
    )


@router.get("/{serial_number}/password", summary="获取设备MQTT密码")
def get_device_password(
    serial_number: str,
    db: Session = Depends(get_db)
):
    """
    获取设备的MQTT密码
    
    密码通过HMAC从master_secret派生，每次调用返回相同的密码。
    """
    device = db.query(Device).filter(
        Device.serial_number == serial_number
    ).first()
    
    if not device:
        raise HTTPException(
            status_code=404,
            detail=f"设备 {serial_number} 不存在"
        )
    
    # 获取派生密码
    try:
        master_secret = decrypt_master_secret(device.master_secret_encrypted)
        mqtt_password = derive_password(master_secret, serial_number)
    except Exception as e:
        logger.error(f"获取设备密码失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取密码失败: {str(e)}"
        )
    
    return {
        "serial_number": serial_number,
        "mqtt_client_id": device.mqtt_client_id,
        "mqtt_username": device.mqtt_username,
        "mqtt_password": mqtt_password,
        "device_type_code": device.type_code
    }


@router.put("/{serial_number}/activate", summary="激活/停用设备")
def toggle_device_status(
    serial_number: str,
    is_active: bool = Query(..., description="是否激活"),
    db: Session = Depends(get_db)
):
    """激活或停用设备"""
    device = db.query(Device).filter(
        Device.serial_number == serial_number
    ).first()
    
    if not device:
        raise HTTPException(
            status_code=404,
            detail=f"设备 {serial_number} 不存在"
        )
    
    device.is_active = is_active
    device.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    return {
        "serial_number": serial_number,
        "is_active": is_active,
        "message": f"设备已{'激活' if is_active else '停用'}"
    }

