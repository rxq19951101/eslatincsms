#
# 事务管理API
# 提供充电会话的查询和管理（使用新表结构）
#

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db, ChargingSession, ChargePoint, EVSE
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


@router.get("", summary="获取充电会话列表")
def list_transactions(
    charge_point_id: Optional[str] = Query(None, description="充电桩ID"),
    status: Optional[str] = Query(None, description="状态过滤"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
) -> List[dict]:
    """获取充电会话列表（使用新表结构）"""
    logger.info(
        f"[API] GET /api/v1/transactions | "
        f"充电桩ID: {charge_point_id or '全部'} | "
        f"状态: {status or '全部'} | "
        f"限制: {limit} | 偏移: {offset}"
    )
    
    query = db.query(ChargingSession)
    
    if charge_point_id:
        query = query.filter(ChargingSession.charge_point_id == charge_point_id)
    if status:
        query = query.filter(ChargingSession.status == status)
    
    sessions = query.order_by(ChargingSession.start_time.desc()).offset(offset).limit(limit).all()
    
    logger.info(f"[API] GET /api/v1/transactions 成功 | 返回 {len(sessions)} 个会话")
    
    result = []
    for s in sessions:
        # 计算能量（kWh）和时长（分钟）
        energy_kwh = None
        duration_minutes = None
        
        if s.meter_stop is not None and s.meter_start is not None:
            energy_wh = s.meter_stop - s.meter_start
            energy_kwh = energy_wh / 1000.0 if energy_wh > 0 else 0
        
        if s.end_time and s.start_time:
            duration_seconds = (s.end_time - s.start_time).total_seconds()
            duration_minutes = duration_seconds / 60.0
        
        result.append({
            "id": s.id,
            "transaction_id": s.transaction_id,
            "charge_point_id": s.charge_point_id,
            "id_tag": s.id_tag,
            "user_id": s.user_id,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "end_time": s.end_time.isoformat() if s.end_time else None,
            "energy_kwh": energy_kwh,
            "duration_minutes": duration_minutes,
            "status": s.status,
        })
    
    return result

