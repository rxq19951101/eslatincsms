#
# APP用户 - 充电记录（会话历史）API
# - 仅返回当前终端用户自己的 ChargingSession
# - 通过 id_tag 进行归属（id_tag 为空时回退到 email / user_id）
#

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.auth import get_current_user
from app.database.base import get_db, tenant_id_context
from app.database.models import EndUser, ChargingSession, ChargePoint, Site

logger = get_logger("ocpp_csms")

router = APIRouter()


async def get_current_end_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EndUser:
    user_id = current_user_payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    end_user = db.query(EndUser).filter(EndUser.id == user_id).first()
    if not end_user:
        raise HTTPException(status_code=404, detail="User not found")

    return end_user


def _end_user_id_tag(end_user: EndUser) -> str:
    return (end_user.id_tag or end_user.email or str(end_user.id)).strip()


@router.get("", summary="获取充电记录列表（终端用户）")
def list_app_transactions(
    status: Optional[str] = Query(None, description="状态过滤（ongoing/completed/cancelled）"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_obj: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    """
    返回当前用户的 ChargingSession 列表。
    """
    tenant_id = tenant_id_context.get()
    id_tag = _end_user_id_tag(current_user_obj)

    query = db.query(ChargingSession).filter(ChargingSession.id_tag == id_tag)
    if tenant_id:
        query = query.filter(ChargingSession.tenant_id == tenant_id)
    if status:
        query = query.filter(ChargingSession.status == status)

    sessions = query.order_by(ChargingSession.start_time.desc()).offset(offset).limit(limit).all()

    # 预加载站点信息（charge_point -> site）
    cp_ids = [s.charge_point_id for s in sessions if s.charge_point_id]
    cp_site_map: Dict[str, dict] = {}
    if cp_ids:
        cps = (
            db.query(ChargePoint)
            .join(Site, ChargePoint.site_id == Site.id)
            .filter(ChargePoint.id.in_(cp_ids))
            .all()
        )
        for cp in cps:
            site = cp.site
            cp_site_map[cp.id] = {
                "site_name": site.name if site else None,
                "site_address": site.address if site else None,
            }

    result: List[dict] = []
    for s in sessions:
        energy_kwh = None
        duration_minutes = None
        if s.meter_stop is not None and s.meter_start is not None:
            energy_wh = s.meter_stop - s.meter_start
            energy_kwh = energy_wh / 1000.0 if energy_wh > 0 else 0.0
        if s.end_time and s.start_time:
            duration_minutes = (s.end_time - s.start_time).total_seconds() / 60.0

        site_info = cp_site_map.get(s.charge_point_id, {})
        result.append(
            {
                "id": s.id,
                "transaction_id": s.transaction_id,
                "charge_point_id": s.charge_point_id,
                "evse_id": s.evse_id,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "status": s.status,
                "energy_kwh": energy_kwh,
                "duration_minutes": duration_minutes,
                "site_name": site_info.get("site_name"),
                "site_address": site_info.get("site_address"),
            }
        )

    return result


@router.get("/{session_id}", summary="获取充电记录详情（终端用户）")
def get_app_transaction_detail(
    session_id: int = Path(..., description="charging_sessions.id"),
    current_user_obj: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
) -> dict:
    tenant_id = tenant_id_context.get()
    id_tag = _end_user_id_tag(current_user_obj)

    query = db.query(ChargingSession).filter(ChargingSession.id == session_id, ChargingSession.id_tag == id_tag)
    if tenant_id:
        query = query.filter(ChargingSession.tenant_id == tenant_id)
    s = query.first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    # 站点信息
    site_name = None
    site_address = None
    cp = (
        db.query(ChargePoint)
        .join(Site, ChargePoint.site_id == Site.id)
        .filter(ChargePoint.id == s.charge_point_id)
        .first()
    )
    if cp and cp.site:
        site_name = cp.site.name
        site_address = cp.site.address

    energy_kwh = None
    duration_minutes = None
    if s.meter_stop is not None and s.meter_start is not None:
        energy_wh = s.meter_stop - s.meter_start
        energy_kwh = energy_wh / 1000.0 if energy_wh > 0 else 0.0
    if s.end_time and s.start_time:
        duration_minutes = (s.end_time - s.start_time).total_seconds() / 60.0

    return {
        "id": s.id,
        "transaction_id": s.transaction_id,
        "charge_point_id": s.charge_point_id,
        "evse_id": s.evse_id,
        "start_time": s.start_time.isoformat() if s.start_time else None,
        "end_time": s.end_time.isoformat() if s.end_time else None,
        "status": s.status,
        "meter_start": s.meter_start,
        "meter_stop": s.meter_stop,
        "energy_kwh": energy_kwh,
        "duration_minutes": duration_minutes,
        "site_name": site_name,
        "site_address": site_address,
    }

