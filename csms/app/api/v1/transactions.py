#
# 事务管理API
# 提供充电会话的查询和管理（使用新表结构）
#

import csv
import io
import re
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from typing import List, Literal, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session, aliased
from app.database.base import get_db, tenant_id_context
from app.database.models import (
    AppUser,
    ChargingSession,
    ChargePoint,
    EVSE,
    Invoice,
    MeterValue,
    PaymentOrder,
    Site,
    Tariff,
)
from app.core.permissions import require_permission
from app.core.logging_config import get_logger
from app.core.asset_identifiers import get_tenant_charge_point_by_reference, parse_uuid
from app.services.billing_service import BillingService

logger = get_logger("ocpp_csms")

router = APIRouter()

_RECORD_NUMBER_RE = re.compile(r"^CHG-(\d{8})-(-?\d+)$", re.IGNORECASE)


def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _decimal_string(value: object, decimal_places: int) -> Optional[str]:
    if value is None:
        return None
    quantizer = Decimal("1").scaleb(-decimal_places)
    return format(Decimal(str(value)).quantize(quantizer, rounding=ROUND_HALF_UP), "f")


def _record_number(session: ChargingSession) -> str:
    start_time = _normalize_datetime(session.start_time)
    date_part = start_time.strftime("%Y%m%d") if start_time else "00000000"
    return f"CHG-{date_part}-{session.transaction_id}"


def _transaction_anomaly_codes(session: ChargingSession, evse: Optional[EVSE]) -> List[str]:
    codes: List[str] = []
    if (
        session.meter_start is not None
        and session.meter_stop is not None
        and session.meter_stop < session.meter_start
    ):
        codes.append("invalid_meter_delta")

    if session.status in {"completed", "cancelled"} and session.end_time is None:
        codes.append("missing_end_time")

    if (
        evse is not None
        and evse.max_power_kw is not None
        and session.meter_start is not None
        and session.meter_stop is not None
        and session.meter_stop >= session.meter_start
        and session.start_time is not None
        and session.end_time is not None
    ):
        duration_hours = Decimal(
            str((session.end_time - session.start_time).total_seconds())
        ) / Decimal("3600")
        if duration_hours > 0:
            energy_kwh = Decimal(session.meter_stop - session.meter_start) / Decimal("1000")
            average_power_kw = energy_kwh / duration_hours
            rating_threshold = Decimal(str(evse.max_power_kw)) * Decimal("1.25")
            if average_power_kw > rating_threshold:
                codes.append("power_exceeds_rating")

    return codes


