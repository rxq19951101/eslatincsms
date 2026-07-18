#
# 事务管理API
# 提供充电会话的查询和管理（使用新表结构）
#

from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.base import get_db, tenant_id_context
from app.database.models import ChargingSession, ChargePoint, EVSE
from app.core.permissions import get_current_admin_user
from app.core.logging_config import get_logger
from app.core.asset_identifiers import get_tenant_charge_point_by_reference

logger = get_logger("ocpp_csms")

router = APIRouter()


@router.get("", summary="获取充电会话列表")
def list_transactions(
    charge_point_id: Optional[str] = Query(None, description="充电桩ID"),
    status: Optional[str] = Query(None, description="状态过滤"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> List[dict]:
    """获取充电会话列表（使用新表结构）"""
    logger.info(
        f"[API] GET /api/v1/transactions | "
        f"充电桩ID: {charge_point_id or '全部'} | "
        f"状态: {status or '全部'} | "
        f"限制: {limit} | 偏移: {offset}"
    )
    
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    query = db.query(ChargingSession).filter(ChargingSession.tenant_id == tenant_id)
    
    if charge_point_id:
        charge_point = get_tenant_charge_point_by_reference(db, charge_point_id, tenant_id)
        if not charge_point:
            raise HTTPException(status_code=404, detail="Charge point not found")
        query = query.filter(ChargingSession.charge_point_id == charge_point.id)
    if status:
        query = query.filter(ChargingSession.status == status)
    
    sessions = query.order_by(ChargingSession.start_time.desc()).offset(offset).limit(limit).all()
    identities = {
        cp.id: cp.ocpp_identity
        for cp in db.query(ChargePoint).filter(
            ChargePoint.tenant_id == tenant_id,
            ChargePoint.id.in_({s.charge_point_id for s in sessions}),
        ).all()
    } if sessions else {}
    
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
            "charge_point_id": str(s.charge_point_id),
            "ocpp_identity": identities.get(s.charge_point_id),
            "id_tag": s.id_tag,
            "user_id": s.user_id,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "end_time": s.end_time.isoformat() if s.end_time else None,
            "energy_kwh": energy_kwh,
            "duration_minutes": duration_minutes,
            "status": s.status,
        })
    
    return result


@router.get("/active", summary="获取进行中的充电会话（实时监控）")
def list_active_sessions(
    limit: int = Query(50, le=200),
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    """返回 status=ongoing 的会话及最新计量值。"""
    from app.database.models import MeterValue

    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    query = db.query(ChargingSession).filter(
        ChargingSession.status == "ongoing",
        ChargingSession.tenant_id == tenant_id,
    )

    sessions = query.order_by(ChargingSession.start_time.desc()).limit(limit).all()
    identities = {
        cp.id: cp.ocpp_identity
        for cp in db.query(ChargePoint).filter(
            ChargePoint.tenant_id == tenant_id,
            ChargePoint.id.in_({s.charge_point_id for s in sessions}),
        ).all()
    } if sessions else {}
    result = []
    for s in sessions:
        latest = (
            db.query(MeterValue)
            .filter(MeterValue.session_id == s.id)
            .order_by(MeterValue.timestamp.desc())
            .first()
        )
        energy_kwh = None
        if s.meter_stop is not None and s.meter_start is not None:
            wh = s.meter_stop - s.meter_start
            energy_kwh = wh / 1000.0 if wh > 0 else 0
        elif latest and s.meter_start is not None:
            wh = latest.value - s.meter_start
            energy_kwh = wh / 1000.0 if wh > 0 else 0

        power_kw = None
        if latest and latest.sampled_value:
            for sv in latest.sampled_value if isinstance(latest.sampled_value, list) else []:
                if isinstance(sv, dict) and sv.get("measurand") == "Power.Active.Import":
                    try:
                        power_kw = float(sv.get("value", 0)) / 1000.0
                    except (TypeError, ValueError):
                        pass

        duration_minutes = None
        if s.start_time:
            duration_minutes = (datetime.now(timezone.utc) - s.start_time).total_seconds() / 60.0

        result.append({
            "id": s.id,
            "transaction_id": s.transaction_id,
            "charge_point_id": str(s.charge_point_id),
            "ocpp_identity": identities.get(s.charge_point_id),
            "user_id": s.user_id,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "energy_kwh": energy_kwh,
            "power_kw": power_kw,
            "duration_minutes": duration_minutes,
            "status": s.status,
        })
    return result
