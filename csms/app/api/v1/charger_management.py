#
# 充电桩管理API
# 新充电桩接入、录入、配置管理
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database import get_db, ChargePoint, Site, Tariff, EVSE, EVSEStatus
from app.services.charge_point_service import ChargePointService
from app.core.logging_config import get_logger
from app.core.config import get_settings
from app.core.id_generator import generate_site_id

settings = get_settings()
logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求模型 ====================

class CreateChargerRequest(BaseModel):
    """创建充电桩请求"""
    charger_id: str = Field(..., description="充电桩ID")
    vendor: Optional[str] = Field(None, description="厂商")
    model: Optional[str] = Field(None, description="型号")
    serial_number: Optional[str] = Field(None, description="序列号")
    firmware_version: Optional[str] = Field(None, description="固件版本")
    connector_type: str = Field("Type2", description="连接器类型")
    charging_rate: float = Field(7.0, description="充电速率 (kW)")
    latitude: Optional[float] = Field(None, description="纬度")
    longitude: Optional[float] = Field(None, description="经度")
    address: Optional[str] = Field(None, description="地址")
    price_per_kwh: float = Field(2700.0, description="每度电价格 (COP/kWh)")


class UpdateChargerLocationRequest(BaseModel):
    """更新充电桩位置请求"""
    charger_id: str = Field(..., description="充电桩ID")
    latitude: float = Field(..., description="纬度")
    longitude: float = Field(..., description="经度")
    address: str = Field("", description="地址")


class UpdateChargerPricingRequest(BaseModel):
    """更新充电桩定价请求"""
    charger_id: str = Field(..., description="充电桩ID")
    price_per_kwh: float = Field(..., gt=0, description="每度电价格 (COP/kWh)")
    charging_rate: Optional[float] = Field(None, description="充电速率 (kW)")


class UpdateChargerInfoRequest(BaseModel):
    """更新充电桩信息请求"""
    charger_id: str = Field(..., description="充电桩ID")
    vendor: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    connector_type: Optional[str] = None


class ChargerStatus(BaseModel):
    """充电桩状态信息"""
    charger_id: str
    is_connected: bool
    is_configured: bool
    status: str
    last_seen: Optional[str]
    vendor: Optional[str] = None
    model: Optional[str] = None
    has_location: bool = False
    has_pricing: bool = False


# ==================== 工具函数 ====================

def check_charger_connection(charger_id: str) -> bool:
    """检查充电桩是否已连接"""
    from app.core.config import get_settings
    settings = get_settings()
    
    if settings.enable_distributed:
        # 分布式模式
        try:
            from app.ocpp.distributed_connection_manager import distributed_connection_manager
            return distributed_connection_manager.is_connected(charger_id)
        except Exception:
            return False
    else:
        # 单服务器模式
        try:
            from app.ocpp.connection_manager import connection_manager
            return connection_manager.is_connected(charger_id)
        except Exception:
            return False


def get_charger_from_redis(charger_id: str) -> Optional[dict]:
    """从Redis获取充电桩信息"""
    try:
        import redis
        import json
        import os
        
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_client = redis.from_url(redis_url, decode_responses=True)
        
        charger_data = redis_client.hget("chargers", charger_id)
        if charger_data:
            return json.loads(charger_data)
        return None
    except Exception as e:
        logger.error(f"从Redis获取充电桩信息失败: {e}")
        return None


# ==================== API端点 ====================

