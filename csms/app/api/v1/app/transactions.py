#
from __future__ import annotations

# APP用户 - 充电记录（会话历史）API
# - 仅返回当前终端用户自己的 ChargingSession
# - 通过 id_tag 进行归属（id_tag 为空时回退到 email / user_id）
#

import base64
import json
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request, Header
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.auth import get_current_user
from app.database.base import get_db, SuperSessionLocal
from app.database.models import AppUser, ChargingSession, ChargePoint, EVSE, Invoice, Site
from app.services.transaction_projection import TransactionProjectionService
from uuid import UUID

logger = get_logger("ocpp_csms")

router = APIRouter()

P002_MEDIA_TYPE = "application/vnd.eslatin.pay-mp-002.v1+json"


def _transaction_contract(accept: Optional[str]) -> str:
    if accept == P002_MEDIA_TYPE:
        return "p002"
    if accept and "application/vnd.eslatin." in accept:
        raise HTTPException(
            status_code=406,
            detail={
                "error": {
                    "code": "CONTRACT_VERSION_UNSUPPORTED",
                    "message": "Unsupported transaction contract version",
                    "retryable": False,
                }
            },
        )
    return "p001"


def _encode_cursor(
    start_time: datetime,
    session_id: UUID,
    *,
    user_id: UUID,
    status: str | None,
) -> str:
    payload = {
        "start_time": start_time.isoformat(),
        "session_id": str(session_id),
        "user_id": str(user_id),
        "status": status,
    }
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str,
    *,
    user_id: UUID,
    status: str | None,
) -> Tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        )
        if payload.get("user_id") != str(user_id) or payload.get("status") != status:
            raise ValueError
        return datetime.fromisoformat(str(payload["start_time"])), UUID(
            str(payload["session_id"])
        )
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "CURSOR_INVALID",
                    "message": "Transaction cursor is invalid or expired",
                    "retryable": False,
                }
            },
        ) from exc


def _p002_item(item: dict) -> dict:
    result = dict(item)
    result["id"] = str(result["id"])
    if result.get("energy_kwh") is not None:
        result["energy_kwh"] = format(Decimal(str(result["energy_kwh"])), ".3f")
    if result.get("duration_minutes") is not None:
        result["duration_minutes"] = format(
            Decimal(str(result["duration_minutes"])), ".2f"
        )
    return result


def get_app_platform_db():
    db = SuperSessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_app_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_app_platform_db),
) -> AppUser:
    user_id = current_user_payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    app_user = db.query(AppUser).filter(AppUser.id == UUID(str(user_id))).first()
    if not app_user:
        raise HTTPException(status_code=404, detail="User not found")

    return app_user


def _app_user_id_tag(app_user: AppUser) -> str:
    """
    平台账号的 ChargingSession.id_tag 我们使用 APP + UUID前17字符 (共20字符)
    OCPP 1.6J 规定 idTag 最大长度为 20 个字符
    """
    user_uuid_str = str(app_user.id).replace("-", "")
    return f"APP{user_uuid_str[:17]}"


