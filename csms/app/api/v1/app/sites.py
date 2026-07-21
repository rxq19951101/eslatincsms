"""Public, site-oriented discovery API for App users."""

from collections import defaultdict
from datetime import datetime, timezone
import re
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.app.chargers import (
    calculate_distance,
    get_current_app_user,
    get_public_charge_point_db,
)
from app.database.models import (
    AppUser,
    AppUserFavoriteSite,
    ChargePoint,
    EVSE,
    EVSEStatus,
    Site,
    Tariff,
)


router = APIRouter()
ONLINE_WINDOW_SECONDS = 300
STATUS_COUNT_KEYS = (
    "available",
    "charging",
    "offline",
    "faulted",
    "occupied",
    "unavailable",
    "unknown",
)
OCCUPIED_STATUSES = {
    "preparing",
    "finishing",
    "reserved",
    "suspendedev",
    "suspendedevse",
}

CONNECTOR_STANDARD_ALIASES = {
    "TYPE1": "TYPE_1",
    "J1772": "TYPE_1",
    "SAEJ1772": "TYPE_1",
    "TYPE2": "TYPE_2",
    "IEC62196TYPE2": "TYPE_2",
    "CCS1": "CCS_1",
    "COMBO1": "CCS_1",
    "CCS2": "CCS_2",
    "COMBO2": "CCS_2",
    "CHADEMO": "CHADEMO",
    "NACS": "NACS",
    "TESLA": "NACS",
    "GBTAC": "GB_T_AC",
    "GBTDC": "GB_T_DC",
    "SCHUKO": "SCHUKO",
}


def _normalize_connector_standard(value: Optional[str]) -> str:
    if not value or not value.strip():
        return "UNKNOWN"
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())
    if compact in CONNECTOR_STANDARD_ALIASES:
        return CONNECTOR_STANDARD_ALIASES[compact]
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_") or "UNKNOWN"


def _connector_current_type(standard: str) -> Optional[str]:
    if standard in {"TYPE_1", "TYPE_2", "GB_T_AC", "SCHUKO"}:
        return "AC"
    if standard in {"CCS_1", "CCS_2", "CHADEMO", "GB_T_DC"}:
        return "DC"
    return None


def _display_status(row: Optional[EVSEStatus], now: datetime) -> str:
    if row is None or row.last_seen is None:
        return "Offline"
    last_seen = row.last_seen
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    if (now - last_seen).total_seconds() >= ONLINE_WINDOW_SECONDS:
        return "Offline"
    return row.status or "Unknown"


def _aggregate_status(statuses: list[str]) -> str:
    if not statuses or all(status == "Offline" for status in statuses):
        return "Offline"
    if "Charging" in statuses:
        return "Charging"
    if "Available" in statuses:
        return "Available"
    if "Faulted" in statuses or "Unavailable" in statuses:
        return "Unavailable"
    return "Unknown"


def _status_counts(statuses: list[str]) -> dict[str, int]:
    counts = {key: 0 for key in STATUS_COUNT_KEYS}
    for status in statuses:
        normalized = status.strip().lower()
        if normalized in OCCUPIED_STATUSES:
            key = "occupied"
        elif normalized in counts:
            key = normalized
        else:
            key = "unknown"
        counts[key] += 1
    return counts


