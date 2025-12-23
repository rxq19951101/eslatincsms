#
# 订单管理API
# 提供充电订单的查询和管理（使用新表结构）
#

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db, Order, ChargePoint, Invoice
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


@router.get("", summary="获取订单列表")
def list_orders(
    user_id: Optional[str] = Query(None, description="用户ID"),
    charge_point_id: Optional[str] = Query(None, description="充电桩ID"),
    status: Optional[str] = Query(None, description="状态过滤"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
) -> List[dict]:
    """获取订单列表（使用新表结构）"""
    logger.info(
        f"[API] GET /api/v1/orders | "
        f"用户ID: {user_id or '全部'} | "
        f"充电桩ID: {charge_point_id or '全部'} | "
        f"状态: {status or '全部'} | "
        f"限制: {limit} | 偏移: {offset}"
    )
    
    query = db.query(Order)
    
    if user_id:
        query = query.filter(Order.user_id == user_id)
    if charge_point_id:
        query = query.filter(Order.charge_point_id == charge_point_id)
    if status:
        query = query.filter(Order.status == status)
    
    orders = query.order_by(Order.created_at.desc()).offset(offset).limit(limit).all()
    
    logger.info(f"[API] GET /api/v1/orders 成功 | 返回 {len(orders)} 个订单")
    
    result = []
    for o in orders:
        # 获取关联的发票信息（如果有）
        invoice = db.query(Invoice).filter(Invoice.order_id == o.id).first()
        total_cost = invoice.total_amount if invoice else None
        
        # 从ChargingSession获取energy_kwh（如果有关联的session）
        energy_kwh = None
        duration_minutes = None
        if o.session_id:
            from app.database.models import ChargingSession
            session = db.query(ChargingSession).filter(ChargingSession.id == o.session_id).first()
            if session:
                # 计算电量（从meter_start和meter_stop）
                if session.meter_start is not None and session.meter_stop is not None:
                    energy_kwh = float(session.meter_stop - session.meter_start) / 1000.0  # Wh转kWh
                # 计算时长（分钟）
                if session.start_time and session.end_time:
                    duration = session.end_time - session.start_time
                    duration_minutes = int(duration.total_seconds() / 60)
        
        result.append({
            "id": o.id,
            "charge_point_id": o.charge_point_id,
            "user_id": o.user_id,
            "id_tag": o.id_tag,
            "start_time": o.start_time.isoformat() if o.start_time else None,
            "end_time": o.end_time.isoformat() if o.end_time else None,
            "energy_kwh": energy_kwh,
            "duration_minutes": duration_minutes,
            "total_cost": float(total_cost) if total_cost is not None else None,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })
    
    return result