@router.get("/pending", summary="获取待配置的充电桩列表")
def get_pending_chargers(db: Session = Depends(get_db)) -> List[ChargerStatus]:
    """
    获取已连接但未完整配置的充电桩列表
    
    判断标准：
    1. 充电桩已连接（WebSocket在线）
    2. 但数据库中不存在或配置不完整（缺少位置、价格等）
    """
    logger.info("[API] GET /api/v1/charger-management/pending | 获取待配置充电桩列表")
    
    pending_chargers = []
    
    # 获取所有已连接的充电桩ID
    from app.core.config import get_settings
    settings = get_settings()
    
    if settings.enable_distributed:
        # 分布式模式
        try:
            from app.ocpp.distributed_connection_manager import distributed_connection_manager
            connected_ids = distributed_connection_manager.get_all_connected_chargers()
        except Exception:
            connected_ids = []
    else:
        # 单服务器模式
        try:
            from app.ocpp.connection_manager import connection_manager
            connected_ids = connection_manager.get_all_charger_ids()
        except Exception:
            connected_ids = []
    
    # 检查每个已连接的充电桩
    for charger_id in connected_ids:
        # 从Redis获取实时状态
        redis_charger = get_charger_from_redis(charger_id)
        
        # 从数据库获取配置信息
        charge_point = db.query(ChargePoint).filter(ChargePoint.id == charger_id).first()
        
        # 判断是否需要配置
        is_configured = False
        has_location = False
        has_pricing = False
        
        if charge_point:
            is_configured = True
            # 检查站点位置
            site = charge_point.site if charge_point.site_id else None
            has_location = site and site.latitude is not None and site.longitude is not None
            # 检查定价
            tariff = db.query(Tariff).filter(
                Tariff.site_id == charge_point.site_id,
                Tariff.is_active == True
            ).first() if charge_point.site_id else None
            has_pricing = tariff and tariff.base_price_per_kwh > 0
        elif redis_charger:
            # 检查Redis中的数据是否完整
            location = redis_charger.get("location", {})
            has_location = location.get("latitude") is not None and location.get("longitude") is not None
            has_pricing = redis_charger.get("price_per_kwh") is not None and redis_charger.get("price_per_kwh", 0) > 0
        
        # 如果配置不完整，加入待配置列表
        if not is_configured or not has_location or not has_pricing:
            status_info = ChargerStatus(
                charger_id=charger_id,
                is_connected=True,
                is_configured=is_configured,
                status=redis_charger.get("status", "Unknown") if redis_charger else "Unknown",
                last_seen=redis_charger.get("last_seen") if redis_charger else None,
                vendor=redis_charger.get("vendor") if redis_charger else None,
                model=redis_charger.get("model") if redis_charger else None,
                has_location=has_location,
                has_pricing=has_pricing
            )
            pending_chargers.append(status_info)
    
    logger.info(f"[API] GET /api/v1/charger-management/pending 成功 | 找到 {len(pending_chargers)} 个待配置充电桩")
    return pending_chargers