def _site_payload(
    site: Site,
    charge_points: list[ChargePoint],
    evses_by_charge_point: dict[UUID, list[EVSE]],
    status_by_evse: dict[UUID, EVSEStatus],
    tariff: Optional[Tariff],
    now: datetime,
) -> Dict[str, Any]:
    all_evses = [
        evse
        for charge_point in charge_points
        for evse in evses_by_charge_point.get(charge_point.id, [])
    ]
    statuses = [_display_status(status_by_evse.get(evse.id), now) for evse in all_evses]
    status_counts = _status_counts(statuses)
    connector_types = sorted(
        {evse.connector_type for evse in all_evses if evse.connector_type}
    )
    power_values = [
        power
        for power in (
            [evse.max_power_kw for evse in all_evses]
            + [charge_point.max_power_kw for charge_point in charge_points]
        )
        if power is not None
    ]
    option_statuses: dict[tuple[str, Optional[str], Optional[float]], list[str]] = defaultdict(list)
    for charge_point in charge_points:
        for evse in evses_by_charge_point.get(charge_point.id, []):
            standard = _normalize_connector_standard(evse.connector_type)
            power_kw = evse.max_power_kw
            if power_kw is None:
                power_kw = charge_point.max_power_kw
            normalized_power = float(power_kw) if power_kw is not None else None
            option_statuses[(
                standard,
                _connector_current_type(standard),
                normalized_power,
            )].append(_display_status(status_by_evse.get(evse.id), now))

    charging_options = [
        {
            "standard": standard,
            "current_type": current_type,
            "max_power_kw": power_kw,
            "available": sum(status == "Available" for status in option_group_statuses),
            "total": len(option_group_statuses),
            "status_counts": _status_counts(option_group_statuses),
        }
        for (standard, current_type, power_kw), option_group_statuses in sorted(
            option_statuses.items(),
            key=lambda item: (
                {"DC": 0, "AC": 1}.get(item[0][1], 2),
                -(item[0][2] or 0),
                item[0][0],
            ),
        )
    ]

    return {
        "id": str(site.id),
        "name": site.name,
        "address": site.address,
        "latitude": float(site.latitude),
        "longitude": float(site.longitude),
        "status": _aggregate_status(statuses),
        "charger_count": len(charge_points),
        "available_connectors": sum(status == "Available" for status in statuses),
        "total_connectors": len(all_evses),
        "status_counts": status_counts,
        "connector_types": connector_types,
        "charging_options": charging_options,
        "max_power_kw": max(power_values) if power_values else None,
        "price_per_kwh": float(tariff.base_price_per_kwh) if tariff else None,
        "has_pricing": tariff is not None,
    }


def _load_site_assets(
    db: Session,
    sites: list[Site],
) -> tuple[
    dict[UUID, list[ChargePoint]],
    dict[UUID, list[EVSE]],
    dict[UUID, EVSEStatus],
    dict[UUID, Tariff],
]:
    site_ids = [site.id for site in sites]
    if not site_ids:
        return {}, {}, {}, {}

    charge_points = db.query(ChargePoint).filter(
        ChargePoint.site_id.in_(site_ids),
        ChargePoint.is_active.is_(True),
    ).all()
    charge_points_by_site: dict[UUID, list[ChargePoint]] = defaultdict(list)
    for charge_point in charge_points:
        charge_points_by_site[charge_point.site_id].append(charge_point)

    charge_point_ids = [charge_point.id for charge_point in charge_points]
    evses = (
        db.query(EVSE).filter(EVSE.charge_point_id.in_(charge_point_ids)).all()
        if charge_point_ids
        else []
    )
    evses_by_charge_point: dict[UUID, list[EVSE]] = defaultdict(list)
    for evse in evses:
        evses_by_charge_point[evse.charge_point_id].append(evse)

    evse_ids = [evse.id for evse in evses]
    status_rows = (
        db.query(EVSEStatus).filter(EVSEStatus.evse_id.in_(evse_ids)).all()
        if evse_ids
        else []
    )
    status_by_evse = {row.evse_id: row for row in status_rows}

    tariffs = db.query(Tariff).filter(
        Tariff.site_id.in_(site_ids),
        Tariff.charge_point_id.is_(None),
        Tariff.is_active.is_(True),
    ).order_by(Tariff.created_at.desc()).all()
    tariff_by_site: dict[UUID, Tariff] = {}
    for tariff in tariffs:
        tariff_by_site.setdefault(tariff.site_id, tariff)

    return charge_points_by_site, evses_by_charge_point, status_by_evse, tariff_by_site