@router.get("", summary="获取充电记录列表（终端用户）")
def list_app_transactions(
    request: Request,
    status: Optional[str] = Query(None, description="状态过滤（ongoing/completed/cancelled）"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    cursor: Optional[str] = Query(None),
    accept: Optional[str] = Header(None, alias="Accept"),
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    """
    返回当前用户的 ChargingSession 列表。
    """
    contract = _transaction_contract(accept)
    if contract == "p002":
        if limit > 100:
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "REQUEST_INVALID"}},
            )
        if "offset" in request.query_params:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "PAGINATION_MODE_INVALID",
                        "message": "P002 transactions use cursor pagination",
                        "retryable": False,
                    }
                },
                headers={"Vary": "Accept"},
            )

    id_tag = _app_user_id_tag(current_user_obj)

    query = db.query(ChargingSession).filter(
        or_(
            ChargingSession.app_user_id == current_user_obj.id,
            ChargingSession.user_id == str(current_user_obj.id),
            ChargingSession.id_tag == id_tag,
        )
    )
    if status:
        query = query.filter(ChargingSession.status == status)

    if contract == "p002" and cursor:
        cursor_start, cursor_id = _decode_cursor(
            cursor,
            user_id=current_user_obj.id,
            status=status,
        )
        query = query.filter(
            (ChargingSession.start_time < cursor_start)
            | (
                (ChargingSession.start_time == cursor_start)
                & (ChargingSession.id < cursor_id)
            )
        )
        sessions = query.order_by(
            ChargingSession.start_time.desc(), ChargingSession.id.desc()
        ).limit(limit + 1).all()
    elif contract == "p002":
        sessions = query.order_by(
            ChargingSession.start_time.desc(), ChargingSession.id.desc()
        ).limit(limit + 1).all()
    else:
        sessions = (
            query.order_by(ChargingSession.start_time.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

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
                "ocpp_identity": cp.ocpp_identity,
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
                "charge_point_id": str(s.charge_point_id),
                "ocpp_identity": site_info.get("ocpp_identity"),
                "evse_id": str(s.evse_id),
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "status": s.status,
                "energy_kwh": energy_kwh,
                "duration_minutes": duration_minutes,
                "site_name": site_info.get("site_name"),
                "site_address": site_info.get("site_address"),
            }
        )

    if contract == "p002":
        projected = TransactionProjectionService(
            db, current_user_obj
        ).project_sessions(sessions)
        result = [projected[s.id] for s in sessions]
        has_more = len(result) > limit
        result = [_p002_item(item) for item in result[:limit]]
        last = sessions[limit - 1] if has_more else None
        next_cursor = (
            _encode_cursor(
                last.start_time,
                last.id,
                user_id=current_user_obj.id,
                status=status,
            )
            if last is not None
            else None
        )
        return JSONResponse(
            status_code=200,
            content={
                "items": result,
                "page": {"next_cursor": next_cursor, "has_more": has_more},
            },
            media_type=P002_MEDIA_TYPE,
            headers={"Vary": "Accept"},
        )
    return result


@router.get("/{session_id}", summary="获取充电记录详情（终端用户）")
def get_app_transaction_detail(
    request: Request,
    session_id: UUID = Path(..., description="charging_sessions.id UUID"),
    accept: Optional[str] = Header(None, alias="Accept"),
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_app_platform_db),
) -> dict:
    contract = _transaction_contract(accept)
    id_tag = _app_user_id_tag(current_user_obj)

    query = db.query(ChargingSession).filter(
        ChargingSession.id == session_id,
        or_(
            ChargingSession.app_user_id == current_user_obj.id,
            ChargingSession.user_id == str(current_user_obj.id),
            ChargingSession.id_tag == id_tag,
        ),
    )
    s = query.first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if contract == "p002":
        projected = TransactionProjectionService(
            db, current_user_obj
        ).project_sessions([s], detail_session_id=s.id)[s.id]
        return JSONResponse(
            status_code=200,
            content=_p002_item(projected),
            media_type=P002_MEDIA_TYPE,
            headers={"Vary": "Accept"},
        )

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
    evse = db.query(EVSE).filter(EVSE.id == s.evse_id).first()
    invoice = db.query(Invoice).filter(Invoice.session_id == s.id).first()

    energy_kwh = None
    duration_minutes = None
    if s.meter_stop is not None and s.meter_start is not None:
        energy_wh = s.meter_stop - s.meter_start
        energy_kwh = energy_wh / 1000.0 if energy_wh > 0 else 0.0
    if s.end_time and s.start_time:
        duration_minutes = (s.end_time - s.start_time).total_seconds() / 60.0

    result = {
        "id": s.id,
        "transaction_id": s.transaction_id,
        "charge_point_id": str(s.charge_point_id),
        "ocpp_identity": cp.ocpp_identity if cp else None,
        "evse_id": str(s.evse_id),
        "start_time": s.start_time.isoformat() if s.start_time else None,
        "end_time": s.end_time.isoformat() if s.end_time else None,
        "status": s.status,
        "meter_start": s.meter_start,
        "meter_stop": s.meter_stop,
        "energy_kwh": energy_kwh,
        "duration_minutes": duration_minutes,
        "site_name": site_name,
        "site_address": site_address,
        "invoice_number": invoice.invoice_number if invoice else None,
        "total_amount": format(invoice.total_amount, ".2f") if invoice else None,
        "currency": "COP",
        "billing_status": invoice.status if invoice else None,
        "connector_number": evse.evse_id if evse else None,
        "connector_label": evse.physical_reference if evse else None,
        "charge_point_label": (
            (cp.display_name or cp.display_code) if cp else None
        ),
    }
    return result