@router.post("/create", summary="创建/录入充电桩")
def create_charger(req: CreateChargerRequest, db: Session = Depends(get_db)) -> dict:
    """
    创建新的充电桩记录
    
    如果充电桩已存在，则更新信息
    """
    logger.info(
        f"[API] POST /api/v1/charger-management/create | "
        f"充电桩ID: {req.charger_id} | "
        f"厂商: {req.vendor} | 型号: {req.model}"
    )
    
    # 检查充电桩是否已存在
    charge_point = db.query(ChargePoint).filter(ChargePoint.id == req.charger_id).first()
    
    if charge_point:
        logger.info(f"[API] 充电桩 {req.charger_id} 已存在，执行更新操作")
        # 更新现有充电桩
        if req.vendor:
            charge_point.vendor = req.vendor
        if req.model:
            charge_point.model = req.model
        if req.serial_number:
            charge_point.serial_number = req.serial_number
        if req.firmware_version:
            charge_point.firmware_version = req.firmware_version
        
        # 更新站点位置
        if req.latitude is not None and req.longitude is not None:
            site = charge_point.site if charge_point.site_id else None
            if not site:
                # 创建新站点
                site = Site(
                    id=generate_site_id(f"站点-{req.charger_id}"),
                    name=f"站点-{req.charger_id}",
                    address=req.address or "",
                    latitude=req.latitude,
                    longitude=req.longitude
                )
                db.add(site)
                db.flush()
                charge_point.site_id = site.id
            else:
                site.latitude = req.latitude
                site.longitude = req.longitude
                if req.address:
                    site.address = req.address
        
        # 更新定价
        if req.price_per_kwh:
            site_id = charge_point.site_id
            if site_id:
                tariff = db.query(Tariff).filter(
                    Tariff.site_id == site_id,
                    Tariff.is_active == True
                ).first()
                if not tariff:
                    tariff = Tariff(
                        site_id=site_id,
                        name="默认定价",
                        base_price_per_kwh=req.price_per_kwh,
                        service_fee=0,
                        valid_from=datetime.now(timezone.utc),
                        is_active=True
                    )
                    db.add(tariff)
                else:
                    tariff.base_price_per_kwh = req.price_per_kwh
    else:
        # 创建新充电桩
        logger.info(f"[API] 创建新充电桩: {req.charger_id}")
        
        # 创建或获取站点
        site = None
        if req.latitude is not None and req.longitude is not None:
            site = Site(
                id=generate_site_id(f"站点-{req.charger_id}"),
                name=f"站点-{req.charger_id}",
                address=req.address or "",
                latitude=req.latitude,
                longitude=req.longitude
            )
            db.add(site)
            db.flush()
        
        # 创建充电桩
        charge_point = ChargePoint(
            id=req.charger_id,
            site_id=site.id if site else None,
            vendor=req.vendor,
            model=req.model,
            serial_number=req.serial_number,
            firmware_version=req.firmware_version,
            device_serial_number=req.serial_number
        )
        db.add(charge_point)
        db.flush()
        
        # 创建定价规则
        if req.price_per_kwh and site:
            tariff = Tariff(
                site_id=site.id,
                name="默认定价",
                base_price_per_kwh=req.price_per_kwh,
                service_fee=0,
                valid_from=datetime.now(timezone.utc),
                is_active=True
            )
            db.add(tariff)
    
    try:
        db.commit()
        db.refresh(charger)
        
        # 同步更新Redis
        try:
            import redis
            import json
            import os
            
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            redis_client = redis.from_url(redis_url, decode_responses=True)
            
            charger_data = get_charger_from_redis(req.charger_id) or {}
            charger_data.update({
                "id": req.charger_id,
                "vendor": req.vendor,
                "model": req.model,
                "connector_type": req.connector_type,
                "charging_rate": req.charging_rate,
                "price_per_kwh": req.price_per_kwh,
                "location": {
                    "latitude": req.latitude,
                    "longitude": req.longitude,
                    "address": req.address or ""
                }
            })
            
            redis_client.hset("chargers", req.charger_id, json.dumps(charger_data))
        except Exception as e:
            logger.warning(f"同步Redis失败: {e}")
        
        logger.info(
            f"[API] POST /api/v1/charger-management/create 成功 | "
            f"充电桩ID: {req.charger_id} | "
            f"位置: ({req.latitude}, {req.longitude}) | "
            f"价格: {req.price_per_kwh} COP/kWh"
        )
        
        # 获取站点和定价信息
        site = charge_point.site if charge_point.site_id else None
        tariff = db.query(Tariff).filter(
            Tariff.site_id == charge_point.site_id,
            Tariff.is_active == True
        ).first() if charge_point.site_id else None
        
        # 获取状态
        evse_status = db.query(EVSEStatus).filter(
            EVSEStatus.charge_point_id == charge_point.id
        ).first()
        status = evse_status.status if evse_status else "Unknown"
        
        return {
            "success": True,
            "message": "充电桩已创建/更新",
            "charger": {
                "id": charge_point.id,
                "vendor": charge_point.vendor,
                "model": charge_point.model,
                "status": status,
                "location": {
                    "latitude": site.latitude if site else None,
                    "longitude": site.longitude if site else None,
                    "address": site.address if site else None
                },
                "price_per_kwh": tariff.base_price_per_kwh if tariff else None
            }
        }
    except Exception as e:
        db.rollback()
        logger.error(f"创建充电桩失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建充电桩失败: {str(e)}")