@router.get("", summary="获取公开充电站点列表（普通用户）")
async def list_sites_for_app(
    latitude: Optional[float] = Query(None, ge=-90, le=90),
    longitude: Optional[float] = Query(None, ge=-180, le=180),
    radius: Optional[float] = Query(None, gt=0, description="搜索半径（米）"),
    limit: int = Query(100, ge=1, le=200),
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_public_charge_point_db),
) -> list[dict]:
    sites = db.query(Site).filter(
        Site.is_active.is_(True),
        Site.latitude.isnot(None),
        Site.longitude.isnot(None),
    ).all()
    charge_points_by_site, evses_by_cp, status_by_evse, tariff_by_site = _load_site_assets(db, sites)
    now = datetime.now(timezone.utc)
    favorite_site_ids = {
        row[0]
        for row in db.query(AppUserFavoriteSite.site_id).filter(
            AppUserFavoriteSite.app_user_id == current_user_obj.id
        ).all()
    }
    result: list[dict] = []

    for site in sites:
        payload = _site_payload(
            site,
            charge_points_by_site.get(site.id, []),
            evses_by_cp,
            status_by_evse,
            tariff_by_site.get(site.id),
            now,
        )
        payload["is_favorite"] = site.id in favorite_site_ids
        if latitude is not None and longitude is not None:
            distance_km = calculate_distance(
                latitude,
                longitude,
                float(site.latitude),
                float(site.longitude),
            )
            if radius is not None and distance_km * 1000 > radius:
                continue
            payload["distance_km"] = round(distance_km, 2)
        result.append(payload)

    if latitude is not None and longitude is not None:
        result.sort(key=lambda item: item["distance_km"])
    else:
        result.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    return result[:limit]


@router.get("/{site_id}", summary="获取公开充电站点详情（普通用户）")
async def get_site_detail_for_app(
    site_id: UUID,
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_public_charge_point_db),
) -> dict:
    site = db.query(Site).filter(
        Site.id == site_id,
        Site.is_active.is_(True),
    ).first()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    charge_points_by_site, evses_by_cp, status_by_evse, tariff_by_site = _load_site_assets(db, [site])
    charge_points = charge_points_by_site.get(site.id, [])
    now = datetime.now(timezone.utc)
    payload = _site_payload(
        site,
        charge_points,
        evses_by_cp,
        status_by_evse,
        tariff_by_site.get(site.id),
        now,
    )
    payload["is_favorite"] = db.query(AppUserFavoriteSite.id).filter(
        AppUserFavoriteSite.app_user_id == current_user_obj.id,
        AppUserFavoriteSite.site_id == site.id,
    ).first() is not None
    payload["charge_points"] = [
        {
            "id": str(charge_point.id),
            "display_code": charge_point.display_code,
            "display_name": charge_point.display_name,
            "location_hint": charge_point.location_hint,
            "status": _aggregate_status([
                _display_status(status_by_evse.get(evse.id), now)
                for evse in evses_by_cp.get(charge_point.id, [])
            ]),
            "vendor": charge_point.vendor,
            "model": charge_point.model,
            "connectors": [
                {
                    "id": str(evse.id),
                    "connector_id": evse.evse_id,
                    "physical_reference": (
                        evse.physical_reference
                        if evse.physical_reference and evse.physical_reference.strip()
                        else f"{charge_point.display_code}-{evse.evse_id}"
                    ),
                    "status": _display_status(status_by_evse.get(evse.id), now),
                    "connector_type": evse.connector_type,
                    "power_kw": evse.max_power_kw,
                }
                for evse in sorted(
                    evses_by_cp.get(charge_point.id, []),
                    key=lambda item: item.evse_id,
                )
            ],
        }
        for charge_point in sorted(
            charge_points,
            key=lambda item: (item.display_code.casefold(), str(item.id)),
        )
    ]
    return payload
