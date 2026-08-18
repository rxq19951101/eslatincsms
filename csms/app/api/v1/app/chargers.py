#
# APP用户 - 充电站查询API
# 提供给普通用户查询充电站的接口
#

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.database.base import get_db, SuperSessionLocal
from app.database.models import ChargePoint, Site, EVSE, EVSEStatus, AppUser
from app.core.logging_config import get_logger
from app.core.auth import get_current_user
from app.services.pricing_service import PricingService
from math import radians, cos, sin, asin, sqrt
from uuid import UUID

logger = get_logger("ocpp_csms")

router = APIRouter()


def get_public_charge_point_db():
    """Explicit cross-tenant read boundary for public App charge-point data."""
    db = SuperSessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_app_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_public_charge_point_db)
) -> AppUser:
    """
    获取当前 APP 平台用户对象（AppUser）
    """
    user_id = current_user_payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    app_user = db.query(AppUser).filter(AppUser.id == UUID(str(user_id))).first()
    if not app_user:
        raise HTTPException(status_code=404, detail="User not found")

    return app_user


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    计算两点之间的距离（千米）
    使用 Haversine 公式
    """
    # 转换为弧度
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    
    # Haversine公式
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    # 地球平均半径（千米）
    r = 6371
    
    return c * r


@router.get("", summary="获取充电站列表（普通用户）")
async def list_chargers_for_app(
    latitude: Optional[float] = Query(None, description="当前纬度"),
    longitude: Optional[float] = Query(None, description="当前经度"),
    radius: Optional[float] = Query(None, description="搜索半径（米）"),
    limit: Optional[int] = Query(100, description="返回数量限制"),
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db)
) -> List[dict]:
    """
    获取充电站列表（普通用户）
    
    - 只返回已配置且激活的充电站
    - 支持基于位置的搜索
    """
    logger.info(f"[APP API] GET /api/v1/app/chargers | 用户: {current_user_obj.id}, 位置: ({latitude}, {longitude}), 半径: {radius}m")
    
    # 查询充电桩 + 站点
    # 注意：evses 表不存 status，实时状态在 evse_status 表
    query = db.query(ChargePoint).join(Site, ChargePoint.site_id == Site.id).filter(
        ChargePoint.is_active.is_(True),
        ChargePoint.commissioning_status == "commissioned",
        Site.is_active.is_(True),
    )
    
    # 只返回有位置信息的充电站
    query = query.filter(
        and_(
            Site.latitude.isnot(None),
            Site.longitude.isnot(None)
        )
    )
    
    chargers = query.limit(limit).all()
    
    # 构建返回数据
    result = []
    for charger in chargers:
        # 获取站点信息
        site = charger.site
        if not site:
            continue
        
        pricing = PricingService.resolve(db, charger.tenant_id, charger.id)
        if not pricing.is_available:
            continue
        
        # 计算可用连接器数量（evse_status.status == 'Available'）
        # 注意：status 可能是历史残留；必须以 last_seen 判断在线后才计数
        total_count = db.query(EVSE).filter(EVSE.charge_point_id == charger.id).count()

        statuses = [
            s[0]
            for s in db.query(EVSEStatus.status)
            .filter(EVSEStatus.charge_point_id == charger.id)
            .all()
        ]
        
        last_seen = db.query(func.max(EVSEStatus.last_seen)).filter(
            EVSEStatus.charge_point_id == charger.id
        ).scalar()
        
        # 根据 last_seen 判断是否真正在线（超过5分钟未更新则认为离线）
        from datetime import datetime, timezone
        is_online = False
        if last_seen:
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            time_diff = datetime.now(timezone.utc) - last_seen
            is_online = time_diff.total_seconds() < 300  # 5分钟内更新过才认为在线
        
        if not is_online:
            overall_status = "Offline"
            available_count = 0
        else:
            available_count = db.query(EVSEStatus).filter(
                EVSEStatus.charge_point_id == charger.id,
                EVSEStatus.status == "Available",
            ).count()
            if "Charging" in statuses:
                overall_status = "Charging"
            elif "Available" in statuses:
                overall_status = "Available"
            elif len(statuses) > 0:
                overall_status = statuses[0] or "Unknown"
            else:
                overall_status = "Unknown"
        
        charger_data = {
            "id": charger.id,
            "ocpp_identity": charger.ocpp_identity,
            "vendor": charger.vendor,
            "model": charger.model,
            "site_name": site.name,
            "site_address": site.address,
            "latitude": float(site.latitude) if site.latitude else None,
            "longitude": float(site.longitude) if site.longitude else None,
            "status": overall_status,
            "price_per_kwh": float(pricing.base_price_per_kwh or 0),
            "pricing": pricing.as_dict(),
            "available_connectors": available_count,
            "total_connectors": total_count,
            "is_configured": True,
            "has_location": True,
            "has_pricing": True,
            "last_seen": last_seen.isoformat() if last_seen else None,
        }
        
        # 如果提供了位置，计算距离
        if latitude is not None and longitude is not None and site.latitude and site.longitude:
            distance_km = calculate_distance(
                latitude, longitude,
                float(site.latitude), float(site.longitude)
            )
            charger_data["distance_km"] = round(distance_km, 2)
            
            # 如果提供了半径，过滤距离
            if radius is not None:
                distance_m = distance_km * 1000
                if distance_m > radius:
                    continue
        
        result.append(charger_data)
    
    # 如果有距离信息，按距离排序
    if latitude is not None and longitude is not None:
        result.sort(key=lambda x: x.get("distance_km", float('inf')))
    
    logger.info(f"[APP API] 返回 {len(result)} 个充电站")
    return result


@router.get("/{charge_point_id}", summary="获取充电站详情（普通用户）")
async def get_charger_detail_for_app(
    charge_point_id: str,
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_public_charge_point_db)
) -> dict:
    """
    获取充电站详情（普通用户）
    """
    logger.info(f"[APP API] GET /api/v1/app/chargers/{charge_point_id} | 用户: {current_user_obj.id}")
    
    # 获取充电站
    charger = db.query(ChargePoint).join(Site, ChargePoint.site_id == Site.id).filter(
        ChargePoint.id == charge_point_id,
        ChargePoint.is_active.is_(True),
        ChargePoint.commissioning_status == "commissioned",
        Site.is_active.is_(True),
    ).first()
    
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    # 获取站点信息
    site = charger.site
    
    pricing = PricingService.resolve(db, charger.tenant_id, charger.id)
    if not pricing.is_available:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    # 获取连接器信息
    evses = db.query(EVSE).filter(EVSE.charge_point_id == charger.id).all()
    status_rows = db.query(EVSEStatus).filter(EVSEStatus.charge_point_id == charger.id).all()
    status_map = {row.evse_id: row.status for row in status_rows}
    
    # 检查最后更新时间判断是否在线
    last_seen_detail = db.query(func.max(EVSEStatus.last_seen)).filter(
        EVSEStatus.charge_point_id == charger.id
    ).scalar()
    
    from datetime import datetime, timezone
    is_online_detail = False
    if last_seen_detail:
        if last_seen_detail.tzinfo is None:
            last_seen_detail = last_seen_detail.replace(tzinfo=timezone.utc)
        time_diff = datetime.now(timezone.utc) - last_seen_detail
        is_online_detail = time_diff.total_seconds() < 300  # 5分钟内更新过才认为在线
    
    def connector_display_status(evse_pk: int) -> str:
        raw = status_map.get(evse_pk, "Unknown")
        # 桩离线时，不展示过期的 Available/Charging，统一 Offline
        if not is_online_detail and raw in ("Available", "Charging", "Preparing", "SuspendedEV", "SuspendedEVSE"):
            return "Offline"
        if not is_online_detail and raw == "Unknown":
            return "Offline"
        return raw

    available_count = (
        0
        if not is_online_detail
        else sum(1 for e in evses if status_map.get(e.id) == "Available")
    )
    
    # 如果离线，状态为Offline；否则根据available数量判断
    detail_status = "Offline" if not is_online_detail else ("Available" if available_count > 0 else "Unknown")
    
    return {
        "id": charger.id,
        "ocpp_identity": charger.ocpp_identity,
        "vendor": charger.vendor,
        "model": charger.model,
        "serial_number": charger.serial_number,
        "firmware_version": charger.firmware_version,
        "site_name": site.name if site else None,
        "site_address": site.address if site else None,
        "latitude": float(site.latitude) if site and site.latitude else None,
        "longitude": float(site.longitude) if site and site.longitude else None,
        "status": detail_status,
        "price_per_kwh": float(pricing.base_price_per_kwh or 0),
        "pricing": pricing.as_dict(),
        "available_connectors": available_count,
        "total_connectors": len(evses),
        "last_seen": last_seen_detail.isoformat() if last_seen_detail else None,
        "connectors": [
            {
                "id": evse.id,
                "connector_id": evse.evse_id,
                "status": connector_display_status(evse.id),
                "power_kw": evse.max_power_kw,
                "connector_type": evse.connector_type,
            }
            for evse in evses
        ],
    }