@router.post("/location", summary="设置充电桩位置")
def update_charger_location(req: UpdateChargerLocationRequest, db: Session = Depends(get_db)) -> dict:
    """设置或更新充电桩的地理位置"""
    logger.info(
        f"[API] POST /api/v1/charger-management/location | "
        f"充电桩ID: {req.charger_id} | "
        f"位置: ({req.latitude}, {req.longitude}) | "
        f"地址: {req.address or '无'}"
    )
    
    charge_point = db.query(ChargePoint).filter(ChargePoint.id == req.charger_id).first()
    
    if not charge_point:
        logger.warning(f"[API] POST /api/v1/charger-management/location | 充电桩 {req.charger_id} 未找到")
        raise HTTPException(status_code=404, detail=f"充电桩 {req.charger_id} 未找到，请先创建充电桩")
    
    # 更新或创建站点位置信息
    site = charge_point.site if charge_point.site_id else None
    if not site:
        # 创建新站点
        site = Site(
            id=generate_site_id(f"站点-{req.charger_id}"),
            name=f"站点-{req.charger_id}",
            address=req.address or "",
            latitude=req.latitude,
            longitude=req.longitude
        )
        db.add(site)
        db.flush()
        charge_point.site_id = site.id
    else:
        site.latitude = req.latitude
        site.longitude = req.longitude
        if req.address:
            site.address = req.address
    
    try:
        db.commit()
        
        # 同步更新Redis
        try:
            import redis
            import json
            import os
            
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            redis_client = redis.from_url(redis_url, decode_responses=True)
            
            charger_data = get_charger_from_redis(req.charger_id) or {"id": req.charger_id}
            charger_data["location"] = {
                "latitude": req.latitude,
                "longitude": req.longitude,
                "address": req.address
            }
            
            redis_client.hset("chargers", req.charger_id, json.dumps(charger_data))
        except Exception as e:
            logger.warning(f"同步Redis失败: {e}")
        
        logger.info(
            f"[API] POST /api/v1/charger-management/location 成功 | "
            f"充电桩ID: {req.charger_id} | "
            f"位置: ({req.latitude}, {req.longitude})"
        )
        
        return {
            "success": True,
            "message": "位置已更新",
            "location": {
                "latitude": req.latitude,
                "longitude": req.longitude,
                "address": req.address
            }
        }
    except Exception as e:
        db.rollback()
        logger.error(f"更新位置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新位置失败: {str(e)}")


