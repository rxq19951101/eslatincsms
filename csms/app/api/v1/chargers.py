#
# 充电桩管理API
# 提供充电桩的CRUD操作（使用新表结构）
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.database import get_db, ChargePoint, Site, EVSE, EVSEStatus, Tariff
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


@router.get("", summary="获取所有充电桩")
def list_chargers(
    filter_type: Optional[str] = Query(None, description="筛选类型: configured(已配置), unconfigured(未配置)"),
    db: Session = Depends(get_db)
) -> List[dict]:
    """
    获取充电桩列表（使用新表结构）
    
    支持筛选：
    - configured: 只返回已配置的充电桩（有位置和价格）
    - unconfigured: 只返回未配置的充电桩（缺少位置或价格）
    """
    logger.info(f"[API] GET /api/v1/chargers | 筛选类型: {filter_type or '全部'}")
    
    query = db.query(ChargePoint)
    
    # 根据筛选类型过滤
    if filter_type == "configured":
        # 已配置：有位置和价格（通过站点和定价规则判断）
        query = query.join(Site).join(Tariff).filter(
            Site.latitude.isnot(None),
            Site.longitude.isnot(None),
            Tariff.is_active == True,
            Tariff.base_price_per_kwh > 0
        )
    elif filter_type == "unconfigured":
        # 未配置：缺少位置或价格
        query = query.outerjoin(Site).outerjoin(Tariff).filter(
            or_(
                Site.latitude.is_(None),
                Site.longitude.is_(None),
                Tariff.is_active == False,
                Tariff.base_price_per_kwh == 0
            )
        )
    
    charge_points = query.all()
    logger.info(f"[API] 查询到 {len(charge_points)} 个充电桩 | 筛选类型: {filter_type or '全部'}")
    
    result = []
    for cp in charge_points:
        # 获取站点信息
        site = cp.site if cp.site_id else None
        has_location = site and site.latitude is not None and site.longitude is not None
        
        # 获取定价信息
        tariff = db.query(Tariff).filter(
            Tariff.site_id == cp.site_id,
            Tariff.is_active == True
        ).first() if cp.site_id else None
        has_pricing = tariff and tariff.base_price_per_kwh > 0
        
        # 获取EVSE状态
        evse_status = db.query(EVSEStatus).filter(
            EVSEStatus.charge_point_id == cp.id
        ).first()
        status = evse_status.status if evse_status else "Unknown"
        last_seen = evse_status.last_seen if evse_status else None
        
        is_configured = has_location and has_pricing
        
        result.append({
            "id": cp.id,
            "vendor": cp.vendor,
            "model": cp.model,
            "status": status,
            "last_seen": last_seen.isoformat() if last_seen else None,
            "location": {
                "latitude": site.latitude if site else None,
                "longitude": site.longitude if site else None,
                "address": site.address if site else None,
            },
            "price_per_kwh": tariff.base_price_per_kwh if tariff else None,
            "is_configured": is_configured,
            "has_location": has_location,
            "has_pricing": has_pricing,
        })
    
    logger.info(f"[API] GET /api/v1/chargers 成功返回 {len(result)} 个充电桩")
    return result


@router.get("/{charge_point_id}", summary="获取充电桩详情")
def get_charger(charge_point_id: str, db: Session = Depends(get_db)) -> dict:
    """获取单个充电桩的详细信息（使用新表结构）"""
    logger.info(f"[API] GET /api/v1/chargers/{charge_point_id} | 请求充电桩详情")
    
    charge_point = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
    if not charge_point:
        logger.warning(f"[API] GET /api/v1/chargers/{charge_point_id} | 充电桩未找到")
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    # 获取站点信息
    site = charge_point.site if charge_point.site_id else None
    
    # 获取定价信息
    tariff = db.query(Tariff).filter(
        Tariff.site_id == charge_point.site_id,
        Tariff.is_active == True
    ).first() if charge_point.site_id else None
    
    # 获取EVSE状态
    evse_status = db.query(EVSEStatus).filter(
        EVSEStatus.charge_point_id == charge_point.id
    ).first()
    status = evse_status.status if evse_status else "Unknown"
    last_seen = evse_status.last_seen if evse_status else None
    
    # 获取EVSE列表
    evses = db.query(EVSE).filter(EVSE.charge_point_id == charge_point.id).all()
    evse_list = []
    for evse in evses:
        evse_status_item = db.query(EVSEStatus).filter(EVSEStatus.evse_id == evse.id).first()
        evse_list.append({
            "evse_id": evse.evse_id,
            "status": evse_status_item.status if evse_status_item else "Unknown",
            "last_seen": evse_status_item.last_seen.isoformat() if evse_status_item and evse_status_item.last_seen else None,
        })
    
    return {
        "id": charge_point.id,
        "vendor": charge_point.vendor,
        "model": charge_point.model,
        "serial_number": charge_point.serial_number,
        "firmware_version": charge_point.firmware_version,
        "status": status,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "location": {
            "latitude": site.latitude if site else None,
            "longitude": site.longitude if site else None,
            "address": site.address if site else None,
        },
        "price_per_kwh": tariff.base_price_per_kwh if tariff else None,
        "evses": evse_list,
        "created_at": charge_point.created_at.isoformat() if charge_point.created_at else None,
        "updated_at": charge_point.updated_at.isoformat() if charge_point.updated_at else None,
    }
    
    logger.info(f"[API] GET /api/v1/chargers/{charge_point_id} 成功 | 状态: {status}")