def _build_transactions_query(
    db: Session,
    tenant_id,
    *,
    search: Optional[str],
    status: Optional[str],
    payment_status: Optional[str],
    site_id: Optional[str],
    charge_point_id: Optional[str],
    started_from: Optional[datetime],
    started_to: Optional[datetime],
):
    """Build the canonical tenant-scoped charging-record query used by list/export."""
    ranked_invoices = (
        db.query(
            *Invoice.__table__.c,
            func.row_number()
            .over(
                partition_by=Invoice.session_id,
                order_by=[
                    Invoice.issued_at.desc(),
                    Invoice.created_at.desc(),
                    Invoice.id.desc(),
                ],
            )
            .label("invoice_rank"),
        )
        .filter(Invoice.tenant_id == tenant_id)
        .subquery("ranked_transaction_invoices")
    )
    latest_invoice = aliased(Invoice, ranked_invoices)

    query = (
        db.query(
            ChargingSession,
            ChargePoint,
            Site,
            EVSE,
            latest_invoice,
            PaymentOrder,
            AppUser,
        )
        .join(
            ChargePoint,
            (ChargePoint.id == ChargingSession.charge_point_id)
            & (ChargePoint.tenant_id == tenant_id),
        )
        .join(
            Site,
            (Site.id == ChargePoint.site_id) & (Site.tenant_id == tenant_id),
        )
        .join(
            EVSE,
            (EVSE.id == ChargingSession.evse_id) & (EVSE.tenant_id == tenant_id),
        )
        .outerjoin(
            latest_invoice,
            (latest_invoice.session_id == ChargingSession.id)
            & (ranked_invoices.c.invoice_rank == 1),
        )
        .outerjoin(PaymentOrder, PaymentOrder.id == ChargingSession.payment_order_id)
        .outerjoin(AppUser, AppUser.id == ChargingSession.app_user_id)
        .filter(ChargingSession.tenant_id == tenant_id)
    )

    if site_id:
        parsed_site_id = parse_uuid(site_id)
        site = (
            db.query(Site)
            .filter(
                Site.tenant_id == tenant_id,
                or_(
                    Site.site_code == site_id,
                    Site.id == parsed_site_id if parsed_site_id is not None else False,
                ),
            )
            .first()
        )
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        query = query.filter(Site.id == site.id)

    if charge_point_id:
        charge_point = get_tenant_charge_point_by_reference(db, charge_point_id, tenant_id)
        if not charge_point:
            raise HTTPException(status_code=404, detail="Charge point not found")
        query = query.filter(ChargingSession.charge_point_id == charge_point.id)

    if status:
        query = query.filter(ChargingSession.status == status)

    if payment_status:
        query = query.filter(
            func.coalesce(
                PaymentOrder.status,
                latest_invoice.status,
                ChargingSession.payment_status,
            )
            == payment_status
        )

    normalized_from = _normalize_datetime(started_from)
    normalized_to = _normalize_datetime(started_to)
    if normalized_from and normalized_to and normalized_from > normalized_to:
        raise HTTPException(
            status_code=422,
            detail="started_from must be earlier than or equal to started_to",
        )
    if normalized_from:
        query = query.filter(ChargingSession.start_time >= normalized_from)
    if normalized_to:
        query = query.filter(ChargingSession.start_time <= normalized_to)

    normalized_search = search.strip() if search else None
    if normalized_search:
        like = f"%{normalized_search}%"
        search_conditions = [
            latest_invoice.invoice_number.ilike(like),
            Site.name.ilike(like),
            ChargePoint.display_code.ilike(like),
            ChargePoint.display_name.ilike(like),
            ChargePoint.ocpp_identity.ilike(like),
            ChargingSession.user_id.ilike(like),
            ChargingSession.id_tag.ilike(like),
            AppUser.email.ilike(like),
            AppUser.phone.ilike(like),
            AppUser.full_name.ilike(like),
            cast(ChargingSession.transaction_id, String).ilike(like),
        ]
        record_match = _RECORD_NUMBER_RE.fullmatch(normalized_search)
        if record_match:
            try:
                record_date = datetime.strptime(record_match.group(1), "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
                transaction_id = int(record_match.group(2))
            except ValueError:
                record_date = None
                transaction_id = None
            if (
                record_date is not None
                and transaction_id is not None
                and -(2**31) <= transaction_id < 2**31
            ):
                search_conditions.append(
                    (ChargingSession.transaction_id == transaction_id)
                    & (ChargingSession.start_time >= record_date)
                    & (ChargingSession.start_time < record_date + timedelta(days=1))
                )
        query = query.filter(or_(*search_conditions))

    return query


def _serialize_transaction_row(row) -> dict:
    session, charge_point, site, evse, invoice, payment_order, app_user = row
    duration_minutes = None
    if invoice is not None:
        duration_minutes = invoice.duration_minutes
    elif session.start_time and session.end_time:
        duration_minutes = Decimal(
            str((session.end_time - session.start_time).total_seconds())
        ) / Decimal("60")

    energy_kwh = None
    if invoice is not None:
        energy_kwh = invoice.energy_kwh
    elif session.meter_start is not None and session.meter_stop is not None:
        energy_kwh = Decimal(session.meter_stop - session.meter_start) / Decimal("1000")

    user_reference = session.user_id or session.id_tag
    if app_user:
        user_reference = app_user.email or app_user.phone or app_user.full_name or user_reference
    payment_status_value = session.payment_status
    if invoice:
        payment_status_value = invoice.status
    if payment_order:
        payment_status_value = payment_order.status

    return {
        "id": str(session.id),
        "record_number": _record_number(session),
        "invoice_number": invoice.invoice_number if invoice else None,
        "site": {
            "site_code": site.site_code,
            "name": site.name,
            "address": site.address,
        },
        "charger": {
            "display_code": charge_point.display_code,
            "display_name": charge_point.display_name,
            "ocpp_identity": charge_point.ocpp_identity,
        },
        "connector": {
            "id": str(evse.id),
            "connector_number": evse.evse_id,
            "physical_reference": evse.physical_reference,
            "connector_type": evse.connector_type,
            "max_power_kw": _decimal_string(evse.max_power_kw, 2),
        },
        "user_reference": user_reference,
        "start_time": session.start_time.isoformat() if session.start_time else None,
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "energy_kwh": _decimal_string(energy_kwh, 3),
        "duration_minutes": _decimal_string(duration_minutes, 2),
        "amount": _decimal_string(invoice.total_amount, 2) if invoice else None,
        "currency": (
            payment_order.currency
            if invoice and payment_order
            else "COP" if invoice else None
        ),
        "status": session.status,
        "payment_status": payment_status_value,
        "anomaly_codes": _transaction_anomaly_codes(session, evse),
    }


def _csv_safe(value: object) -> str:
    """Prevent spreadsheet software from interpreting exported values as formulas."""
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


@router.get("", summary="获取充电会话列表")
def list_transactions(
    search: Optional[str] = Query(None, max_length=100),
    status: Optional[Literal["ongoing", "completed", "cancelled"]] = Query(None),
    payment_status: Optional[str] = Query(None, max_length=50),
    site_id: Optional[str] = Query(None),
    charge_point_id: Optional[str] = Query(None),
    started_from: Optional[datetime] = Query(None),
    started_to: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_obj=Depends(require_permission("transactions.read")),
    db: Session = Depends(get_db),
) -> dict:
    """Return tenant-scoped charging records with server-side filters and pagination."""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")

    query = _build_transactions_query(
        db,
        tenant_id,
        search=search,
        status=status,
        payment_status=payment_status,
        site_id=site_id,
        charge_point_id=charge_point_id,
        started_from=started_from,
        started_to=started_to,
    )

    total = query.order_by(None).with_entities(func.count(ChargingSession.id)).scalar() or 0
    rows = (
        query.order_by(ChargingSession.start_time.desc(), ChargingSession.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [_serialize_transaction_row(row) for row in rows]

    logger.info(
        "[API] GET /api/v1/transactions success | tenant=%s total=%s returned=%s",
        tenant_id,
        total,
        len(items),
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/export", summary="导出充电记录 CSV")
def export_transactions(
    search: Optional[str] = Query(None, max_length=100),
    status: Optional[Literal["ongoing", "completed", "cancelled"]] = Query(None),
    payment_status: Optional[str] = Query(None, max_length=50),
    site_id: Optional[str] = Query(None),
    charge_point_id: Optional[str] = Query(None),
    started_from: Optional[datetime] = Query(None),
    started_to: Optional[datetime] = Query(None),
    current_user_obj=Depends(require_permission("transactions.read")),
    db: Session = Depends(get_db),
) -> Response:
    """Export the same tenant-scoped filtered records as the canonical list query."""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")

    query = _build_transactions_query(
        db,
        tenant_id,
        search=search,
        status=status,
        payment_status=payment_status,
        site_id=site_id,
        charge_point_id=charge_point_id,
        started_from=started_from,
        started_to=started_to,
    )
    rows = (
        query.order_by(ChargingSession.start_time.desc(), ChargingSession.id.desc())
        .limit(10_001)
        .all()
    )
    if len(rows) > 10_000:
        raise HTTPException(
            status_code=422,
            detail="Export exceeds 10000 records; narrow the date range or filters",
        )

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "record_number",
        "invoice_number",
        "site_code",
        "site_name",
        "site_address",
        "charger_display_code",
        "charger_display_name",
        "connector_number",
        "connector_reference",
        "connector_type",
        "max_power_kw",
        "user_reference",
        "start_time",
        "end_time",
        "energy_kwh",
        "duration_minutes",
        "amount",
        "currency",
        "status",
        "payment_status",
        "anomaly_codes",
    ])
    for row in rows:
        item = _serialize_transaction_row(row)
        writer.writerow([
            _csv_safe(item["record_number"]),
            _csv_safe(item["invoice_number"]),
            _csv_safe(item["site"]["site_code"]),
            _csv_safe(item["site"]["name"]),
            _csv_safe(item["site"]["address"]),
            _csv_safe(item["charger"]["display_code"]),
            _csv_safe(item["charger"]["display_name"]),
            _csv_safe(item["connector"]["connector_number"]),
            _csv_safe(item["connector"]["physical_reference"]),
            _csv_safe(item["connector"]["connector_type"]),
            _csv_safe(item["connector"]["max_power_kw"]),
            _csv_safe(item["user_reference"]),
            _csv_safe(item["start_time"]),
            _csv_safe(item["end_time"]),
            _csv_safe(item["energy_kwh"]),
            _csv_safe(item["duration_minutes"]),
            _csv_safe(item["amount"]),
            _csv_safe(item["currency"]),
            _csv_safe(item["status"]),
            _csv_safe(item["payment_status"]),
            _csv_safe("|".join(item["anomaly_codes"])),
        ])

    filename_date = datetime.now(timezone.utc).strftime("%Y%m%d")
    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    logger.info(
        "[API] GET /api/v1/transactions/export success | tenant=%s exported=%s",
        tenant_id,
        len(rows),
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="charging_records_{filename_date}.csv"'
            )
        },
    )