@router.post("/pricing", summary="设置充电桩定价")
def update_charger_pricing(req: UpdateChargerPricingRequest, db: Session = Depends(get_db)) -> dict:
    """设置或更新充电桩的价格和充电速率"""
    logger.info(
        f"[API] POST /api/v1/charger-management/pricing | "
        f"充电桩ID: {req.charger_id} | "
        f"价格: {req.price_per_kwh} COP/kWh | "
        f"充电速率: {req.charging_rate or '未设置'} kW"
    )
    
    charge_point = db.query(ChargePoint).filter(ChargePoint.id == req.charger_id).first()
    
    if not charge_point:
        logger.warning(f"[API] POST /api/v1/charger-management/pricing | 充电桩 {req.charger_id} 未找到")
        raise HTTPException(status_code=404, detail=f"充电桩 {req.charger_id} 未找到，请先创建充电桩")
    
    # 确保有站点
    if not charge_point.site_id:
        raise HTTPException(status_code=400, detail="充电桩未配置站点，请先设置位置")
    
    # 更新或创建定价规则
    tariff = db.query(Tariff).filter(
        Tariff.site_id == charge_point.site_id,
        Tariff.is_active == True
    ).first()
    
    if not tariff:
        tariff = Tariff(
            site_id=charge_point.site_id,
            name="默认定价",
            base_price_per_kwh=req.price_per_kwh,
            service_fee=0,
            valid_from=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(tariff)
    else:
        tariff.base_price_per_kwh = req.price_per_kwh
    
    try:
        db.commit()
        
        # 同步更新Redis
        try:
            import redis
            import json
            import os
            
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            redis_client = redis.from_url(redis_url, decode_responses=True)
            
            charger_data = get_charger_from_redis(req.charger_id) or {"id": req.charger_id}
            charger_data["price_per_kwh"] = req.price_per_kwh
            if req.charging_rate:
                charger_data["charging_rate"] = req.charging_rate
            
            redis_client.hset("chargers", req.charger_id, json.dumps(charger_data))
        except Exception as e:
            logger.warning(f"同步Redis失败: {e}")
        
        logger.info(
            f"[API] POST /api/v1/charger-management/pricing 成功 | "
            f"充电桩ID: {req.charger_id} | "
            f"价格: {req.price_per_kwh} COP/kWh | "
            f"充电速率: {charger.charging_rate} kW"
        )
        
        return {
            "success": True,
            "message": "价格已更新",
            "pricing": {
                "price_per_kwh": req.price_per_kwh
            }
        }
    except Exception as e:
        db.rollback()
        logger.error(f"更新价格失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新价格失败: {str(e)}")


@router.get("/{charger_id}/status", summary="获取充电桩状态和配置信息")
def get_charger_status(charger_id: str, db: Session = Depends(get_db)) -> dict:
    """获取充电桩的连接状态和配置完整性"""
    logger.info(f"[API] GET /api/v1/charger-management/{charger_id}/status | 查询充电桩状态")
    
    # 检查连接状态
    is_connected = check_charger_connection(charger_id)
    
    # 从Redis获取实时信息
    redis_charger = get_charger_from_redis(charger_id)
    
    # 从数据库获取配置信息
    charge_point = db.query(ChargePoint).filter(ChargePoint.id == charger_id).first()
    
    # 判断配置完整性
    is_configured = charge_point is not None
    has_location = False
    has_pricing = False
    
    if charge_point:
        site = charge_point.site if charge_point.site_id else None
        has_location = site and site.latitude is not None and site.longitude is not None
        
        tariff = db.query(Tariff).filter(
            Tariff.site_id == charge_point.site_id,
            Tariff.is_active == True
        ).first() if charge_point.site_id else None
        has_pricing = tariff and tariff.base_price_per_kwh > 0
    elif redis_charger:
        location = redis_charger.get("location", {})
        has_location = location.get("latitude") is not None and location.get("longitude") is not None
        has_pricing = redis_charger.get("price_per_kwh") is not None and redis_charger.get("price_per_kwh", 0) > 0
    
    return {
        "charger_id": charger_id,
        "is_connected": is_connected,
        "is_configured": is_configured,
        "has_location": has_location,
        "has_pricing": has_pricing,
        "configuration_complete": is_configured and has_location and has_pricing,
        "real_time_info": {
            "status": redis_charger.get("status", "Unknown") if redis_charger else "Unknown",
            "last_seen": redis_charger.get("last_seen") if redis_charger else None,
            "vendor": redis_charger.get("vendor") if redis_charger else None,
            "model": redis_charger.get("model") if redis_charger else None,
        },
        "database_info": {
            "exists": charge_point is not None,
            "location": {
                "latitude": charge_point.site.latitude if charge_point and charge_point.site else None,
                "longitude": charge_point.site.longitude if charge_point and charge_point.site else None,
                "address": charge_point.site.address if charge_point and charge_point.site else None,
            } if charge_point and charge_point.site else None,
            "pricing": (
                (lambda: (
                    (lambda t: {"price_per_kwh": t.base_price_per_kwh} if t else None)(
                        db.query(Tariff).filter(
                            Tariff.site_id == charge_point.site_id,
                            Tariff.is_active == True
                        ).first()
                    ) if charge_point and charge_point.site_id else None
                ))()
            ) if charge_point and charge_point.site_id else None,
        }
    }
    
    logger.info(
        f"[API] GET /api/v1/charger-management/{charger_id}/status 成功 | "
        f"连接状态: {'已连接' if is_connected else '未连接'} | "
        f"配置完整: {is_configured and has_location and has_pricing}"
    )