@router.get("/active", summary="获取进行中的充电会话（实时监控）")
def list_active_sessions(
    limit: int = Query(50, le=200),
    current_user_obj=Depends(require_permission("transactions.read")),
    db: Session = Depends(get_db),
) -> List[dict]:
    """返回 status=ongoing 的会话及最新计量值。"""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    query = db.query(ChargingSession).filter(
        ChargingSession.status == "ongoing",
        ChargingSession.tenant_id == tenant_id,
    )

    sessions = query.order_by(ChargingSession.start_time.desc()).limit(limit).all()
    if not sessions:
        return []

    session_ids = {session.id for session in sessions}
    charge_point_ids = {session.charge_point_id for session in sessions}
    evse_ids = {session.evse_id for session in sessions}

    charge_points = {
        charge_point.id: charge_point
        for charge_point in db.query(ChargePoint).filter(
            ChargePoint.tenant_id == tenant_id,
            ChargePoint.id.in_(charge_point_ids),
        ).all()
    }
    site_ids = {charge_point.site_id for charge_point in charge_points.values()}
    sites = {
        site.id: site
        for site in db.query(Site).filter(
            Site.tenant_id == tenant_id,
            Site.id.in_(site_ids),
        ).all()
    }
    evses = {
        evse.id: evse
        for evse in db.query(EVSE).filter(
            EVSE.tenant_id == tenant_id,
            EVSE.id.in_(evse_ids),
        ).all()
    }

    latest_timestamps = (
        db.query(
            MeterValue.session_id.label("session_id"),
            func.max(MeterValue.timestamp).label("timestamp"),
        )
        .filter(
            MeterValue.tenant_id == tenant_id,
            MeterValue.session_id.in_(session_ids),
        )
        .group_by(MeterValue.session_id)
        .subquery()
    )
    latest_meter_values = {}
    for meter_value in (
        db.query(MeterValue)
        .join(
            latest_timestamps,
            (MeterValue.session_id == latest_timestamps.c.session_id)
            & (MeterValue.timestamp == latest_timestamps.c.timestamp),
        )
        .filter(MeterValue.tenant_id == tenant_id)
        .all()
    ):
        latest_meter_values.setdefault(meter_value.session_id, meter_value)

    now = datetime.now(timezone.utc)
    tariffs = (
        db.query(Tariff)
        .filter(
            Tariff.tenant_id == tenant_id,
            Tariff.is_active.is_(True),
            Tariff.valid_from <= now,
            or_(Tariff.valid_until.is_(None), Tariff.valid_until >= now),
            or_(
                Tariff.charge_point_id.in_(charge_point_ids),
                Tariff.site_id.in_(site_ids),
            ),
        )
        .order_by(Tariff.valid_from.desc())
        .all()
    )
    tariffs_by_charge_point = {}
    tariffs_by_site = {}
    for tariff in tariffs:
        if tariff.charge_point_id in charge_point_ids:
            tariffs_by_charge_point.setdefault(tariff.charge_point_id, tariff)
        if tariff.charge_point_id is None and tariff.site_id in site_ids:
            tariffs_by_site.setdefault(tariff.site_id, tariff)

    result = []
    for s in sessions:
        charge_point = charge_points.get(s.charge_point_id)
        site = sites.get(charge_point.site_id) if charge_point else None
        evse = evses.get(s.evse_id)
        latest = latest_meter_values.get(s.id)
        current_meter = s.meter_stop if s.meter_stop is not None else (latest.value if latest else None)
        energy_kwh = None
        has_reliable_energy = s.meter_start is not None and current_meter is not None
        if has_reliable_energy:
            wh = current_meter - s.meter_start
            energy_kwh = wh / 1000.0 if wh > 0 else 0
            has_reliable_energy = wh >= 0

        power_kw = None
        if latest and latest.sampled_value:
            for sv in latest.sampled_value if isinstance(latest.sampled_value, list) else []:
                if isinstance(sv, dict) and sv.get("measurand") == "Power.Active.Import":
                    try:
                        power_kw = float(sv.get("value", 0)) / 1000.0
                    except (TypeError, ValueError):
                        pass

        duration_minutes = None
        normalized_start_time = s.start_time
        if s.start_time:
            if normalized_start_time.tzinfo is None:
                normalized_start_time = normalized_start_time.replace(tzinfo=timezone.utc)
            duration_minutes = (now - normalized_start_time).total_seconds() / 60.0

        tariff = tariffs_by_charge_point.get(s.charge_point_id)
        if tariff is None and charge_point:
            tariff = tariffs_by_site.get(charge_point.site_id)
        estimated_cost = None
        currency = None
        if tariff is not None and has_reliable_energy:
            cost_session = SimpleNamespace(
                meter_start=s.meter_start,
                meter_stop=current_meter,
                start_time=normalized_start_time,
                end_time=None,
            )
            estimated_cost = str(BillingService.calculate_cost(cost_session, tariff)["total_amount"])
            currency = "COP"

        result.append({
            "id": s.id,
            "charge_point_id": str(s.charge_point_id),
            "user_id": s.user_id,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "energy_kwh": energy_kwh,
            "power_kw": power_kw,
            "duration_minutes": duration_minutes,
            "status": s.status,
            "site": {
                "id": site.site_code,
                "name": site.name,
                "address": site.address,
            } if site else None,
            "charger": {
                "id": str(charge_point.id),
                "display_code": charge_point.display_code,
                "display_name": charge_point.display_name,
                "ocpp_identity": charge_point.ocpp_identity,
            } if charge_point else None,
            "connector": {
                "id": str(evse.id),
                "connector_number": evse.evse_id,
                "physical_reference": evse.physical_reference,
            } if evse else None,
            "user_reference": s.user_id,
            "last_meter_at": latest.timestamp.isoformat() if latest else None,
            "estimated_cost": estimated_cost,
            "currency": currency,
        })
    return result
